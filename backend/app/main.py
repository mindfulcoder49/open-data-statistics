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
from pydantic import BaseModel
import re
import asyncio
import numpy as np

from app.schemas import JobCreateRequest, JobCreateResponse, JobStatusResponse
from app.tasks import run_analysis_pipeline, app as celery_app
from app.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Ladder Analytics Service",
    description="An API for running statistical analysis pipelines.",
    version="1.0.0"
)

def json_safe_default(obj):
    """
    A default JSON serializer for objects that are not directly serializable.
    This is especially useful for NumPy types.
    """
    if isinstance(obj, (np.integer, np.int64)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# Mount static files directory to serve test data
# This makes files in the 'storage' directory available under the /data path
# e.g., /data/test_data/sample_incidents.csv
app.mount("/data", StaticFiles(directory="storage"), name="data")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VIEWERS_DIR = os.path.join(os.path.dirname(__file__), "..", "reporting", "viewers")
UPLOADS_DIR = os.path.join("storage", "uploads")
TEST_DATA_DIR = os.path.join("storage", "test_data")

class FilePreviewRequest(BaseModel):
    file_path: str

class UniqueValuesRequest(BaseModel):
    file_path: str
    column_name: str

@app.on_event("startup")
async def startup_event():
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    # Ensure the uploads directory exists
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(TEST_DATA_DIR, exist_ok=True)

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.redis.close()

@app.get("/", response_class=FileResponse)
async def read_index():
    """Serves the main index.html file."""
    index_path = os.path.join(VIEWERS_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)

@app.get("/admin", response_class=FileResponse)
async def read_admin_index():
    """Serves the admin dashboard file."""
    admin_path = os.path.join(VIEWERS_DIR, "admin.html")
    if not os.path.exists(admin_path):
        raise HTTPException(status_code=404, detail="admin.html not found")
    return FileResponse(admin_path)

@app.get("/api/v1/data/files")
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

    #for source in data_sources_list:
    #    source['data_url'] = str(source['data_url']).replace(
    #        public_base_url.strip('/'), 
    #        settings.INTERNAL_API_HOSTNAME.strip('/')
    #    )
    #    logger.info(f"Rewrote data URL for worker: {source['data_url']}")

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

    job_dir = os.path.join(settings.RESULTS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return {"job_id": job_id, "results": {}}

    files = os.listdir(job_dir)
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
    artifact_path = os.path.join(settings.RESULTS_DIR, job_id, artifact_name)

    if not os.path.exists(artifact_path):
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Determine content type for images
    media_type = None
    if artifact_name.lower().endswith('.png'):
        media_type = 'image/png'
    elif artifact_name.lower().endswith('.json'):
        media_type = 'application/json'
    
    return FileResponse(artifact_path, media_type=media_type)

@app.get("/reports/view/stage4", response_class=FileResponse)
async def serve_stage4_viewer():
    """Serves the generic HTML viewer for Stage 4 results."""
    viewer_path = os.path.join(VIEWERS_DIR, "stage4_viewer.html")
    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail="Stage 4 viewer not found.")
    return FileResponse(viewer_path)
