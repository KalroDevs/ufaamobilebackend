# apps/live_operations/tasks.py
from celery import shared_task
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta
import logging
from .services import LiveDatabaseService
from apps.claims.models import Claim

logger = logging.getLogger(__name__)


@shared_task(name='apps.live_operations.tasks.push_pending_claims_to_live')
def push_pending_claims_to_live():
    """
    Celery task to push all pending claims to live database
    Runs every 3 hours
    """
    logger.info("Starting scheduled task: push_pending_claims_to_live")
    
    try:
        result = LiveDatabaseService.push_pending_claims_to_live()
        
        logger.info(f"Push task completed: {result}")
        
        # Log summary
        if result.get('success'):
            logger.info(
                f"Claims pushed: {result.get('pushed', 0)}, "
                f"Failed: {result.get('failed', 0)}, "
                f"Skipped: {result.get('skipped', 0)}"
            )
        else:
            logger.error(f"Push task failed: {result.get('message', 'Unknown error')}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in push_pending_claims_to_live task: {e}")
        raise


@shared_task(name='apps.live_operations.tasks.push_single_claim_to_live')
def push_single_claim_to_live(claim_id):
    """
    Celery task to push a single claim to live database
    
    Args:
        claim_id: The ID of the claim to push
    """
    logger.info(f"Starting task: push_single_claim_to_live for claim ID {claim_id}")
    
    try:
        result = LiveDatabaseService.push_claim_to_live(claim_id)
        
        logger.info(f"Single push completed for claim ID {claim_id}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in push_single_claim_to_live task for claim ID {claim_id}: {e}")
        raise


@shared_task(name='apps.live_operations.tasks.push_claims_by_ids')
def push_claims_by_ids(claim_ids):
    """
    Celery task to push specific claims by IDs
    
    Args:
        claim_ids: List of claim IDs to push
    """
    logger.info(f"Starting task: push_claims_by_ids for {len(claim_ids)} claims")
    logger.info(f"Claim IDs: {claim_ids}")
    
    try:
        result = LiveDatabaseService.push_claims_by_ids(claim_ids)
        
        logger.info(f"Push by IDs completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in push_claims_by_ids task: {e}")
        raise


@shared_task(name='apps.live_operations.tasks.sync_claim_statuses')
def sync_claim_statuses():
    """
    Celery task to sync claim statuses from live database back to default database
    Runs every 6 hours
    """
    logger.info("Starting scheduled task: sync_claim_statuses")
    
    try:
        from .models import LiveOnlineClaim
        
        # Use iterator to avoid loading all records into memory
        live_claims = LiveOnlineClaim.objects.all().iterator()
        synced_count = 0
        failed_count = 0
        skipped_count = 0
        
        for live_claim in live_claims:
            try:
                # Find matching claim in default database
                claim = Claim.objects.filter(no=live_claim.claim_no).first()
                
                if not claim:
                    skipped_count += 1
                    logger.debug(f"Claim {live_claim.claim_no} not found in default database")
                    continue
                
                # Map status from live database to default database status
                # Live status is stored as integer, map to string
                status_mapping = {
                    0: 'Draft',
                    1: 'Pending',
                    2: 'Under_Review',
                    3: 'In_Progress',
                    4: 'Processing',
                    5: 'Approved',
                    6: 'Rejected',
                    7: 'Paid',
                    8: 'Completed',
                    9: 'Archived',
                    10: 'Cancelled',
                }
                
                # Get status string from mapping
                live_status_int = live_claim.status
                if isinstance(live_status_int, int):
                    live_status_str = status_mapping.get(live_status_int, 'Pending')
                else:
                    live_status_str = live_status_int
                
                if claim.status != live_status_str:
                    # Sync status
                    result = LiveDatabaseService.sync_claim_status(
                        live_claim.claim_no, 
                        live_status_str
                    )
                    
                    if result.get('success'):
                        synced_count += 1
                        logger.info(f"Synced claim {live_claim.claim_no} status to {live_status_str}")
                    else:
                        failed_count += 1
                        logger.error(f"Failed to sync claim {live_claim.claim_no}: {result.get('message')}")
                else:
                    skipped_count += 1
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Error syncing claim {live_claim.claim_no}: {e}")
        
        result = {
            'success': True,
            'synced': synced_count,
            'failed': failed_count,
            'skipped': skipped_count,
            'total': synced_count + failed_count + skipped_count,
            'message': f'Synced {synced_count} claims, {failed_count} failed, {skipped_count} skipped'
        }
        
        logger.info(f"Sync task completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in sync_claim_statuses task: {e}")
        raise


