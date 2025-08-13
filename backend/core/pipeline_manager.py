import pandas as pd
import logging
from app.schemas import JobCreateRequest
from stages import AVAILABLE_STAGES
from reporting import AVAILABLE_REPORTERS
import os

logger = logging.getLogger(__name__)

class PipelineManager:
    def __init__(self, job_id: str, config: dict, data_url: str, redis_client=None):
        self.job_id = job_id
        self.config = config
        self.data_url = data_url
        self.results = {}
        self.redis_client = redis_client

    def execute(self):
        """
        Executes the full analysis pipeline: loads data, then runs requested stages.
        """
        analysis_stages = self.config.get('analysis_stages', [])
        logger.info(f"[{self.job_id}] Running stages: {analysis_stages}")
        generate_reports_config = self.config.get('generate_reports', {})

        # Data is loaded conditionally by or for each stage.
        df = None

        for stage_name in analysis_stages:
            if stage_name in AVAILABLE_STAGES:
                stage_class = AVAILABLE_STAGES[stage_name]
                
                # --- Stage-Specific Instantiation and Execution ---
                if stage_name == 'stage4_h3_anomaly':
                    # This stage handles its own data loading from a URL to minimize memory.
                    stage_instance = stage_class(
                        self.job_id, 
                        self.config, 
                        redis_client=self.redis_client, 
                        data_url=self.data_url
                    )
                    logger.info(f"[{self.job_id}] Executing stage: {stage_name} with chunked processing.")
                    stage_result = stage_instance.run() # Called without a DataFrame
                else:
                    # For other potential stages, load the full DataFrame if not already loaded.
                    if df is None:
                        logger.info(f"[{self.job_id}] Loading full DataFrame for stage {stage_name} from {self.data_url}")
                        try:
                            df = pd.read_csv(self.data_url)
                        except Exception as e:
                            logger.error(f"[{self.job_id}] Failed to load data for stage {stage_name}: {e}")
                            raise
                    
                    stage_instance = stage_class(self.job_id, self.config, redis_client=self.redis_client)
                    logger.info(f"[{self.job_id}] Executing stage: {stage_name}")
                    stage_result = stage_instance.run(df) # Called with a DataFrame
                
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
