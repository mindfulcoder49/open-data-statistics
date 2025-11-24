import pandas as pd
import numpy as np
import os
import json
import logging
from typing import Optional
from core.storage import JsonStorageModel

logger = logging.getLogger(__name__)

class Stage2YearlyCountComparison:
    """
    Performs a yearly count comparison analysis.
    - Groups data by a specified column.
    - Counts occurrences per year for each group.
    - Calculates year-over-year percentage changes.
    - Compares the latest year's count to a specified baseline year.
    """
    def __init__(self, job_id: str, config: dict, results_dir: str, redis_client=None, data_sources: list = None):
        self.job_id = job_id
        self.config = config
        self.redis_client = redis_client
        self.data_sources = data_sources
        self.job_dir = os.path.join(results_dir, self.job_id)
        # We still create local dir for temp processing if needed, but storage is abstracted
        os.makedirs(self.job_dir, exist_ok=True)
        self.json_storage = JsonStorageModel()

    @property
    def name(self) -> str:
        return "stage2_yearly_count_comparison"

    def get_reporter(self) -> Optional[object]:
        """
        This stage does not have a specific Python-based reporter.
        Results are intended for direct use or visualization in a client application.
        """
        return None

    def _save_results(self, results: dict, filename: str) -> str:
        """
        Helper method to save results using the JsonStorageModel.
        """
        print(f"Saving results for job {self.job_id} to storage: {filename}")
        return self.json_storage.save(self.job_id, filename, results)

    def run(self, df: Optional[pd.DataFrame] = None) -> dict:
        """
        Executes the yearly count comparison analysis.
        """
        # Check if stage should be skipped
        skip_existing = self.config.get('skip_existing', False)
        filename = f"{self.name}.json"
        
        if skip_existing and self.json_storage.exists(self.job_id, filename):
            print(f"Skipping stage {self.name} as output already exists.")
            return self.json_storage.load(self.job_id, filename)

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
        if not group_by_col:
            raise ValueError(f"Missing required parameter 'group_by_col' for stage {self.name}")

        df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors='coerce')
        df.dropna(subset=[timestamp_col, group_by_col], inplace=True)
        df['year'] = df[timestamp_col].dt.year

        # --- Full Year Analysis ---
        full_year_counts = df.groupby([group_by_col, 'year']).size().unstack(fill_value=0)

        # --- To-Date Analysis (for current year vs previous years) ---
        latest_date = df[timestamp_col].max()
        current_year = latest_date.year
        
        # Filter data to include only days up to the latest date's day-of-year
        to_date_df = df[df[timestamp_col].dt.dayofyear <= latest_date.dayofyear].copy()
        to_date_counts = to_date_df.groupby([group_by_col, 'year']).size().unstack(fill_value=0)

        results = []
        all_years = sorted(list(set(full_year_counts.columns) | set(to_date_counts.columns)))

        for group in full_year_counts.index:
            group_result = {"group": group, "full_year": {}, "to_date": {}}
            
            # Process Full Year Data
            full_year_row = full_year_counts.loc[group]
            for year in all_years:
                count = int(full_year_row.get(year, 0))
                prev_year_count = int(full_year_row.get(year - 1, 0))
                change = None
                if prev_year_count > 0:
                    change = round(((count - prev_year_count) / prev_year_count) * 100, 2)
                
                # Don't show full-year data for the current, incomplete year
                if year < current_year:
                    group_result["full_year"][year] = {"count": count, "change_pct": change}
                elif year == current_year:
                     group_result["full_year"][year] = {"count": count, "change_pct": None}


            # Process To-Date Data
            if group in to_date_counts.index:
                to_date_row = to_date_counts.loc[group]
                for year in all_years:
                    count = int(to_date_row.get(year, 0))
                    prev_year_count = int(to_date_row.get(year - 1, 0))
                    change = None
                    if prev_year_count > 0:
                        change = round(((count - prev_year_count) / prev_year_count) * 100, 2)
                    
                    group_result["to_date"][year] = {"count": count, "change_pct": change}
            
            results.append(group_result)

        output = {
            "status": "success",
            "stage_name": self.name,
            "parameters": {
                **stage_params,
                "analysis_current_year": current_year,
                "analysis_to_date_cutoff": latest_date.strftime('%Y-%m-%d')
            },
            "results": results,
            "all_years": all_years
        }

        self._save_results(output, filename)
        return output
