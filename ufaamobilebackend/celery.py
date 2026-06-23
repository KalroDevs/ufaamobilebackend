# ufaamobilebackend/celery.py
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ufaamobilebackend.settings')

app = Celery('ufaamobilebackend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Schedule tasks using crontab for more flexibility
app.conf.beat_schedule = {
    # Push claims every 3 hours
    'push-claims-to-live-every-3-hours': {
        'task': 'apps.live_operations.tasks.push_pending_claims_to_live',
        'schedule': crontab(minute=0, hour='*/3'),  # Every 3 hours at minute 0
        'options': {
            'expires': 3600.0,
        }
    },
    # Sync statuses every 6 hours
    'sync-claim-statuses-every-6-hours': {
        'task': 'apps.live_operations.tasks.sync_claim_statuses',
        'schedule': crontab(minute=30, hour='*/6'),  # Every 6 hours at minute 30
        'options': {
            'expires': 3600.0,
        }
    },
}

# Optional: Configure task routing
app.conf.task_routes = {
    'apps.live_operations.tasks.push_pending_claims_to_live': {'queue': 'default'},
    'apps.live_operations.tasks.sync_claim_statuses': {'queue': 'default'},
    'apps.live_operations.tasks.push_claims_by_ids': {'queue': 'default'},
}

# Configure task time limits
app.conf.task_time_limit = 30 * 60  # 30 minutes
app.conf.task_soft_time_limit = 25 * 60  # 25 minutes

if __name__ == '__main__':
    app.start()
