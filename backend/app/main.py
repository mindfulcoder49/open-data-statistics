from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging
import json
import os
import redis.asyncio as aioredis

from app.schemas import JobCreateRequest, JobCreateResponse, JobStatusResponse
from app.tasks import run_analysis_pipeline
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

@app.on_event("startup")
async def startup_event():
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.redis.close()

@app.post("/api/v1/jobs", response_model=JobCreateResponse, status_code=202)
async def create_job(request_data: JobCreateRequest, request: Request):
    """
    Accepts an analysis job request, validates it, and queues it for background processing.
    """
    job_id = request_data.job_id
    logger.info(f"Received job request: {job_id}")

    # Dispatch the task to Celery
    task = run_analysis_pipeline.delay(
        job_id=job_id,
        data_url=str(request_data.data_url),
        config=request_data.config.dict()
    )

    # Store initial status in Redis
    initial_status = {"status": "queued", "task_id": task.id}
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
        error_message=status_dict.get("error_message")
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




