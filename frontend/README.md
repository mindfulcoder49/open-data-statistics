# Ladder Analytics Frontend

This directory contains the React-based frontend for the Ladder Analytics job submission and monitoring service.

## Prerequisites

-   [Node.js](https://nodejs.org/) (v16 or later recommended)
-   [npm](https://www.npmjs.com/) (usually comes with Node.js)

## Installation

1.  **Navigate to the frontend directory:**

    ```bash
    cd /path/to/open-data-statistics/frontend
    ```

2.  **Install dependencies:**

    This command reads the `package.json` file and installs all the required libraries (like React, etc.) into the `node_modules` directory.

    ```bash
    npm install
    ```

## Running the Development Server

To run the application in development mode, use the following command:

```bash
npm start
```

This will:
-   Start a local development server, usually at `http://localhost:3000`.
-   Open the application in your default web browser.
-   Automatically reload the page whenever you make changes to the source code.

The development server will proxy API requests to the backend service running at `http://localhost:8000` (as configured in `package.json`). **Ensure the Python backend is running for the frontend to function correctly.**

## Building for Production

To create an optimized production build of the application, run:

```bash
npm run build
```

This command bundles the application into static files and places them in the `frontend/build` directory. The Python backend is configured to serve these files when running in a production environment.

## Distributed Development (Remote Worker)

It is possible to run the `backend` and `redis` services on a remote server while running the Celery `worker` on your local machine. This is useful for offloading heavy processing tasks from the server.

**Prerequisites:**
- A remote server with Docker and a public domain name (e.g., `lotusfiremeditation.org`).
- Your local machine with the project code and Docker installed.
- S3 storage is **required**, as both the remote backend and local worker need access to the same storage artifacts.

### On the Remote Server

1.  **Configure `.env` file**:
    -   Create or edit the `.env` file in the project root.
    -   Set a strong `REDIS_PASSWORD`.
    -   Set `STORAGE_TYPE=s3` and provide your S3 bucket details and AWS credentials.
    -   Set `CELERY_BROKER_URL` to your public Redis URL, including the password (e.g., `redis://:your-password@lotusfiremeditation.org:6379/0`).
    -   Set `INTERNAL_API_HOSTNAME` to your public backend URL (e.g., `http://lotusfiremeditation.org:8080`).

2.  **Launch Services**:
    -   Use the `docker-compose.server.yml` file to start the `redis` and `backend` containers.

    ```bash
    sudo docker-compose -f docker-compose.server.yml up --build -d
    ```

### On Your Local Machine

This setup now involves two potential types of workers: one for data analysis and one for AI completions.

1.  **Configure `.env` file**:
    -   Create or edit the `.env` file in your local project root.
    -   Set the `REDIS_PASSWORD` to match the server.
    -   Set `STORAGE_TYPE=s3` with the same S3/AWS configuration as the server.
    -   Set `REDIS_URL` to your public Redis URL, including the password.
    -   Set `INTERNAL_API_HOSTNAME` to your public backend URL.
    -   Set `OLLAMA_URL` to point to your local Ollama service (e.g., `http://host.docker.internal:11434`).

2.  **Launch the Analysis Worker**:
    -   To process standard data analysis jobs, use the `docker-compose.analysis-worker.yml` file.
    ```bash
    docker-compose -f docker-compose.analysis-worker.yml up --build
    ```

3.  **Launch the Completions Worker**:
    -   To process AI completion jobs from the Laravel app, use the `docker-compose.completions-worker.yml` file. Ensure your local Ollama service is running.
    ```bash
    docker-compose -f docker-compose.completions-worker.yml up --build
    ```

The workers will connect to the Redis instance on your server and start processing tasks from their respective queues.

### Testing the Distributed Setup Locally

You can simulate the server/worker split on your local machine to test the distributed configuration. This involves running the server components and the worker component in separate terminals.

1.  **Configure `.env` file for Local Testing**:
    -   Edit the `.env` file in your project root.
    -   Set a `REDIS_PASSWORD`.
    -   Set `STORAGE_TYPE=s3` and provide your S3 credentials.
    -   Point the URLs to `host.docker.internal`. This allows standard containers (like the analysis worker) to reach services on your host. The completions worker, which uses host networking, will override these values internally.
        ```properties
        REDIS_PASSWORD=your-secure-password
        REDIS_URL=redis://:your-secure-password@host.docker.internal:6379/0
        CELERY_BROKER_URL=redis://:your-secure-password@host.docker.internal:6379/0
        INTERNAL_API_HOSTNAME=http://host.docker.internal:8030
        OLLAMA_URL=http://host.docker.internal:11434
        ```

2.  **Launch Server Components**:
    -   In your **first terminal**, run `docker-compose.server.yml`. This will start the `redis` and `backend` services and make them available on your host machine's ports.
    ```bash
    docker-compose -f docker-compose.server.yml up --build
    ```

3.  **Launch the Workers**:
    -   In a **second terminal**, run `docker-compose.analysis-worker.yml` to start the worker for analysis jobs.
    ```bash
    docker-compose -f docker-compose.analysis-worker.yml up --build
    ```
    -   In a **third terminal**, run `docker-compose.completions-worker.yml` to start the worker for AI completion jobs.
    ```bash
    docker-compose -f docker-compose.completions-worker.yml up --build
    ```

You can now submit an analysis job to `http://localhost:8030/api/v1/jobs` and see the analysis worker process it. You can submit a completion job to `http://localhost:8030/api/v1/completions` and see the completions worker process it. Both job types will produce artifacts retrievable via the `/api/v1/jobs/{job_id}/results` endpoint.

### Testing the Completions Endpoint with `curl`

You can quickly test the AI completions workflow from your terminal using `curl`. Make sure your server and completions worker containers are running.

1.  **Submit a Completion Job**:
    Send a POST request with a unique `job_id` and a `prompt`.

    ```bash
    curl -X POST http://localhost:8030/api/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
      "model": "llama3:8b",
      "job_id": "my-curl-test-01",
      "prompt": "Why is the sky blue? Explain it simply."
    }'
    ```
    You will get a response with URLs to check the job's status and results.

2.  **Check the Job Status**:
    Use the `status_url` from the previous response to poll the job's status.

    ```bash
    # Replace the job_id with your own
    curl http://localhost:8030/api/v1/jobs/my-curl-test-01/status
    ```
    Initially, this will show `{"status":"queued"}`. After the worker processes it, it will show `{"status":"completed", ...}`.

3.  **Retrieve the Result**:
    Once the job is complete, you can list the available result files.

    ```bash
    # Replace the job_id with your own
    curl http://localhost:8030/api/v1/jobs/my-curl-test-01/results
    ```
    This will return a JSON object with a link to `completion.json`.

4.  **View the Final JSON Output**:
    Use the URL for `completion.json` to see the response from Ollama.

    ```bash
    # Replace the job_id with your own
    curl http://localhost:8030/api/v1/jobs/my-curl-test-01/results/completion.json
    ```
