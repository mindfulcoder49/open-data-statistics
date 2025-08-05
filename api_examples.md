# API Job Submission Examples

This file contains example `curl` commands to submit analysis jobs to the API.

## Example 1: Stage 3 - Univariate Anomaly Analysis

This example runs the univariate anomaly and trend detection, grouping data by `DISTRICT` and `OFFENSE_DESCRIPTION`.

```bash
curl -X POST http://localhost:8080/api/v1/jobs -H "Content-Type: application/json" -d '{
    "job_id": "test-job-131",
    "data_url": "http://backend:8080/data/test_data/crime-incident-reports.csv",
    "config": {
        "timestamp_col": "OCCURRED_ON_DATE",
        "lat_col": "Lat",
        "lon_col": "Long",
        "analysis_stages": ["stage3_univariate_anomaly"],
        "generate_reports": {
                "stage3_univariate_anomaly":"true"
                },
        "parameters": {
            "stage3_univariate_anomaly": {
                "primary_group_col": "DISTRICT",
                "secondary_group_col": "OFFENSE_DESCRIPTION"
            }
        }
    }
}'
```

## Example 2: Stage 4 - H3-Based Spatial Anomaly Analysis

This example runs the same anomaly and trend detection as Stage 3, but uses H3 hexagonal spatial clustering instead of a predefined primary column. It groups incidents into H3 cells at resolution 9, and then analyzes each cell's time series grouped by `OFFENSE_DESCRIPTION`.

The `skip_existing` flag is set to `true`, so if a results file for this stage and job ID already exists, the stage will be skipped.

```bash
curl -X POST http://localhost:8080/api/v1/jobs -H "Content-Type: application/json" -d '{
    "job_id": "test-job-h3-1",
    "data_url": "http://backend:8080/data/test_data/crime-incident-reports.csv",
    "config": {
        "timestamp_col": "OCCURRED_ON_DATE",
        "lat_col": "Lat",
        "lon_col": "Long",
        "skip_existing": true,
        "analysis_stages": ["stage4_h3_anomaly"],
        "generate_reports": {
            "stage4_h3_anomaly": "true"
        },
        "parameters": {
            "stage4_h3_anomaly": {
                "secondary_group_col": "OFFENSE_DESCRIPTION",
                "h3_resolution": 9
            }
        }
    }
}'
```

```bash
curl -X POST http://localhost:8080/api/v1/jobs -H "Content-Type: application/json" -d '{
    "job_id": "test-job-h3-311",
    "data_url": "http://backend:8080/data/test_data/boston_311_2025.csv",
    "config": {
        "timestamp_col": "open_dt",
        "lat_col": "latitude",
        "lon_col": "longitude",
        "skip_existing": true,
        "analysis_stages": ["stage4_h3_anomaly"],
        "generate_reports": {
            "stage4_h3_anomaly": "true"
        },
        "parameters": {
            "stage4_h3_anomaly": {
                "secondary_group_col": "type",
                "h3_resolution": 9
            }
        }
    }
}'
```

## Example 3: Stage 4 with Filtering

This example is the same as the 311 data analysis above, but it adds a filter to **only analyze "Needle Pickup" requests**. This is useful for focusing on a specific problem area.

```bash
curl -X POST http://localhost:8080/api/v1/jobs -H "Content-Type: application/json" -d '{
    "job_id": "test-job-h3-311-needles",
    "data_url": "http://backend:8080/data/test_data/boston_311_2025.csv",
    "config": {
        "timestamp_col": "open_dt",
        "lat_col": "latitude",
        "lon_col": "longitude",
        "skip_existing": true,
        "analysis_stages": ["stage4_h3_anomaly"],
        "parameters": {
            "stage4_h3_anomaly": {
                "secondary_group_col": "type",
                "h3_resolution": 9,
                "filter_col": "type",
                "filter_val": "Needle Pickup"
            }
        }
    }
}'
```

## Accessing Reports

Once a job is complete, you can access the generated reports and data artifacts.

1.  **Check Job Status**: Poll the status URL until the status is `completed`.
    ```bash
    curl http://localhost:8080/api/v1/jobs/test-job-h3-1/status
    ```
    **Response:**
    ```json
    {
        "job_id": "test-job-h3-1",
        "status": "completed",
        "current_stage": null,
        "error_message": null
    }
    ```

2.  **List Available Results**: Once completed, query the results URL.
    ```bash
    curl http://localhost:8080/api/v1/jobs/test-job-h3-1/results
    ```
    **Response:**
    ```json
    {
        "job_id": "test-job-h3-1",
        "status": "completed",
        "results": {
            "stage4_h3_anomaly": "http://localhost:8080/api/v1/jobs/test-job-h3-1/results/stage4_h3_anomaly.json",
            "stage4_h3_anomaly_viewer": "http://localhost:8080/reports/view/stage4?job_id=test-job-h3-1"
        }
    }
    ```

3.  **View the Report**:
    *   For **Stage 3**, you will see a link to a static HTML report (e.g., `report_stage3_univariate_anomaly`). You can download and open this file.
    *   For **Stage 4**, open the `stage4_h3_anomaly_viewer` URL in your web browser. This is a dynamic viewer that loads your job's data on the fly.
