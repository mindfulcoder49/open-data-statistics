# API Job Submission Examples

This file contains example `curl` commands to submit analysis jobs to the API.

## Example 1: Stage 2 - Yearly Count Comparison

This example runs the yearly count comparison, grouping data by `OFFENSE_DESCRIPTION` and comparing against a baseline year of 2019.

```bash
curl -X POST http://localhost:8080/api/v1/jobs -H "Content-Type: application/json" -d '{
    "job_id": "test-job-stage2-yearly-1",
    "data_sources": [
        {
            "data_url": "http://localhost:8080/data/test_data/crime-incident-reports.csv",
            "timestamp_col": "OCCURRED_ON_DATE",
            "lat_col": "Lat",
            "lon_col": "Long",
            "secondary_group_col": "OFFENSE_DESCRIPTION"
        }
    ],
    "config": {
        "analysis_stages": ["stage2_yearly_count_comparison"],
        "parameters": {
            "stage2_yearly_count_comparison": {
                "timestamp_col": "OCCURRED_ON_DATE",
                "group_by_col": "OFFENSE_DESCRIPTION",
                "baseline_year": 2019
            }
        }
    }
}'
```

## Example 2: Stage 3 - Univariate Anomaly Analysis

This example runs univariate anomaly and trend detection, grouping data by `DISTRICT` and `OFFENSE_DESCRIPTION`.

```bash
curl -X POST http://localhost:8080/api/v1/jobs -H "Content-Type: application/json" -d '{
    "job_id": "test-job-stage3-univariate-1",
    "data_sources": [
        {
            "data_url": "http://localhost:8080/data/test_data/crime-incident-reports.csv",
            "timestamp_col": "OCCURRED_ON_DATE",
            "lat_col": "Lat",
            "lon_col": "Long",
            "secondary_group_col": "OFFENSE_DESCRIPTION"
        }
    ],
    "config": {
        "analysis_stages": ["stage3_univariate_anomaly"],
        "parameters": {
            "stage3_univariate_anomaly": {
                "timestamp_col": "OCCURRED_ON_DATE",
                "primary_group_col": "DISTRICT",
                "secondary_group_col": "OFFENSE_DESCRIPTION"
            }
        }
    }
}'
```

## Example 3: Stage 4 - H3-Based Spatial Anomaly Analysis

This example runs anomaly and trend detection using H3 hexagonal spatial clustering. It groups incidents into H3 cells at resolution 9, and then analyzes each cell's time series grouped by `OFFENSE_DESCRIPTION`.

```bash
curl -X POST http://localhost:8080/api/v1/jobs -H "Content-Type: application/json" -d '{
    "job_id": "test-job-h3-crime-1",
    "data_sources": [
        {
            "data_url": "http://localhost:8080/data/test_data/crime-incident-reports.csv",
            "timestamp_col": "OCCURRED_ON_DATE",
            "lat_col": "Lat",
            "lon_col": "Long",
            "secondary_group_col": "OFFENSE_DESCRIPTION"
        }
    ],
    "config": {
        "analysis_stages": ["stage4_h3_anomaly"],
        "parameters": {
            "stage4_h3_anomaly": {
                "h3_resolution": 9
            }
        }
    }
}'
```

## Example 4: Stage 4 with 311 Data and Filtering

This example analyzes 311 data, but adds a filter to **only analyze "Needle Pickup" requests**. This is useful for focusing on a specific problem area.

```bash
curl -X POST http://localhost:8080/api/v1/jobs -H "Content-Type: application/json" -d '{
    "job_id": "test-job-h3-311-needles",
    "data_sources": [
        {
            "data_url": "http://localhost:8080/data/test_data/boston_311_2025.csv",
            "timestamp_col": "open_dt",
            "lat_col": "latitude",
            "lon_col": "longitude",
            "secondary_group_col": "type"
        }
    ],
    "config": {
        "analysis_stages": ["stage4_h3_anomaly"],
        "parameters": {
            "stage4_h3_anomaly": {
                "h3_resolution": 9,
                "filter_col": "type",
                "filter_values": ["Needle Pickup"]
            }
        }
    }
}'
```

## Example 5: Stage 4 with Custom Parameters

This example uses the 311 dataset and demonstrates a fully customized request. It filters for "Needle Pickup" requests, defines multiple trend analysis windows, sets custom p-value thresholds, and disables plot generation to save time.

```bash
curl -X POST http://localhost:8080/api/v1/jobs -H "Content-Type: application/json" -d '{
    "job_id": "test-job-h3-311-needles-custom",
    "data_sources": [
        {
            "data_url": "http://localhost:8080/data/test_data/boston_311_2025.csv",
            "timestamp_col": "open_dt",
            "lat_col": "latitude",
            "lon_col": "longitude",
            "secondary_group_col": "type"
        }
    ],
    "config": {
        "analysis_stages": ["stage4_h3_anomaly"],
        "parameters": {
            "stage4_h3_anomaly": {
                "h3_resolution": 9,
                "filter_col": "type",
                "filter_values": ["Needle Pickup"],
                "analysis_weeks_trend": [4, 8, 12],
                "analysis_weeks_anomaly": 4,
                "p_value_anomaly": 0.01,
                "p_value_trend": 0.05,
                "plot_generation": "none"
            }
        }
    }
}'
```

## Accessing Reports

Once a job is complete, you can access the generated reports and data artifacts.

1.  **Check Job Status**: Poll the status URL until the status is `completed`.
    ```bash
    curl http://localhost:8080/api/v1/jobs/test-job-h3-crime-1/status
    ```
    **Response:**
    ```json
    {
        "job_id": "test-job-h3-crime-1",
        "status": "completed",
        "current_stage": null,
        "error_message": null,
        "progress": 100,
        "stage_detail": "Finalizing results"
    }
    ```

2.  **List Available Results**: Once completed, query the results URL.
    ```bash
    curl http://localhost:8080/api/v1/jobs/_job-id_/results
    ```
    **Response (Example for a job with Stage 4):**
    ```json
    {
        "job_id": "test-job-h3-crime-1",
        "status": "completed",
        "results": {
            "stage4_h3_anomaly": "http://localhost:8080/api/v1/jobs/test-job-h3-crime-1/results/stage4_h3_anomaly.json",
            "stage4_h3_anomaly_viewer": "http://localhost:8080/reports/view/stage4?job_id=test-job-h3-crime-1"
        }
    }
    ```

3.  **View the Report**:
    *   For **Stage 2 & 3**, you will get a JSON artifact with the analysis results.
    *   For **Stage 4**, open the `stage4_h3_anomaly_viewer` URL in your web browser. This is a dynamic viewer that loads your job's data on the fly.