@shared_task(name='apps.live_operations.tasks.push_pending_claims_with_filter')
def push_pending_claims_with_filter(status_filter=None, days_old=None, limit=None):
    """
    Celery task to push pending claims with filters
    
    Args:
        status_filter: List of statuses to filter (e.g., ['Pending', 'Under_Review'])
        days_old: Only push claims older than X days
        limit: Maximum number of claims to push
    """
    logger.info(f"Starting filtered push task with status_filter={status_filter}, days_old={days_old}, limit={limit}")
    
    try:
        # Build the query
        claims = Claim.objects.filter(status__in=['Pending', 'Under_Review'])
        
        # Apply status filter if provided
        if status_filter:
            if isinstance(status_filter, str):
                status_filter = [status_filter]
            claims = claims.filter(status__in=status_filter)
        
        # Apply days filter if provided
        if days_old:
            cutoff_date = timezone.now() - timedelta(days=days_old)
            # Use date_created or created_at - adjust field name as needed
            # Check which date field exists on your Claim model
            if hasattr(Claim, 'created_at'):
                claims = claims.filter(created_at__lte=cutoff_date)
            elif hasattr(Claim, 'date_created'):
                claims = claims.filter(date_created__lte=cutoff_date)
            elif hasattr(Claim, 'submitted_at'):
                claims = claims.filter(submitted_at__lte=cutoff_date)
            else:
                # If no date field, use id as fallback
                logger.warning("No date field found on Claim model, using id filter")
                claims = claims.filter(id__lte=cutoff_date)
        
        # Apply limit if provided
        if limit:
            claims = claims[:limit]
        
        claim_ids = list(claims.values_list('id', flat=True))
        
        if not claim_ids:
            return {
                'success': True,
                'message': 'No claims found matching the filters',
                'pushed': 0,
                'failed': 0,
                'skipped': 0
            }
        
        logger.info(f"Found {len(claim_ids)} claims matching filters")
        
        # Push the filtered claims
        result = LiveDatabaseService.push_claims_by_ids(claim_ids)
        
        logger.info(f"Filtered push completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in push_pending_claims_with_filter task: {e}")
        raise


@shared_task(name='apps.live_operations.tasks.cleanup_duplicate_claims')
def cleanup_duplicate_claims():
    """
    Celery task to find and cleanup duplicate claims in the live database
    """
    logger.info("Starting cleanup_duplicate_claims task")
    
    try:
        from django.db import connections
        
        with connections['ereunify'].cursor() as cursor:
            # Find duplicate claim numbers
            cursor.execute("""
                SELECT [No_], COUNT(*) as count
                FROM [UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1]
                GROUP BY [No_]
                HAVING COUNT(*) > 1
            """)
            
            duplicates = cursor.fetchall()
            
            if not duplicates:
                logger.info("No duplicate claims found")
                return {
                    'success': True,
                    'message': 'No duplicate claims found',
                    'duplicates_found': 0,
                    'cleaned': 0
                }
            
            logger.info(f"Found {len(duplicates)} duplicate claim numbers")
            
            cleaned_count = 0
            for claim_no, count in duplicates:
                # Keep the most recent one, delete others
                cursor.execute("""
                    SELECT TOP 1 [No_], [$systemCreatedAt]
                    FROM [UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1]
                    WHERE [No_] = %s
                    ORDER BY [$systemCreatedAt] DESC
                """, [claim_no])
                
                # Delete all but the most recent
                cursor.execute("""
                    DELETE FROM [UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1]
                    WHERE [No_] = %s
                    AND [$systemCreatedAt] < (
                        SELECT MAX([$systemCreatedAt])
                        FROM [UFAA TRUST FUND$Online Claim$2636ffcf-1aea-4b3a-808a-c1da12e824c1]
                        WHERE [No_] = %s
                    )
                """, [claim_no, claim_no])
                
                cleaned_count += cursor.rowcount
                logger.info(f"Cleaned {cursor.rowcount} duplicate entries for claim {claim_no}")
            
            return {
                'success': True,
                'message': f'Cleaned {cleaned_count} duplicate entries',
                'duplicates_found': len(duplicates),
                'cleaned': cleaned_count
            }
            
    except Exception as e:
        logger.error(f"Error in cleanup_duplicate_claims task: {e}")
        raise
