import pandas as pd
import logging
from app.schemas import JobCreateRequest
from stages import AVAILABLE_STAGES
from reporting import AVAILABLE_REPORTERS
import os

logger = logging.getLogger(__name__)

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
        generate_reports_config = self.config.get('generate_reports', {})

        for stage_name in analysis_stages:
            if stage_name in AVAILABLE_STAGES:
                stage_class = AVAILABLE_STAGES[stage_name]
                stage_instance = stage_class(self.job_id, self.config)
                
                logger.info(f"[{self.job_id}] Executing stage: {stage_name}")
                stage_result = stage_instance.run(df)
                
                # Add filepath to result for reporter context
                result_filename = f"{stage_name}.json"
                stage_instance._save_results(stage_result, result_filename)
                stage_result['__filepath__'] = os.path.join(stage_instance.job_dir, result_filename)

                self.results[stage_name] = stage_result
                logger.info(f"[{self.job_id}] Completed stage: {stage_name}")

                # 3. Generate report if requested
                if generate_reports_config.get(stage_name, False):
                    if stage_name in AVAILABLE_REPORTERS:
                        logger.info(f"[{self.job_id}] Generating report for stage: {stage_name}")
                        reporter_class = AVAILABLE_REPORTERS[stage_name]
                        reporter_instance = reporter_class()
                        report_content = reporter_instance.generate_report(stage_result)
                        report_filename = f"{stage_name}.{reporter_instance.file_extension}"
                        stage_instance._save_report(report_content, report_filename)
                        logger.info(f"[{self.job_id}] Saved report: {report_filename}")
                    else:
                        logger.warning(f"[{self.job_id}] Report requested for '{stage_name}' but no reporter found.")
            else:
                logger.warning(f"[{self.job_id}] Unknown stage requested: {stage_name}")
        
        return self.results
