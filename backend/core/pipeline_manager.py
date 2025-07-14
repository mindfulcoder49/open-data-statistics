import pandas as pd
import logging
from app.schemas import JobCreateRequest
from stages.stage4_explain import Stage4Explain

logger = logging.getLogger(__name__)

# This map acts as a registry for available analysis stages.
# To add a new stage, import it and add it to this dictionary.
AVAILABLE_STAGES = {
    "stage4_explain": Stage4Explain,
}

class PipelineManager:
    def __init__(self, job_id: str, config: dict, data_url: str):
        self.job_id = job_id
        self.config = config
        self.data_url = data_url
        self.results = {}

    def execute(self):
        """
        Executes the full analysis pipeline: loads data, then runs requested stages.
        """
        # 1. Load data from the provided URL
        logger.info(f"[{self.job_id}] Loading data from {self.data_url}")
        try:
            df = pd.read_csv(self.data_url)
        except Exception as e:
            logger.error(f"[{self.job_id}] Failed to load data: {e}")
            raise  # Re-raise to be caught by the Celery task

        # 2. Dynamically instantiate and run each requested stage
        analysis_stages = self.config.get('analysis_stages', [])
        logger.info(f"[{self.job_id}] Running stages: {analysis_stages}")

        for stage_name in analysis_stages:
            if stage_name in AVAILABLE_STAGES:
                stage_class = AVAILABLE_STAGES[stage_name]
                stage_instance = stage_class(self.job_id, self.config)
                
                logger.info(f"[{self.job_id}] Executing stage: {stage_name}")
                stage_result = stage_instance.run(df)
                self.results[stage_name] = stage_result
                logger.info(f"[{self.job_id}] Completed stage: {stage_name}")
            else:
                logger.warning(f"[{self.job_id}] Unknown stage requested: {stage_name}")
        
        return self.results
