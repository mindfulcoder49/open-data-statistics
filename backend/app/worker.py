from app.main import celery_app as app

# This file is the entry point for the Celery worker.
# The 'app' variable must be defined for Celery to find the application instance.
# To run the worker, you would use the command:
# celery -A app.worker:app worker --loglevel=info --concurrency=1
