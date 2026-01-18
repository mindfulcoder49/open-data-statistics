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

## Docker Development

For instructions on how to run the backend services using Docker for local development, please see the comprehensive guide in the root directory:

[**DOCKER_README.md**](../DOCKER_README.md)

That guide explains the different Docker Compose files and provides step-by-step instructions for running the complete local development environment.

## Distributed Development (Remote Worker)

For instructions on running a distributed setup with a remote server and local workers, please refer to the "Distributed (Remote Worker) Setup" section in the main [**DOCKER_README.md**](../DOCKER_README.md).

### Testing the Completions Endpoint with `curl`

You can quickly test the AI completions workflow from your terminal using `curl`. Make sure your server and completions worker containers are running as described in `DOCKER_README.md`.

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
