# apps/iprs/services.py
"""
IPRS Proxy Service
Handles communication with the UFAA IPRS Proxy API.

This service is designed to be used by unauthenticated users during
the registration process. It does not require a User instance.
"""
import logging
import time
from typing import Optional, Dict, Any, Tuple

import requests
from django.conf import settings
from django.utils import timezone

from .models import IprsSearchLog, IprsCache

logger = logging.getLogger(__name__)


class IprsServiceError(Exception):
    """Base exception for IPRS service errors"""
    pass


class IprsNotFoundError(IprsServiceError):
    """Raised when ID card is not found in IPRS"""
    pass


class IprsTimeoutError(IprsServiceError):
    """Raised when IPRS API times out"""
    pass


class IprsRateLimitError(IprsServiceError):
    """Raised when IPRS API rate limits us"""
    pass


def build_other_names(data: Dict[str, Any]) -> str:
    """
    Combine first_Name and other_Name into 'other names'.
    
    In Kenyan naming convention, the surname is the family name and
    everything else is the 'other names'.
    """
    first_name = (data.get('first_Name') or '').strip()
    other_name = (data.get('other_Name') or '').strip()
    return ' '.join(p for p in [first_name, other_name] if p).strip()


def build_full_name(data: Dict[str, Any]) -> str:
    """
    Build the full name in Kenyan convention: Surname OtherNames.
    """
    surname = (data.get('surname') or '').strip()
    other_names = build_other_names(data)
    return ' '.join(p for p in [surname, other_names] if p).strip()


