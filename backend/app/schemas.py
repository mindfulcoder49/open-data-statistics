from pydantic import BaseModel, Field, AnyHttpUrl
from typing import List, Optional, Literal

class AnalysisConfig(BaseModel):
    timestamp_col: str
    lat_col: str
    lon_col: str
    analysis_stages: List[Literal["stage4_explain"]]
    parameters: Optional[dict] = {}

class JobCreateRequest(BaseModel):
    job_id: str = Field(..., description="A UUID provided by the client (e.g., Laravel)")
    data_url: AnyHttpUrl = Field(..., description="Pre-signed URL to the input CSV")
    config: AnalysisConfig
    callback_url: Optional[AnyHttpUrl] = None

class JobCreateResponse(BaseModel):
    job_id: str
    status: str = "queued"
    message: str = "Analysis job accepted and queued for processing."
    status_url: str
    results_url: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str # e.g., "queued", "processing", "completed", "failed"
    current_stage: Optional[str] = None
    error_message: Optional[str] = None
