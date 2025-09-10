import pandas as pd
import logging
from app.schemas import JobCreateRequest
from stages import AVAILABLE_STAGES
from reporting import AVAILABLE_REPORTERS
import os
import json

logger = logging.getLogger(__name__)

class PipelineManager:
    def __init__(self, job_id: str, config: dict, data_sources: list, redis_client=None):
        self.job_id = job_id
        self.config = config
        self.data_sources = data_sources
        self.results = {}
        self.redis_client = redis_client

    def execute(self):
        """
        Executes the full analysis pipeline: loads data, then runs requested stages.
        """
        analysis_stages = self.config.get('analysis_stages', [])
        logger.info(f"[{self.job_id}] Running stages: {analysis_stages}")
        generate_reports_config = self.config.get('generate_reports', {})

        for stage_name in analysis_stages:
            if stage_name not in AVAILABLE_STAGES:
                logger.warning(f"[{self.job_id}] Unknown stage requested: {stage_name}")
                continue

            logger.info(f"[{self.job_id}] Executing stage: {stage_name}")
            stage_class = AVAILABLE_STAGES[stage_name]
            
            # Instantiate every stage consistently, providing all context.
            # Each stage is responsible for its own data loading logic.
            stage_instance = stage_class(
                self.job_id, 
                self.config, 
                redis_client=self.redis_client, 
                data_sources=self.data_sources
            )
            
            # The `run` method is called without a DataFrame.
            # Stages that need data will load it themselves.
            stage_result = stage_instance.run()
            
            # For stages that don't save their own results (like Stage 2 & 3), save them now.
            # Stage 4 handles its own streaming save, so this is a no-op for it if the file exists.
            result_filename = f"{stage_name}.json"
            if not os.path.exists(os.path.join(stage_instance.job_dir, result_filename)):
                 stage_instance._save_results(stage_result, result_filename)

            # Add filepath to result for reporter context
            stage_result['__filepath__'] = os.path.join(stage_instance.job_dir, result_filename)

            self.results[stage_name] = stage_result
            logger.info(f"[{self.job_id}] Completed stage: {stage_name}")

            # Generate report if requested
            if generate_reports_config.get(stage_name, False):
                reporter = stage_instance.get_reporter()
                if reporter:
                    logger.info(f"[{self.job_id}] Generating report for stage: {stage_name}")
                    # The DataFrame might need to be re-loaded for reporting if not passed.
                    # For simplicity, we assume the reporter can handle the result dict.
                    # A more advanced implementation might pass the loaded df from the stage.
                    df_for_report = pd.read_csv(self.data_sources[0]['data_url']) if stage_name != 'stage4_h3_anomaly' else None
                    stage_instance.generate_and_save_report(stage_result, df_for_report)
                    logger.info(f"[{self.job_id}] Saved report for stage: {stage_name}")
                else:
                    logger.warning(f"[{self.job_id}] Report requested for '{stage_name}' but no reporter found.")
        
        return self.results
