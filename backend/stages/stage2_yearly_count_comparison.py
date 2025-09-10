import pandas as pd
import numpy as np
import os
import json
import logging
from .base_stage import BaseAnalysisStage
from reporting.base_reporter import BaseReporter
from typing import Optional

logger = logging.getLogger(__name__)

class Stage2YearlyCountComparison(BaseAnalysisStage):
    """
    Performs a yearly count comparison analysis.
    - Groups data by a specified column.
    - Counts occurrences per year for each group.
    - Calculates year-over-year percentage changes.
    - Compares the latest year's count to a specified baseline year.
    """
    def __init__(self, job_id: str, config: dict, redis_client=None, data_sources: list = None):
        super().__init__(job_id, config, redis_client=redis_client, data_sources=data_sources)

    @property
    def name(self) -> str:
        return "stage2_yearly_count_comparison"

    def get_reporter(self) -> Optional[BaseReporter]:
        """
        This stage does not have a specific Python-based reporter.
        Results are intended for direct use or visualization in a client application.
        """
        return None

    def run(self, df: Optional[pd.DataFrame] = None) -> dict:
        """
        Executes the yearly count comparison analysis.
        """
        # Check if stage should be skipped
        skip_existing = self.config.get('skip_existing', False)
        output_path = os.path.join(self.job_dir, f"{self.name}.json")
        if skip_existing and os.path.exists(output_path):
            print(f"Skipping stage {self.name} as output already exists.")
            with open(output_path, 'r') as f:
                return json.load(f)

        # --- This stage loads its own data ---
        if not self.data_sources:
            raise ValueError("data_sources list must be provided to run this stage.")
        
        logger.info(f"[{self.job_id}] Loading data for {self.name} from {self.data_sources[0]['data_url']}")
        df = pd.read_csv(self.data_sources[0]['data_url'])
        # ---

        # Get parameters
        stage_params = self.config.get('parameters', {}).get(self.name, {})
        
        # For stages that get a pre-loaded df, column names must be in parameters
        timestamp_col = stage_params.get('timestamp_col')
        if not timestamp_col:
            raise ValueError(f"Missing required parameter 'timestamp_col' for stage {self.name}")

        group_by_col = stage_params.get('group_by_col')
        baseline_year = stage_params.get('baseline_year')

        if not group_by_col:
            raise ValueError(f"Missing required parameter 'group_by_col' for stage {self.name}")

        df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors='coerce')
        df.dropna(subset=[timestamp_col], inplace=True)
        df['year'] = df[timestamp_col].dt.year

        # Perform aggregation
        yearly_counts = df.groupby([group_by_col, 'year']).size().unstack(fill_value=0)

        results = []
        for group, counts in yearly_counts.iterrows():
            yearly_counts_dict = counts.to_dict()
            
            # Calculate Year-over-Year (YoY) percentage change
            sorted_years = sorted(yearly_counts_dict.keys())
            yoy_change = {}
            for i in range(1, len(sorted_years)):
                prev_year = sorted_years[i-1]
                current_year = sorted_years[i]
                prev_count = yearly_counts_dict[prev_year]
                current_count = yearly_counts_dict[current_year]
                
                if prev_count > 0:
                    change_pct = ((current_count - prev_count) / prev_count) * 100
                    yoy_change[f"{current_year}_vs_{prev_year}"] = round(change_pct, 2)
                else:
                    yoy_change[f"{current_year}_vs_{prev_year}"] = None # Avoid division by zero

            # Calculate change from baseline year to latest year
            baseline_comparison = {}
            if baseline_year and baseline_year in sorted_years and sorted_years:
                latest_year = sorted_years[-1]
                baseline_count = yearly_counts_dict.get(baseline_year, 0)
                latest_count = yearly_counts_dict.get(latest_year, 0)

                if baseline_count > 0:
                    change_pct = ((latest_count - baseline_count) / baseline_count) * 100
                    baseline_comparison = {
                        "vs_year": baseline_year,
                        "latest_year": latest_year,
                        "change_pct": round(change_pct, 2)
                    }
                else:
                     baseline_comparison = {
                        "vs_year": baseline_year,
                        "latest_year": latest_year,
                        "change_pct": None
                    }

            results.append({
                "group": group,
                "yearly_counts": yearly_counts_dict,
                "yoy_change": yoy_change,
                "baseline_comparison": baseline_comparison
            })

        output = {
            "status": "success",
            "stage_name": self.name,
            "parameters": stage_params,
            "results": results
        }

        self._save_results(output, f"{self.name}.json")
        return output
