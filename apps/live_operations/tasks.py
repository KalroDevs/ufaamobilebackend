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
        
        logger.info(f"Single push completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in push_single_claim_to_live task: {e}")
        raise


@shared_task(name='apps.live_operations.tasks.push_claims_by_ids')
def push_claims_by_ids(claim_ids):
    """
    Celery task to push specific claims by IDs
    
    Args:
        claim_ids: List of claim IDs to push
    """
    logger.info(f"Starting task: push_claims_by_ids for {len(claim_ids)} claims")
    
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
        
        live_claims = LiveOnlineClaim.objects.all()
        synced_count = 0
        failed_count = 0
        
        for live_claim in live_claims:
            try:
                # Find matching claim in default database
                claim = Claim.objects.filter(no=live_claim.claim_no).first()
                
                if claim and claim.status != live_claim.status:
                    # Sync status
                    result = LiveDatabaseService.sync_claim_status(
                        live_claim.claim_no, 
                        live_claim.status
                    )
                    
                    if result.get('success'):
                        synced_count += 1
                        logger.info(f"Synced claim {live_claim.claim_no} status to {live_claim.status}")
                    else:
                        failed_count += 1
                        logger.error(f"Failed to sync claim {live_claim.claim_no}: {result.get('message')}")
                        
            except Exception as e:
                failed_count += 1
                logger.error(f"Error syncing claim {live_claim.claim_no}: {e}")
        
        result = {
            'success': True,
            'synced': synced_count,
            'failed': failed_count,
            'message': f'Synced {synced_count} claims, {failed_count} failed'
        }
        
        logger.info(f"Sync task completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in sync_claim_statuses task: {e}")
        raise


@shared_task(name='apps.live_operations.tasks.push_pending_claims_with_filter')
def push_pending_claims_with_filter(status_filter=None, days_old=None):
    """
    Celery task to push pending claims with filters
    
    Args:
        status_filter: List of statuses to filter (e.g., ['Pending', 'Under_Review'])
        days_old: Only push claims older than X days
    """
    logger.info(f"Starting filtered push task with status_filter={status_filter}, days_old={days_old}")
    
    try:
        claims = Claim.objects.filter(status__in=['Pending', 'Under_Review'])
        
        # Apply status filter if provided
        if status_filter:
            claims = claims.filter(status__in=status_filter)
        
        # Apply days filter if provided
        if days_old:
            cutoff_date = timezone.now() - timedelta(days=days_old)
            claims = claims.filter(created_at__lte=cutoff_date)
        
        claim_ids = list(claims.values_list('id', flat=True))
        
        if not claim_ids:
            return {
                'success': True,
                'message': 'No claims found matching the filters',
                'pushed': 0,
                'failed': 0
            }
        
        # Push the filtered claims
        result = LiveDatabaseService.push_claims_by_ids(claim_ids)
        
        logger.info(f"Filtered push completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in push_pending_claims_with_filter task: {e}")
        raise
