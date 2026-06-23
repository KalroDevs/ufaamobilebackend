# apps/live_operations/management/commands/trigger_push_to_live.py
from django.core.management.base import BaseCommand
from apps.live_operations.tasks import push_pending_claims_to_live
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Trigger Celery task to push claims to live database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--async',
            action='store_true',
            help='Run asynchronously using Celery'
        )
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Run synchronously (directly)'
        )

    def handle(self, *args, **options):
        if options.get('async'):
            self.stdout.write("Triggering Celery task asynchronously...")
            result = push_pending_claims_to_live.delay()
            self.stdout.write(f"Task ID: {result.id}")
            self.stdout.write("Task scheduled. Check Celery worker logs for progress.")
            
        elif options.get('sync'):
            self.stdout.write("Running task synchronously...")
            result = push_pending_claims_to_live()
            self.stdout.write(f"Result: {result}")
            
        else:
            self.stdout.write("Please specify --async or --sync")
