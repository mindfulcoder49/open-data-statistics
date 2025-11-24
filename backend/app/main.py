from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging
import json
import os
import redis.asyncio as aioredis
import uuid
import pandas as pd
from pydantic import BaseModel, Field
import re
import asyncio
import numpy as np
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Dict, Any, Optional, Literal
from celery import Celery
from kombu import Queue
import redis
import requests
from app.config import settings
from core.storage import JsonStorageModel, ImageStorageModel

from stages.stage2_yearly_count_comparison import Stage2YearlyCountComparison
from stages.stage3_univariate_anomaly import Stage3UnivariateAnomaly
from stages.stage4_h3_anomaly import Stage4H3Anomaly

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


# Ensure the results directory exists
os.makedirs(settings.RESULTS_DIR, exist_ok=True)

# --- FastAPI App Initialization ---
app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Directory and Static File Setup ---
# Define paths relative to the /app directory inside the container
STORAGE_DIR = "storage"
UPLOADS_DIR = os.path.join(STORAGE_DIR, "uploads")
TEST_DATA_DIR = os.path.join(STORAGE_DIR, "test_data")
VIEWERS_DIR = "reporting/viewers"

# Create directories if they don't exist
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(TEST_DATA_DIR, exist_ok=True)

# Mount static directories
app.mount("/data", StaticFiles(directory=STORAGE_DIR), name="data")

# --- Redis Connection ---
@app.on_event("startup")
async def startup_event():
    app.state.redis = await aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.redis.close()

# --- JSON Helper ---
def json_safe_default(obj):
    """Helper to serialize non-standard JSON types like numpy integers."""
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


# --- Contents from stages/__init__.py and reporting/__init__.py ---
AVAILABLE_STAGES = {
    "stage2_yearly_count_comparison": Stage2YearlyCountComparison,
    "stage3_univariate_anomaly": Stage3UnivariateAnomaly,
    "stage4_h3_anomaly": Stage4H3Anomaly,
}


# --- Contents from core/pipeline_manager.py ---
class PipelineManager:
    def __init__(self, job_id: str, config: dict, data_sources: list, redis_client=None):
        self.job_id = job_id
        self.config = config
        self.data_sources = data_sources
        self.results = {}
        self.redis_client = redis_client

    def execute(self):
        """
        Executes the full analysis pipeline: loads data, then runs requested stages.
        """
        analysis_stages = self.config.get('analysis_stages', [])
        logger.info(f"[{self.job_id}] Running stages: {analysis_stages}")
        generate_reports_config = self.config.get('generate_reports', {})

        for stage_name in analysis_stages:
            if stage_name not in AVAILABLE_STAGES:
                logger.warning(f"[{self.job_id}] Unknown stage requested: {stage_name}")
                continue

            logger.info(f"[{self.job_id}] Executing stage: {stage_name}")
            stage_class = AVAILABLE_STAGES[stage_name]
            
            # Instantiate every stage consistently, providing all context.
            # Each stage is responsible for its own data loading logic.
            stage_instance = stage_class(
                self.job_id, 
                self.config, 
                results_dir=settings.RESULTS_DIR,
                redis_client=self.redis_client, 
                data_sources=self.data_sources
            )
            
            # The `run` method is called without a DataFrame.
            # Stages that need data will load it themselves.
            stage_result = stage_instance.run()
            
            # For stages that don't save their own results (like Stage 2 & 3), save them now.
            # Stage 4 handles its own streaming save, so this is a no-op for it if the file exists.
            result_filename = f"{stage_name}.json"
            if not os.path.exists(os.path.join(stage_instance.job_dir, result_filename)):
                 stage_instance._save_results(stage_result, result_filename)

            # Add filepath to result for reporter context
            stage_result['__filepath__'] = os.path.join(stage_instance.job_dir, result_filename)

            self.results[stage_name] = stage_result
            logger.info(f"[{self.job_id}] Completed stage: {stage_name}")

            # Generate report if requested
            if generate_reports_config.get(stage_name, False):
                reporter = stage_instance.get_reporter()
                if reporter:
                    logger.info(f"[{self.job_id}] Generating report for stage: {stage_name}")
                    # The DataFrame might need to be re-loaded for reporting if not passed.
                    # For simplicity, we assume the reporter can handle the result dict.
                    # A more advanced implementation might pass the loaded df from the stage.
                    df_for_report = pd.read_csv(self.data_sources[0]['data_url']) if stage_name != 'stage4_h3_anomaly' else None
                    stage_instance.generate_and_save_report(stage_result, df_for_report)
                    logger.info(f"[{self.job_id}] Saved report for stage: {stage_name}")
                else:
                    logger.warning(f"[{self.job_id}] Report requested for '{stage_name}' but no reporter found.")
        
        return self.results


