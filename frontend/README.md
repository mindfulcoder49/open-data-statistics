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