class IprsService:
    """
    Service class for interacting with the IPRS Proxy API.
    
    Usage:
        service = IprsService()
        result = service.lookup_id('27457180')
    """
    
    # Default configuration (can be overridden in Django settings)
    DEFAULT_BASE_URL = 'https://api.ufaa.go.ke/api/IprsProxy'
    DEFAULT_TIMEOUT = 30  # seconds
    DEFAULT_CACHE_TTL_HOURS = 24
    DEFAULT_MAX_RETRIES = 2
    DEFAULT_RETRY_DELAY = 1  # seconds
    
    # Rate limiting: max searches per IP per hour
    DEFAULT_MAX_SEARCHES_PER_IP_PER_HOUR = 5
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        cache_ttl_hours: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[int] = None,
    ):
        """
        Initialize the IPRS service.
        
        Args:
            base_url: Base URL for the IPRS API (defaults to settings.IPRS_API_BASE_URL)
            timeout: Request timeout in seconds (defaults to settings.IPRS_API_TIMEOUT)
            cache_ttl_hours: Cache TTL in hours (defaults to settings.IPRS_CACHE_TTL_HOURS)
            max_retries: Maximum retry attempts (defaults to settings.IPRS_MAX_RETRIES)
            retry_delay: Delay between retries in seconds (defaults to settings.IPRS_RETRY_DELAY)
        """
        self.base_url = base_url or getattr(
            settings, 'IPRS_API_BASE_URL', self.DEFAULT_BASE_URL
        ).rstrip('/')
        self.timeout = timeout or getattr(
            settings, 'IPRS_API_TIMEOUT', self.DEFAULT_TIMEOUT
        )
        self.cache_ttl_hours = cache_ttl_hours or getattr(
            settings, 'IPRS_CACHE_TTL_HOURS', self.DEFAULT_CACHE_TTL_HOURS
        )
        self.max_retries = max_retries or getattr(
            settings, 'IPRS_MAX_RETRIES', self.DEFAULT_MAX_RETRIES
        )
        self.retry_delay = retry_delay or getattr(
            settings, 'IPRS_RETRY_DELAY', self.DEFAULT_RETRY_DELAY
        )
        self.max_searches_per_ip_per_hour = getattr(
            settings, 'IPRS_MAX_SEARCHES_PER_IP_PER_HOUR',
            self.DEFAULT_MAX_SEARCHES_PER_IP_PER_HOUR
        )
        
        # Configure session with headers
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': getattr(
                settings, 'IPRS_USER_AGENT', 'UFAA-Reunite/1.0'
            ),
        })
        
        # Add API key if configured
        api_key = getattr(settings, 'IPRS_API_KEY', None)
        if api_key:
            self.session.headers['Authorization'] = f'Bearer {api_key}'
    
    def lookup_id(
        self,
        id_card: str,
        use_cache: bool = True,
        log_search: bool = True,
        requested_from_ip: Optional[str] = None,
        user_agent: str = '',
        device_fingerprint: str = '',
    ) -> Dict[str, Any]:
        """
        Look up a national ID number in the IPRS system.
        
        Args:
            id_card: The national ID number to look up
            use_cache: Whether to use cached results (default True)
            log_search: Whether to log the search (default True)
            requested_from_ip: IP address of the requester (for audit/rate limiting)
            user_agent: User agent string of the requester
            device_fingerprint: Device fingerprint from the mobile app
            
        Returns:
            dict: Personal details from IPRS (with surname and other_names added)
            
        Raises:
            IprsNotFoundError: If ID card not found
            IprsTimeoutError: If API times out
            IprsRateLimitError: If rate limited
            IprsServiceError: For other errors
        """
        # Validate input
        id_card = self._validate_id_card(id_card)
        
        # Check IP-based rate limit (only for non-cached requests)
        if requested_from_ip:
            self._check_rate_limit(requested_from_ip)
        
        # Check cache first
        if use_cache:
            cached = IprsCache.get_cached(id_card)
            if cached:
                logger.info(f"IPRS cache hit for ID: {id_card}")
                if log_search:
                    self._log_search(
                        id_card=id_card,
                        status='success' if cached.is_valid else 'not_found',
                        response_data=cached.raw_response,
                        requested_from_ip=requested_from_ip,
                        user_agent=user_agent,
                        device_fingerprint=device_fingerprint,
                    )
                if not cached.is_valid:
                    raise IprsNotFoundError(f"ID card {id_card} not found in IPRS (cached)")
                return self._enrich(cached.raw_response)
        
        # Make API request
        start_time = time.time()
        response_data = None
        status = 'error'
        error_message = ''
        
        try:
            response_data, status, error_message = self._make_request(id_card)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Handle not found
            if status == 'not_found':
                # Cache the negative result (shorter TTL)
                IprsCache.set_cache(
                    id_card=id_card,
                    data=response_data,
                    is_valid=False,
                    ttl_hours=min(self.cache_ttl_hours, 6),  # Max 6 hours for negative cache
                )
                raise IprsNotFoundError(f"ID card {id_card} not found in IPRS")
            
            # Cache successful result
            IprsCache.set_cache(
                id_card=id_card,
                data=response_data,
                is_valid=True,
                ttl_hours=self.cache_ttl_hours,
            )
            
            # Log successful search
            if log_search:
                self._log_search(
                    id_card=id_card,
                    status='success',
                    response_data=response_data,
                    requested_from_ip=requested_from_ip,
                    user_agent=user_agent,
                    device_fingerprint=device_fingerprint,
                    response_time_ms=response_time_ms,
                )
            
            return self._enrich(response_data)
            
        except IprsNotFoundError:
            # Already logged above
            raise
        except IprsTimeoutError as e:
            error_message = str(e)
            if log_search:
                self._log_search(
                    id_card=id_card,
                    status='timeout',
                    error_message=error_message,
                    requested_from_ip=requested_from_ip,
                    user_agent=user_agent,
                    device_fingerprint=device_fingerprint,
                )
            raise
        except IprsRateLimitError as e:
            error_message = str(e)
            if log_search:
                self._log_search(
                    id_card=id_card,
                    status='rate_limited',
                    error_message=error_message,
                    requested_from_ip=requested_from_ip,
                    user_agent=user_agent,
                    device_fingerprint=device_fingerprint,
                )
            raise
        except Exception as e:
            error_message = str(e)
            logger.exception(f"IPRS lookup failed for ID {id_card}: {e}")
            if log_search:
                self._log_search(
                    id_card=id_card,
                    status='error',
                    error_message=error_message,
                    requested_from_ip=requested_from_ip,
                    user_agent=user_agent,
                    device_fingerprint=device_fingerprint,
                )
            raise IprsServiceError(f"IPRS lookup failed: {error_message}")
    
    @staticmethod
    def _enrich(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich the IPRS response with computed name fields.
        
        Adds:
            - other_names: first_Name + other_Name combined
            - full_name: surname + other_names
        """
        if not data:
            return data
        data['other_names'] = build_other_names(data)
        data['full_name'] = build_full_name(data)
        return data
    
    def _check_rate_limit(self, ip_address: str):
        """
        Check if the IP address has exceeded the rate limit.
        
        Raises:
            IprsRateLimitError: If rate limit exceeded
        """
        count = IprsSearchLog.get_ip_search_count(ip_address, hours=1)
        if count >= self.max_searches_per_ip_per_hour:
            logger.warning(
                f"IPRS rate limit exceeded for IP {ip_address}: "
                f"{count} searches in the last hour"
            )
            raise IprsRateLimitError(
                f"Too many IPRS lookups from your IP address. "
                f"Maximum {self.max_searches_per_ip_per_hour} per hour."
            )
    
    def _make_request(self, id_card: str) -> Tuple[Dict[str, Any], str, str]:
        """
        Make the actual HTTP request to the IPRS API with retries.
        
        Returns:
            Tuple of (response_data, status, error_message)
        """
        url = f"{self.base_url}/{id_card}"
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"IPRS request to {url} (attempt {attempt + 1})")
                
                response = self.session.get(url, timeout=self.timeout)
                
                # Handle rate limiting from upstream
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', self.retry_delay))
                    if attempt < self.max_retries:
                        logger.warning(f"IPRS rate limited, retrying after {retry_after}s")
                        time.sleep(retry_after)
                        continue
                    raise IprsRateLimitError("IPRS API rate limit exceeded")
                
                # Handle not found
                if response.status_code == 404:
                    return {'error': 'ID card not found'}, 'not_found', ''
                
                # Handle server errors (retryable)
                if response.status_code >= 500:
                    if attempt < self.max_retries:
                        logger.warning(f"IPRS server error {response.status_code}, retrying...")
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    response.raise_for_status()
                
                # Handle client errors (not retryable)
                if response.status_code >= 400:
                    response.raise_for_status()
                
                # Parse response
                data = response.json()
                
                # Check for error in response body
                if 'error' in data:
                    error_msg = data.get('error', 'Unknown error')
                    if 'not found' in error_msg.lower():
                        return data, 'not_found', ''
                    return data, 'error', error_msg
                
                # Validate response has expected fields
                if not data.get('idCard'):
                    return data, 'error', 'Invalid response from IPRS'
                
                return data, 'success', ''
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(f"IPRS request timed out, retrying...")
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise IprsTimeoutError(f"IPRS API timed out after {self.timeout}s")
                
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(f"IPRS connection error, retrying...")
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise IprsServiceError(f"Could not connect to IPRS API: {e}")
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                raise IprsServiceError(f"IPRS request failed: {e}")
        
        # Should not reach here, but just in case
        raise IprsServiceError(f"IPRS request failed after {self.max_retries + 1} attempts: {last_exception}")
    
    def _validate_id_card(self, id_card: str) -> str:
        """
        Validate and normalize the ID card number.
        
        Args:
            id_card: Raw ID card input
            
        Returns:
            Normalized ID card string
            
        Raises:
            ValueError: If ID card is invalid
        """
        if not id_card:
            raise ValueError("ID card number is required")
        
        # Convert to string and strip whitespace
        id_card = str(id_card).strip()
        
        # Remove any non-digit characters
        id_card = ''.join(c for c in id_card if c.isdigit())
        
        # Validate length (Kenyan IDs are typically 7-8 digits)
        if len(id_card) < 7 or len(id_card) > 8:
            raise ValueError(
                f"Invalid ID card number length: {len(id_card)}. "
                "Kenyan National IDs must be 7-8 digits."
            )
        
        return id_card
    
    def _log_search(
        self,
        id_card: str,
        status: str,
        response_data: Optional[Dict] = None,
        error_message: str = '',
        requested_from_ip: Optional[str] = None,
        user_agent: str = '',
        device_fingerprint: str = '',
        response_time_ms: Optional[int] = None,
    ):
        """Log the search to the database"""
        try:
            # Extract details from response if available
            surname = ''
            other_names = ''
            gender = ''
            iprs_id = None
            searched_at = None
            
            if response_data and 'idCard' in response_data:
                surname = response_data.get('surname', '') or ''
                other_names = build_other_names(response_data)
                gender = response_data.get('gender', '')
                iprs_id = response_data.get('id')
                searched_at_str = response_data.get('searchedAt')
                if searched_at_str:
                    try:
                        from django.utils.dateparse import parse_datetime
                        searched_at = parse_datetime(searched_at_str)
                    except Exception:
                        pass
            
            IprsSearchLog.objects.create(
                id_card=id_card,
                requested_from_ip=requested_from_ip,
                user_agent=user_agent,
                device_fingerprint=device_fingerprint,
                status=status,
                response_data=response_data,
                error_message=error_message,
                surname=surname,
                other_names=other_names,
                gender=gender,
                iprs_id=iprs_id,
                searched_at=searched_at,
                response_time_ms=response_time_ms,
            )
        except Exception as e:
            # Don't let logging errors break the main flow
            logger.error(f"Failed to log IPRS search: {e}")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check if the IPRS API is reachable.
        
        Returns:
            dict: Health check result
        """
        result = {
            'healthy': False,
            'base_url': self.base_url,
            'error': None,
        }
        
        try:
            response = self.session.get(
                f"{self.base_url}/test",
                timeout=5,
                allow_redirects=False,
            )
            result['healthy'] = response.status_code < 500
            result['status_code'] = response.status_code
        except requests.exceptions.RequestException as e:
            result['error'] = str(e)
        
        return result


# Singleton instance for convenience
_default_service = None


def get_iprs_service() -> IprsService:
    """Get the default IPRS service instance"""
    global _default_service
    if _default_service is None:
        _default_service = IprsService()
    return _default_service