# --- Contents from schemas.py ---
class DataSourceConfig(BaseModel):
    data_url: str
    timestamp_col: str
    lat_col: str
    lon_col: str
    secondary_group_col: str

class StageParameters(BaseModel):
    h3_resolution: int = 8
    min_trend_events: int = 4
    filter_col: Optional[str] = None
    filter_values: Optional[List[str]] = None
    analysis_weeks_trend: List[int] = Field([4], description="List of recent week counts to use for trend detection (e.g., [4, 8, 12]).")
    analysis_weeks_anomaly: int = Field(4, description="Number of recent weeks to use for anomaly detection.")
    p_value_anomaly: float = 0.05
    p_value_trend: float = 0.05
    plot_generation: Literal["both", "trends", "anomalies", "none"] = Field("both", description="Control plot generation: 'both', 'trends' only, 'anomalies' only, or 'none'.")
    save_full_series: bool = Field(False, description="If true, saves the full weekly time series data for each group in the final JSON result.")
    # General parameters that might be needed by stages running on a pre-loaded DataFrame
    timestamp_col: Optional[str] = Field(None, description="Timestamp column for analysis (if not taken from data_sources).")
    primary_group_col: Optional[str] = Field(None, description="Primary grouping column for analysis.")
    secondary_group_col: Optional[str] = Field(None, description="Secondary grouping column for analysis.")
    # Stage 2 Parameters
    group_by_col: Optional[str] = Field(None, description="Column to group data by for yearly count comparison.")
    baseline_year: Optional[int] = Field(None, description="Baseline year for comparison (e.g., 2019 for pre-pandemic).")

class JobConfig(BaseModel):
    analysis_stages: List[str]
    parameters: Dict[str, StageParameters]

class JobCreateRequest(BaseModel):
    job_id: str
    data_sources: List[DataSourceConfig]
    config: JobConfig

class JobCreateResponse(BaseModel):
    job_id: str
    status_url: str
    results_url: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    current_stage: Optional[str] = None
    error_message: Optional[str] = None
    progress: Optional[int] = None
    stage_detail: Optional[str] = None

class FilePreviewRequest(BaseModel):
    file_path: str

class UniqueValuesRequest(BaseModel):
    file_path: str
    column_name: str

class CompletionRequest(BaseModel):
    job_id: str
    prompt: str
    model: str = "llama3"

# --- Contents from tasks.py ---
# Initialize Celery
# Use CELERY_BROKER_URL if provided, otherwise fall back to REDIS_URL.
# This allows the worker to connect from a different network.
broker_url = settings.CELERY_BROKER_URL or settings.REDIS_URL
celery_app = Celery('tasks', broker=broker_url, backend=broker_url)

# Define queues
celery_app.conf.task_queues = (
    Queue('celery'),  # Default queue for analysis tasks
    Queue('completions'),  # Dedicated queue for AI completions
)
celery_app.conf.task_default_queue = 'celery'

celery_app.conf.update(
    task_track_started=True,
)

# Initialize a Redis client for custom status updates
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
@celery_app.task(bind=True)
def run_analysis_pipeline(self, job_id: str, data_sources: list, config: dict):
    """
    Celery task to run the full analysis pipeline using PipelineManager.
    """
    try:
        # Set initial status in Redis
        status = {"status": "processing", "current_stage": "initializing", "progress": 0, "stage_detail": "Starting job..."}
        redis_client.set(f"job_status:{job_id}", json.dumps(status))

        logger.info(f"[{job_id}] Starting pipeline execution.")
        manager = PipelineManager(job_id=job_id, config=config, data_sources=data_sources, redis_client=redis_client)
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
        # Re-raise the exception so Celery knows the task failed
        raise

