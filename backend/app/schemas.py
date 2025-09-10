from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal

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
