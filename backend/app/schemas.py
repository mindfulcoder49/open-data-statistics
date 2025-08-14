from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

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
    analysis_weeks: int = 4
    p_value_anomaly: float = 0.05
    p_value_trend: float = 0.05
    generate_plots: bool = True

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
