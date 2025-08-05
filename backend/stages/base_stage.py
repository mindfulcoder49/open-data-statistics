from abc import ABC, abstractmethod
import pandas as pd
import json
import os
from app.config import settings
from typing import Optional
# Import BaseReporter for type hinting, avoiding circular import with a forward reference if needed
from reporting.base_reporter import BaseReporter

class BaseAnalysisStage(ABC):
    """
    Abstract Base Class for all analysis stages in the pipeline.
    """
    def __init__(self, job_id: str, config: dict):
        self.job_id = job_id
        self.config = config
        self.job_dir = os.path.join(settings.RESULTS_DIR, self.job_id)
        os.makedirs(self.job_dir, exist_ok=True)

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique name of the stage, e.g., 'stage4_explain'."""
        pass

    @abstractmethod
    def get_reporter(self) -> Optional[BaseReporter]:
        """Returns an instance of the reporter for this stage, or None."""
        pass

    @abstractmethod
    def run(self, df: pd.DataFrame) -> dict:
        """
        Executes the analysis for this stage.
        Takes a pandas DataFrame as input.
        Returns a dictionary to be serialized as the JSON result.
        """
        pass

    def generate_and_save_report(self, results: dict, df: pd.DataFrame):
        """Generates and saves the report for the stage, if a reporter is available."""
        reporter = self.get_reporter()
        if reporter:
            # Add filepath to results so reporter knows where to save images
            results['__filepath__'] = os.path.join(self.job_dir, f"{self.name}.json")
            
            report_content = reporter.generate_report(results, df)
            report_filename = f"report_{self.name}.{reporter.file_extension}"
            self._save_report(report_content, report_filename)

    def _save_results(self, results: dict, filename: str) -> str:
        """
        Helper method to save a dictionary as JSON to the local results directory.
        Returns the path to the saved file.
        """
        output_path = os.path.join(self.job_dir, filename)
        
        print(f"Saving results for job {self.job_id} to {output_path}")
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=4)
            
        return output_path

    def _save_report(self, content: str, filename: str):
        """Saves the report content to a file in the job's directory."""
        filepath = os.path.join(self.job_dir, filename)
        with open(filepath, 'w') as f:
            f.write(content)