@celery_app.task(bind=True, name="tasks.process_completion_request")
def process_completion_request(self, job_id: str, prompt: str, model: str):
    """
    Celery task to process a completion request using a local Ollama service.
    """
    json_storage = JsonStorageModel()
    try:
        status = {"status": "processing", "stage": "starting"}
        redis_client.set(f"job_status:{job_id}", json.dumps(status))

        logger.info(f"[{job_id}] Sending prompt to Ollama model {model} at {settings.OLLAMA_URL}")
        
        ollama_payload = {
            "model": model,
            "prompt": prompt,
            "stream": False  # We want the full response at once
        }
        # Add a timeout to the request (e.g., 5 minutes)
        response = requests.post(f"{settings.OLLAMA_URL}/api/generate", json=ollama_payload, timeout=300)
        response.raise_for_status()
        
        ollama_result = response.json()
        
        final_status = {
            "status": "completed",
            "response": ollama_result.get("response"),
            "context": ollama_result.get("context")
        }
        
        # Save the result to a JSON file
        json_storage.save(job_id, "completion.json", final_status)
        
        redis_client.set(f"job_status:{job_id}", json.dumps({"status": "completed"}))
        logger.info(f"[{job_id}] Ollama completion successful and saved.")
        return final_status

    except requests.exceptions.HTTPError as e:
        logger.error(f"[{job_id}] HTTP error connecting to Ollama: {e}", exc_info=True)
        error_message = f"Ollama service returned an error: {e}. Check if the Ollama server is running and the model '{model}' is available."
        if e.response.status_code == 404:
            error_message += " A 404 error suggests the Ollama API endpoint was not found. Check your OLLAMA_URL and any proxy settings."
        error_status = {"status": "failed", "error_message": error_message}
        redis_client.set(f"job_status:{job_id}", json.dumps(error_status))
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"[{job_id}] Failed to connect to Ollama: {e}", exc_info=True)
        error_status = {"status": "failed", "error_message": f"Could not connect to Ollama service at {settings.OLLAMA_URL}. Is it running and accessible? Error: {e}"}
        redis_client.set(f"job_status:{job_id}", json.dumps(error_status))
        raise
    except Exception as e:
        logger.error(f"[{job_id}] Completion task failed: {e}", exc_info=True)
        error_status = {"status": "failed", "error_message": str(e)}
        redis_client.set(f"job_status:{job_id}", json.dumps(error_status))
        raise

