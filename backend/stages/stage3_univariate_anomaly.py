import pandas as pd
import numpy as np
from scipy import stats
import os
import json
import logging
from .base_stage import BaseAnalysisStage
from reporting import Stage3Reporter
from reporting.base_reporter import BaseReporter
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class Stage3UnivariateAnomaly(BaseAnalysisStage):
    def __init__(self, job_id: str, config: dict, redis_client=None, data_sources: list = None):
        super().__init__(job_id, config, redis_client=redis_client, data_sources=data_sources)

    @property
    def name(self) -> str:
        return "stage3_univariate_anomaly"

    def get_reporter(self) -> Optional[BaseReporter]:
        return Stage3Reporter()

    def _analyze_time_series(
        self, 
        group_df: pd.DataFrame, 
        timestamp_col: str, 
        end_date: pd.Timestamp, 
        four_weeks_prior: pd.Timestamp,
        min_trend_events: int
    ) -> Optional[dict]:
        """Analyzes a single time series for anomalies and trends."""
        # Resample the full series for the group first
        full_weekly_counts = group_df.resample('W', on=timestamp_col).size()

        # Filter to only include data up to the dataset's end_date
        weekly_counts = full_weekly_counts[full_weekly_counts.index <= end_date]

        # Need at least 8 weeks of data for stable history and 4 weeks of trend
        if len(weekly_counts) < 8:
            return None

        # Correctly define recent and historical periods based on the global end_date
        recent_weeks_counts = weekly_counts[weekly_counts.index > four_weeks_prior]
        historical_counts = weekly_counts[weekly_counts.index <= four_weeks_prior]

        if historical_counts.sum() == 0: # Skip groups with no historical data
            return None

        historical_avg = historical_counts.mean()
        historical_var = historical_counts.var()

        # --- Model Selection based on Mean/Variance Test ---
        model_choice = ""
        # Check for overdispersion (variance > mean)
        if historical_var > historical_avg and historical_avg > 0:
            model_choice = "Negative Binomial"
            try:
                # Use Method of Moments to estimate NB parameters
                p = historical_avg / historical_var
                n = historical_avg * p / (1 - p)
                if not (np.isfinite(p) and np.isfinite(n) and 0 < p <= 1 and n > 0):
                    model_choice = "Poisson (NB fallback)"
                    dist = stats.poisson(mu=historical_avg)
                else:
                    dist = stats.nbinom(n=n, p=p)
            except (ValueError, ZeroDivisionError):
                model_choice = "Poisson (NB error)"
                dist = stats.poisson(mu=historical_avg)
        else:
            model_choice = "Poisson"
            dist = stats.poisson(mu=historical_avg)

        # --- Anomaly Detection for Last 4 Weeks ---
        last_4_weeks_analysis = []
        for week_timestamp, count in recent_weeks_counts.items():
            # p-value is P(X >= count), calculated using the survival function P(X > count-1)
            p_value = dist.sf(count - 1) if count > 0 else 1.0
            
            # Calculate z-score for effect size
            mean = dist.mean()
            std_dev = dist.std()
            z_score = (count - mean) / std_dev if std_dev > 0 else 0

            last_4_weeks_analysis.append({
                "week": week_timestamp.strftime('%Y-%m-%d'),
                "count": int(count),
                "anomaly_p_value": float(p_value),
                "z_score": float(z_score)
            })

        # --- Trend Detection on Last 4 Weeks ---
        counts = recent_weeks_counts.values
        time_steps = np.arange(len(counts))
        slope, p_value_trend, trend_description = None, None, "Not Enough Data"
        
        # Only perform trend analysis if there's a minimum number of events and more than one data point.
        if len(counts) > 1 and counts.sum() >= min_trend_events:
            res = stats.linregress(time_steps, counts)
            slope, p_value_trend = res.slope, res.pvalue
            if p_value_trend < 0.05:
                trend_description = "Significant " + ("Upward" if slope > 0 else "Downward") + " Trend"
            elif p_value_trend < 0.1:
                trend_description = "Potential " + ("Upward" if slope > 0 else "Downward") + " Trend"
            else:
                trend_description = "Not Significant"

        # Convert weekly_counts to a JSON-serializable format (dict with string keys)
        full_weekly_series_dict = {
            ts.strftime('%Y-%m-%d'): count 
            for ts, count in weekly_counts.items()
        }

        slope_val = slope if slope is not None and np.isfinite(slope) else None
        p_val = p_value_trend if p_value_trend is not None and np.isfinite(p_value_trend) else None

        return {
            "model_used": model_choice,
            "historical_weekly_avg": float(historical_avg),
            "historical_weekly_var": float(historical_var),
            "full_weekly_series": full_weekly_series_dict,
            "last_4_weeks_analysis": last_4_weeks_analysis,
            "trend_analysis": {
                "slope": slope_val,
                "p_value": p_val,
                "description": trend_description
            }
        }

    def run(self, df: Optional[pd.DataFrame] = None) -> dict:
        """
        Performs advanced univariate anomaly and trend detection.
        1. Groups data by two columns for localized analysis.
        2. Groups data by the secondary column for city-wide analysis.
        3. For each group, performs anomaly and trend detection.
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

        stage_params = self.config.get('parameters', {}).get(self.name, {})
        
        timestamp_col = stage_params.get('timestamp_col')
        primary_col = stage_params.get('primary_group_col')
        secondary_col = stage_params.get('secondary_group_col')

        if not timestamp_col and self.data_sources: # Fallback
            timestamp_col = self.data_sources[0].get('timestamp_col')
            secondary_col = self.data_sources[0].get('secondary_group_col')

        min_trend_events = stage_params.get('min_trend_events', 4)

        if not primary_col or not secondary_col or not timestamp_col:
            raise ValueError("Missing required parameters: 'timestamp_col', 'primary_group_col', 'secondary_group_col'")

        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        if df.empty:
            return {"status": "success", "stage_name": self.name, "parameters": stage_params, "results": [], "city_wide_results": []}
        
        end_date = df[timestamp_col].max()
        four_weeks_prior = end_date - pd.Timedelta(weeks=4)

        # 1. Localized analysis (by primary and secondary columns)
        localized_results = []
        for (group1, group2), group_df in df.groupby([primary_col, secondary_col]):
            analysis_result = self._analyze_time_series(group_df, timestamp_col, end_date, four_weeks_prior, min_trend_events)
            if analysis_result:
                analysis_result[primary_col] = group1
                analysis_result[secondary_col] = group2
                localized_results.append(analysis_result)

        # 2. City-wide analysis (by secondary column only)
        city_wide_results = []
        for group2, group_df in df.groupby(secondary_col):
            analysis_result = self._analyze_time_series(group_df, timestamp_col, end_date, four_weeks_prior, min_trend_events)
            if analysis_result:
                analysis_result[primary_col] = "City-Wide" # Placeholder
                analysis_result[secondary_col] = group2
                analysis_result['primary_group_name'] = "City-Wide"
                city_wide_results.append(analysis_result)

        output = {
            "status": "success",
            "stage_name": self.name,
            "parameters": stage_params,
            "results": localized_results,
            "city_wide_results": city_wide_results
        }

        self._save_results(output, f"{self.name}.json")
        self.generate_and_save_report(output, df)
        return output
