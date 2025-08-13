import pandas as pd
from celery import Celery
import redis
import json
import logging

from app.config import settings
from core.pipeline_manager import PipelineManager

logger = logging.getLogger(__name__)

# Initialize Celery
app = Celery('tasks', broker=settings.REDIS_URL, backend=settings.REDIS_URL)
app.conf.update(
    task_track_started=True,
)

# Initialize a Redis client for custom status updates
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

@app.task(bind=True)
def run_analysis_pipeline(self, job_id: str, data_url: str, config: dict):
    """
    Celery task to run the full analysis pipeline using PipelineManager.
    """
    try:
        # Set initial status in Redis
        status = {"status": "processing", "current_stage": "initializing", "progress": 0, "stage_detail": "Starting job..."}
        redis_client.set(f"job_status:{job_id}", json.dumps(status))

        logger.info(f"[{job_id}] Starting pipeline execution.")
        manager = PipelineManager(job_id=job_id, config=config, data_url=data_url, redis_client=redis_client)
        results = manager.execute()

        # Set final status. Crucially, we do NOT store the full results in Redis.
        # The results are on disk and will be served by the API endpoints.
        final_status = {"status": "completed"}
        redis_client.set(f"job_status:{job_id}", json.dumps(final_status))
        logger.info(f"[{job_id}] Processing complete.")
        return final_status

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline failed: {e}", exc_info=True)
        error_status = {"status": "failed", "error_message": str(e)}
        redis_client.set(f"job_status:{job_id}", json.dumps(error_status))
        # Re-raise the exception to have Celery mark the task as FAILED
        raise
