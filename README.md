# Open Data Statistical Analytics Service

A FastAPI application designed to provide a robust, asynchronous API for offloading complex statistical and machine learning analyses. It uses Celery and Redis to manage long-running analysis jobs in the background.

## Features

- **Asynchronous Job Processing:** Uses Celery and Redis to handle long-running tasks without blocking the API.
- **Modular Pipeline Architecture:** Easily extend the service with new analysis "stages".
- **Dockerized:** Fully containerized for easy setup and deployment.
- **Self-Contained Testing:** Includes a static file server to host its own test data.

## Prerequisites

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/) (usually included with Docker Desktop)

## Getting Started

### 1. Build and Run the Services

From the project's root directory (`open-data-statistics`), run the following command:

```bash
docker-compose -f docker-compose.dev.yml up --build
```

This will build the Docker images and start three services:
- `backend`: The FastAPI web server running on `http://localhost:8080`.
- `worker`: The Celery worker that processes analysis jobs.
- `redis`: The message broker and results backend for Celery.

## API Usage

You can interact with the service using any HTTP client, such as `curl`.

### 1. Submit an Analysis Job

To start a new analysis, send a `POST` request to the `/api/v1/jobs` endpoint.

The `data_url` in the payload must point to a location accessible by the **Celery worker container**. Since the `backend` service hosts the test data, we use the internal Docker network URL `http://backend:8080/...` instead of `http://localhost:8080/...`.

```bash
curl -X POST http://localhost:8080/api/v1/jobs \
-H "Content-Type: application/json" \
-d '{
  "job_id": "my-first-test-job",
  "data_url": "http://backend:8080/data/test_data/sample_incidents.csv",
  "config": {
    "timestamp_col": "timestamp",
    "lat_col": "lat",
    "lon_col": "lon",
    "analysis_stages": ["stage4_explain"],
    "parameters": {
      "stage4_explain": {
        "features_to_include": ["is_weekend", "day_of_week"]
      }
    }
  }
}'
```

You should receive a `202 Accepted` response with URLs to check the status and retrieve results:

```json
{
  "job_id": "my-first-test-job",
  "status": "queued",
  "message": "Analysis job accepted and queued for processing.",
  "status_url": "http://localhost:8080/api/v1/jobs/my-first-test-job/status",
  "results_url": "http://localhost:8080/api/v1/jobs/my-first-test-job/results"
}
```

### 2. Check Job Status

Use the `status_url` from the previous response to poll for the job's status. The status will transition from `queued` to `processing` and finally to `completed` or `failed`.

```bash
curl http://localhost:8080/api/v1/jobs/my-first-test-job/status
```

### 3. Retrieve Results

Once the job status is `completed`, you can get a list of available result files from the `results_url`.

```bash
curl http://localhost:8080/api/v1/jobs/my-first-test-job/results
```

This will return a list of artifacts. You can then download a specific artifact using its URL.

```bash
# Example URL from the previous response
curl http://localhost:8080/api/v1/jobs/my-first-test-job/results/stage4_explain.json
```
