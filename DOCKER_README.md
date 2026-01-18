# Docker Environment Guide

This document explains the different Docker Compose files in this project and how to use them for local development, distributed testing, and production.

## File Overview

This project uses multiple `docker-compose` files to handle different deployment scenarios.

-   `docker-compose.local.yml`
    -   **Purpose**: **Recommended for local development.**
    -   **Services**: `redis`, `backend`, `analysis-worker`.
    -   **Description**: Runs the core application (backend, Redis, and analysis worker) on a single Docker network. It's the easiest way to get started for most development tasks. The completions worker must be run separately.

-   `docker-compose.worker-completions.yml`
    -   **Purpose**: Runs the AI completions worker.
    -   **Services**: `completions-worker`.
    -   **Description**: This worker connects to your local Ollama instance. It uses `network_mode: "host"` to access Ollama running on your host machine's `localhost`. It must be run separately from other Docker Compose setups.

-   `docker-compose.server.yml`
    -   **Purpose**: Runs only the server-side components for a distributed setup.
    -   **Services**: `redis`, `backend`.
    -   **Description**: Use this on a remote server. It exposes the Redis and backend ports to allow remote workers to connect.

-   `docker-compose.worker-analysis.yml`
    -   **Purpose**: Runs only the analysis worker for a distributed setup.
    -   **Services**: `analysis-worker`.
    -   **Description**: Use this on a local or separate machine to connect to a remote server running `docker-compose.server.yml`.

-   `docker-compose.yml`
    -   **Purpose**: **Production deployment.**
    -   **Services**: `backend`, `nginx`, `letsencrypt`.
    -   **Description**: Deploys the application behind an Nginx reverse proxy with automatic SSL certificate generation via Let's Encrypt. This file is intended for a public-facing server.

---

## Complete Local Development Setup

This is the recommended way to run the entire system on your local machine for development. This setup uses `local` storage and allows you to test both analysis and completion jobs.

### 1. Prerequisites

-   Docker and Docker Compose are installed.
-   [Ollama](https://ollama.com/) is installed and running on your local machine.
-   You have pulled at least one model (e.g., `ollama pull llama3`).

### 2. Configure `.env` File

Create or update your `.env` file with the following settings for local development.

```properties
# .env

# --- Redis ---
# This password is used by all local services.
REDIS_PASSWORD=your-secure-password

# --- URLs for Distributed Setup (used by completions-worker) ---
# These point to the host machine from within a container.
REDIS_URL=redis://:your-secure-password@host.docker.internal:6379/0
CELERY_BROKER_URL=redis://:your-secure-password@host.docker.internal:6379/0
INTERNAL_API_HOSTNAME=http://host.docker.internal:8030

# --- Ollama ---
# This is used by the completions worker to find Ollama on the host.
OLLAMA_URL=http://localhost:11434

# --- Storage ---
# Use local storage for simple local development.
STORAGE_TYPE=local
S3_BUCKET_NAME=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=
```

### 3. Run the Core Services

In your **first terminal**, launch the backend, Redis, and the analysis worker.

```bash
docker-compose -f docker-compose.local.yml up --build
```

-   The backend API will be available at `http://localhost:8030`.
-   The analysis worker will connect automatically and start listening for jobs on the `celery` queue.

### 4. Run the Completions Worker

In your **second terminal**, launch the completions worker. This worker needs to run in a separate command because it uses host networking to see Ollama.

```bash
docker-compose -f docker-compose.completions-worker.yml up --build
```

-   This worker will connect to Redis and start listening for jobs on the `completions` queue.

The full system is now running locally.

---

## Connecting from Laravel (Local Development)

When your Laravel application is also running in a Docker container (e.g., via Laravel Sail), it needs to connect to the backend service. Since the backend is exposed on your host machine at port `8030`, your Laravel app can use the special `host.docker.internal` DNS name to reach it.

Set the following in your Laravel application's `.env` file:

```properties
# In your Laravel .env file
ANALYSIS_API_URL=http://host.docker.internal:8030
```

This tells Laravel to send API requests to port `8030` on the machine that is hosting the Docker containers.
