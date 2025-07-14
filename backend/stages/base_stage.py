from abc import ABC, abstractmethod
import pandas as pd
import json
import os
from app.config import settings

class BaseAnalysisStage(ABC):
    """
    Abstract Base Class for all analysis stages in the pipeline.
    """
    def __init__(self, job_id: str, config: dict):
        self.job_id = job_id
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique name of the stage, e.g., 'stage4_explain'."""
        pass

    @abstractmethod
    def run(self, df: pd.DataFrame) -> dict:
        """
        Executes the analysis for this stage.
        Takes a pandas DataFrame as input.
        Returns a dictionary to be serialized as the JSON result.
        """
        pass

    def _save_results(self, results: dict, filename: str) -> str:
        """
        Helper method to save a dictionary as JSON to the local results directory.
        Returns the path to the saved file.
        """
        # Ensure the job-specific directory exists
        job_dir = os.path.join(settings.RESULTS_DIR, self.job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        output_path = os.path.join(job_dir, filename)
        
        print(f"Saving results for job {self.job_id} to {output_path}")
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=4)
            
        return output_path