@celery_app.task(name="tasks.get_available_models")
def get_available_models():
    """
    Celery task to be executed by the completions worker to fetch models from Ollama.
    """
    try:
        logger.info(f"Task 'get_available_models' fetching from {settings.OLLAMA_URL}")
        response = requests.get(f"{settings.OLLAMA_URL}/api/tags", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Task 'get_available_models' failed to connect to Ollama: {e}")
        # Celery will propagate this exception to the caller waiting on the result.
        raise

# --- API Endpoints ---

@app.get("/api/v1/data/list")
async def list_data_files():
    """Lists available CSV files from the test_data and uploads directories."""
    response = {"test_data": [], "uploads": []}
    
    # List files in test_data
    for filename in os.listdir(TEST_DATA_DIR):
        if filename.endswith('.csv'):
            response["test_data"].append(f"/data/test_data/{filename}")

    # List files in uploads
    for filename in os.listdir(UPLOADS_DIR):
        if filename.endswith('.csv'):
            response["uploads"].append(f"/data/uploads/{filename}")
            
    return response

@app.post("/api/v1/data/preview")
async def preview_data_file(preview_request: FilePreviewRequest):
    """Returns the headers and first 5 rows of a given CSV file."""
    # The file_path is relative to the web root, e.g., /data/uploads/file.csv
    # We need to map it to the local filesystem path, e.g., storage/uploads/file.csv
    if not preview_request.file_path.startswith('/data/'):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    
    local_path = os.path.join("storage", preview_request.file_path.replace('/data/', '', 1))

    if not os.path.exists(local_path):
        raise HTTPException(status_code=404, detail="File not found on server.")

    try:
        df = pd.read_csv(local_path, nrows=5)
        # Use pandas' to_json which handles NaN/NaT correctly by converting to null.
        # Then load it back into a Python object for FastAPI to re-serialize.
        json_str = df.to_json(orient='records', date_format='iso')
        rows = json.loads(json_str)
        headers = df.columns.tolist()
        return {"headers": headers, "rows": rows}
    except Exception as e:
        logger.error(f"Failed to preview file {local_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not read or parse file: {e}")

@app.post("/api/v1/data/unique-values")
async def get_unique_column_values(request: UniqueValuesRequest):
    """Returns the unique values for a given column in a CSV file."""
    if not request.file_path.startswith('/data/'):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    
    local_path = os.path.join("storage", request.file_path.replace('/data/', '', 1))

    if not os.path.exists(local_path):
        raise HTTPException(status_code=404, detail="File not found on server.")

    try:
        df = pd.read_csv(local_path, usecols=[request.column_name])
        unique_values = df[request.column_name].dropna().unique().tolist()
        # Sort if possible, handle mixed types by converting to string
        try:
            unique_values.sort()
        except TypeError:
            unique_values.sort(key=str)
        return {"unique_values": unique_values}
    except Exception as e:
        logger.error(f"Failed to get unique values for {request.column_name} in {local_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not read file or find column: {e}")

@app.post("/api/v1/data/upload")
async def upload_data_file(request: Request, file: UploadFile = File(...)):
    """
    Accepts a CSV file upload, saves it, and returns its accessible URL.
    """
    # Sanitize original filename and append a UUID for uniqueness
    original_name, original_ext = os.path.splitext(file.filename)
    
    # Sanitize: remove invalid chars, replace spaces with underscores
    sanitized_name = re.sub(r'[\\/*?:"<>|]', "", original_name)
    sanitized_name = re.sub(r'\s+', '_', sanitized_name).strip('_')

    unique_filename = f"{sanitized_name}_{uuid.uuid4()}{original_ext}"
    file_path = os.path.join(UPLOADS_DIR, unique_filename)

    try:
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(status_code=500, detail="Could not save file.")

    # Return a relative path that the client can use to construct a full URL
    relative_path = f"/data/uploads/{unique_filename}"
    
    return {"file_path": relative_path}

@app.post("/api/v1/completions", response_model=JobCreateResponse, status_code=202)
async def create_completion_job(request_data: CompletionRequest, request: Request):
    """
    Accepts a completion job, validates it, and queues it for the 'completions' worker.
    """
    job_id = request_data.job_id
    logger.info(f"Received completion job request: {job_id}")

    # Dispatch the task to the 'completions' queue
    task = process_completion_request.apply_async(
        args=[job_id, request_data.prompt, request_data.model],
        queue='completions'
    )

    # Store initial status in Redis
    initial_status = {
        "status": "queued",
        "task_id": task.id,
        "request_payload": request_data.dict()
    }
    await app.state.redis.set(f"job_status:{job_id}", json.dumps(initial_status))

    base_url = str(request.base_url)
    return JobCreateResponse(
        job_id=job_id,
        status_url=f"{base_url}api/v1/jobs/{job_id}/status",
        results_url=f"{base_url}api/v1/jobs/{job_id}/results"
    )

@app.get("/api/v1/completions/models")
async def get_ollama_models():
    """
    Fetches the list of available models by dispatching a task to the completions worker.
    """
    try:
        # This is a blocking call. We wait for the worker to respond.
        # A timeout is crucial to prevent the API from hanging if the worker is down.
        async_result = get_available_models.apply_async(queue='completions')
        result = async_result.get(timeout=15) 
        return result
    except Exception as e:
        logger.error(f"Could not get models from completions worker: {e}", exc_info=True)
        raise HTTPException(
            status_code=502, 
            detail="Could not retrieve models from the completions worker. It may be offline or unable to connect to Ollama."
        )

# --- Admin Endpoints ---

@app.get("/api/v1/admin/jobs")
async def admin_list_jobs():
    """(Admin) Lists all jobs found in Redis."""
    try:
        job_keys = await app.state.redis.keys("job_status:*")
        jobs = []
        for key in job_keys:
            job_id = key.split(":")[-1]
            data = await app.state.redis.get(key)
            jobs.append({"job_id": job_id, "data": json.loads(data)})
        
        # Serialize the content to a JSON string using the custom default function
        json_content = json.dumps(jobs, default=json_safe_default)
        return Response(content=json_content, media_type="application/json")
    except Exception as e:
        logger.error(f"Admin failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve jobs from Redis.")

@app.get("/api/v1/admin/queue-status")
async def admin_get_queue_status():
    """(Admin) Gets the status of Celery queues (queued, active, reserved)."""
    try:
        # 1. Get queued tasks from Redis (non-blocking)
        queued_tasks_raw = await app.state.redis.lrange("celery", 0, -1)
        queued_tasks = [json.loads(task) for task in queued_tasks_raw]

        # 2. Get active and reserved tasks from workers (blocking, run in executor)
        def get_worker_tasks():
            inspector = celery_app.control.inspect()
            return {
                "active": inspector.active(),
                "reserved": inspector.reserved(),
                "scheduled": inspector.scheduled()
            }

        # In Python 3.9+, asyncio.to_thread is preferred.
        # For broader compatibility, we can use run_in_executor.
        loop = asyncio.get_running_loop()
        worker_tasks = await loop.run_in_executor(None, get_worker_tasks)

        return {
            "queued_tasks": queued_tasks,
            "active_tasks": worker_tasks.get("active"),
            "reserved_tasks": worker_tasks.get("reserved"),
            "scheduled_tasks": worker_tasks.get("scheduled")
        }
    except Exception as e:
        logger.error(f"Admin failed to get queue status: {e}", exc_info=True)
        # Return partial data if possible, or a full error
        error_content = {"error": "Could not retrieve all queue statuses.", "detail": str(e)}
        json_content = json.dumps(error_content, default=json_safe_default)
        return Response(content=json_content, status_code=500, media_type="application/json")

@app.delete("/api/v1/admin/jobs/{job_id}")
async def admin_delete_job(job_id: str):
    """(Admin) Deletes a job's status from Redis and attempts to revoke the task."""
    # First, get the task_id from the status data before deleting
    status_data = await app.state.redis.get(f"job_status:{job_id}")
    
    if status_data:
        try:
            status_dict = json.loads(status_data)
            task_id = status_dict.get("task_id")
            if task_id:
                logger.info(f"Admin request to revoke task {task_id} for job {job_id}.")
                # Revoke the task. terminate=True attempts to kill the worker process if the task is running.
                celery_app.control.revoke(task_id, terminate=True)
        except Exception as e:
            # Log the error but proceed with deletion, as the primary goal is to remove the job from view.
            logger.error(f"Failed to revoke Celery task for job {job_id}: {e}")

    # Now, delete the job status key from Redis
    deleted_count = await app.state.redis.delete(f"job_status:{job_id}")
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Job not found in Redis.")
    
    return {"message": f"Job {job_id} deleted and task revocation attempted."}

@app.put("/api/v1/admin/jobs/{job_id}")
async def admin_update_job(job_id: str, request: Request):
    """(Admin) Updates a job's raw status data in Redis."""
    try:
        new_data = await request.json()
        await app.state.redis.set(f"job_status:{job_id}", json.dumps(new_data))
        return {"message": f"Job {job_id} updated successfully."}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in request body.")
    except Exception as e:
        logger.error(f"Admin failed to update job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not update job in Redis.")

# --- End Admin Endpoints ---

@app.post("/api/v1/jobs", response_model=JobCreateResponse, status_code=202)
async def create_job(request_data: JobCreateRequest, request: Request):
    """
    Accepts an analysis job request, validates it, and queues it for background processing.
    """
    job_id = request_data.job_id
    logger.info(f"Received job request: {job_id} with {len(request_data.data_sources)} data sources.")

    # The data_url from the client will be based on the public-facing hostname
    # (e.g., http://localhost:8080). We need to replace this with the internal
    # hostname so the Celery worker can access the data.
    public_base_url = str(request.base_url)
    
    # Create a mutable copy of the config to modify URLs
    config_dict = request_data.config.dict()
    data_sources_list = [ds.dict() for ds in request_data.data_sources]

    if "localhost" in public_base_url or "127.0.0.1" in public_base_url:
        for source in data_sources_list:
            source['data_url'] = str(source['data_url']).replace(
                public_base_url.strip('/'), 
                settings.INTERNAL_API_HOSTNAME.strip('/')
            )
            logger.info(f"Rewrote data URL for worker: {source['data_url']}")

    # Dispatch the task to Celery
    task = run_analysis_pipeline.delay(
        job_id=job_id,
        data_sources=data_sources_list,
        config=config_dict
    )

    # Store initial status in Redis, including the original request for admin view
    initial_status = {
        "status": "queued",
        "task_id": task.id,
        "request_payload": request_data.dict()
    }
    await app.state.redis.set(f"job_status:{job_id}", json.dumps(initial_status))

    base_url = str(request.base_url)
    return JobCreateResponse(
        job_id=job_id,
        status_url=f"{base_url}api/v1/jobs/{job_id}/status",
        results_url=f"{base_url}api/v1/jobs/{job_id}/results"
    )

@app.get("/api/v1/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Retrieves the current status of a processing job.
    """
    status_data = await app.state.redis.get(f"job_status:{job_id}")
    if not status_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    status_dict = json.loads(status_data)
    # Ensure the response matches the Pydantic model
    return JobStatusResponse(
        job_id=job_id,
        status=status_dict.get("status"),
        current_stage=status_dict.get("current_stage"),
        error_message=status_dict.get("error_message"),
        progress=status_dict.get("progress"),
        stage_detail=status_dict.get("stage_detail")
    )

@app.get("/api/v1/jobs/{job_id}/results")
async def get_job_results_list(job_id: str, request: Request):
    """
    Lists the available result artifacts for a completed job.
    """
    status_data = await app.state.redis.get(f"job_status:{job_id}")
    if not status_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    status = json.loads(status_data)
    if status.get("status") != "completed":
        raise HTTPException(status_code=400, detail=f"Job is not complete. Current status: {status.get('status')}")

    json_storage = JsonStorageModel()
    files = json_storage.list_artifacts(job_id)
    
    base_url = str(request.base_url)
    results_urls = {}
    
    for f in files:
        # Add URLs for raw artifacts
        results_urls[os.path.splitext(f)[0]] = f"{base_url}api/v1/jobs/{job_id}/results/{f}"
        
        # Add special URLs for viewers
        if f == "stage4_h3_anomaly.json":
            results_urls["stage4_h3_anomaly_viewer"] = f"{base_url}reports/view/stage4?job_id={job_id}"

    return {"job_id": job_id, "status": "completed", "results": results_urls}


@app.get("/api/v1/jobs/{job_id}/results/stage4_h3_anomaly/summary")
async def get_stage4_summary_result(job_id: str):
    """
    Retrieves the Stage 4 H3 anomaly results but excludes the bulky 'weekly_series' data
    for a more lightweight summary.
    """
    artifact_name = "stage4_h3_anomaly.json"
    artifact_path = os.path.join(settings.RESULTS_DIR, job_id, artifact_name)

    if not os.path.exists(artifact_path):
        raise HTTPException(status_code=404, detail="Stage 4 result artifact not found.")

    try:
        with open(artifact_path, 'r') as f:
            data = json.load(f)

        # Remove the weekly_series from each result for a summary view
        if "results" in data and isinstance(data["results"], list):
            for result_item in data["results"]:
                if "full_weekly_series" in result_item:
                    del result_item["full_weekly_series"]
        
        # Also remove from city_wide_results if it exists
        if "city_wide_results" in data and isinstance(data["city_wide_results"], list):
             for result_item in data["city_wide_results"]:
                if "full_weekly_series" in result_item:
                    del result_item["full_weekly_series"]

        return data
    except Exception as e:
        logger.error(f"Failed to generate summary for {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not process result file for summary.")


@app.get("/api/v1/jobs/{job_id}/results/{artifact_name}")
async def get_job_result_artifact(job_id: str, artifact_name: str):
    """
    Retrieves a specific result artifact file for a job.
    """
    if artifact_name.lower().endswith('.png'):
        storage = ImageStorageModel()
    else:
        storage = JsonStorageModel()

    if not storage.exists(job_id, artifact_name):
        raise HTTPException(status_code=404, detail="Artifact not found")

    response = storage.get_response(job_id, artifact_name)
    if not response:
        raise HTTPException(status_code=500, detail="Could not retrieve file.")
    
    return response

# --- Frontend Serving Endpoints ---

@app.get("/", response_class=FileResponse)
async def serve_index():
    """Serves the main job submission page."""
    viewer_path = os.path.join(VIEWERS_DIR, "index.html")
    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail="index.html not found.")
    return FileResponse(viewer_path)

@app.get("/admin", response_class=FileResponse)
async def serve_admin_page():
    """Serves the admin dashboard."""
    viewer_path = os.path.join(VIEWERS_DIR, "admin.html")
    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail="admin.html not found.")
    return FileResponse(viewer_path)

@app.get("/reports/view/stage2", response_class=FileResponse)
async def serve_stage2_viewer():
    """Serves the generic HTML viewer for Stage 2 results."""
    viewer_path = os.path.join(VIEWERS_DIR, "stage2_viewer.html")
    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail="Stage 2 viewer not found.")
    return FileResponse(viewer_path)

@app.get("/reports/view/stage4", response_class=FileResponse)
async def serve_stage4_viewer():
    """Serves the generic HTML viewer for Stage 4 results."""
    viewer_path = os.path.join(VIEWERS_DIR, "stage4_viewer.html")
    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail="Stage 4 viewer not found.")
    return FileResponse(viewer_path)

@app.get("/completions", response_class=FileResponse)
async def serve_completions_page():
    """Serves the completions chat interface."""
    viewer_path = os.path.join(VIEWERS_DIR, "completions.html")
    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail="completions.html not found.")
    return FileResponse(viewer_path)
