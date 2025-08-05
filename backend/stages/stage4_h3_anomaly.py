import pandas as pd
import numpy as np
from scipy import stats
import h3
import os
import json
import re
from .base_stage import BaseAnalysisStage
from reporting.base_reporter import BaseReporter
from reporting.visualizations.common import plot_comparative_time_series
from typing import Optional

class Stage4H3Anomaly(BaseAnalysisStage):
    @property
    def name(self) -> str:
        return "stage4_h3_anomaly"

    def get_reporter(self) -> Optional[BaseReporter]:
        """
        Stage 4 uses a dynamic, client-side viewer instead of a static report.
        Therefore, it does not have a Python-based reporter.
        """
        return None

    def _analyze_time_series(
        self, 
        group_df: pd.DataFrame, 
        timestamp_col: str, 
        end_date: pd.Timestamp, 
        four_weeks_prior: pd.Timestamp,
        min_trend_events: int
    ) -> Optional[dict]:
        """Analyzes a single time series for anomalies and trends. (Copied from Stage 3)"""
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

    def _sanitize_filename(self, name: str) -> str:
        """Removes characters that are invalid for filenames."""
        return re.sub(r'[\\/*?:"<>|]',"", name)

    def run(self, df: pd.DataFrame) -> dict:
        """
        Performs H3-based spatial clustering, then univariate anomaly and trend detection.
        """
        # Check if stage should be skipped
        skip_existing = self.config.get('skip_existing', False)
        output_path = os.path.join(self.job_dir, f"{self.name}.json")
        if skip_existing and os.path.exists(output_path):
            print(f"Skipping stage {self.name} as output already exists.")
            with open(output_path, 'r') as f:
                return json.load(f)

        stage_params = self.config.get('parameters', {}).get(self.name, {})
        timestamp_col = self.config['timestamp_col']
        lat_col = self.config.get('lat_col') # Get from top-level config
        lon_col = self.config.get('lon_col') # Get from top-level config
        h3_resolution = stage_params.get('h3_resolution', 8)
        secondary_col = stage_params.get('secondary_group_col')
        min_trend_events = stage_params.get('min_trend_events', 4)
        filter_col = stage_params.get('filter_col')
        filter_val = stage_params.get('filter_val')

        # Add lat/lon col names to params so reporter can access them
        stage_params['lat_col'] = lat_col
        stage_params['lon_col'] = lon_col

        if not lat_col or not lon_col or not secondary_col:
            raise ValueError("Missing required parameters: 'lat_col', 'lon_col' (in main config) and 'secondary_group_col' (in stage parameters)")

        # Clean column names to remove leading/trailing whitespace
        df.columns = df.columns.str.strip()

        # --- Apply optional filter ---
        if filter_col and filter_val is not None:
            # Sanitize filter column name to match cleaned df columns
            filter_col = filter_col.strip()
            if filter_col not in df.columns:
                raise ValueError(f"Filter column '{filter_col}' not found in the dataset.")
            
            original_rows = len(df)
            # Ensure consistent type for comparison, especially for strings
            df = df[df[filter_col].astype(str) == str(filter_val)]
            print(f"Applied filter: '{filter_col}' == '{filter_val}'. Kept {len(df)} of {original_rows} rows.")

        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        # --- Validate and clean geographic coordinates ---
        df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
        df[lon_col] = pd.to_numeric(df[lon_col], errors='coerce')

        # Drop rows with invalid or out-of-range coordinates
        df.dropna(subset=[lat_col, lon_col], inplace=True)
        df = df[df[lat_col].between(-90, 90) & df[lon_col].between(-180, 180)]
        # Filter out common placeholder values that might be valid but are incorrect for this dataset
        df = df[~((df[lat_col] == 0) & (df[lon_col] == 0))]
        df = df[~((df[lat_col] == -1) & (df[lon_col] == -1))]
        
        if df.empty:
            return {"status": "success", "stage_name": self.name, "parameters": stage_params, "results": [], "city_wide_results": []}

        # Add H3 index column
        h3_col = f"h3_index_{h3_resolution}"
        df[h3_col] = df.apply(lambda row: h3.latlng_to_cell(row[lat_col], row[lon_col], h3_resolution), axis=1)
        
        end_date = df[timestamp_col].max()
        four_weeks_prior = end_date - pd.Timedelta(weeks=4)

        # 1. Localized analysis (by H3 index and secondary column)
        localized_results = []
        for (h3_index, group2), group_df in df.groupby([h3_col, secondary_col]):
            analysis_result = self._analyze_time_series(group_df, timestamp_col, end_date, four_weeks_prior, min_trend_events)
            if analysis_result:
                analysis_result[h3_col] = h3_index
                analysis_result[secondary_col] = group2
                # Add geo-coordinates for the hexagon center
                lat, lon = h3.cell_to_latlng(h3_index)
                analysis_result['lat'] = lat
                analysis_result['lon'] = lon
                localized_results.append(analysis_result)

        # 2. City-wide analysis (by secondary column only)
        city_wide_results = []
        for group2, group_df in df.groupby(secondary_col):
            analysis_result = self._analyze_time_series(group_df, timestamp_col, end_date, four_weeks_prior, min_trend_events)
            if analysis_result:
                analysis_result[secondary_col] = group2
                analysis_result['primary_group_name'] = "City-Wide"
                city_wide_results.append(analysis_result)

        # --- Generate plots for significant findings ---
        p_value_threshold = 0.05
        city_wide_map = {item[secondary_col]: item for item in city_wide_results}
        
        # Use a set to track generated plots to avoid duplicates for a given H3/secondary group combo
        generated_plots = set()

        for result in localized_results:
            sec_group = result[secondary_col]
            h3_index = result[h3_col]
            plot_key = (h3_index, sec_group)

            is_significant_trend = result['trend_analysis']['p_value'] is not None and result['trend_analysis']['p_value'] < p_value_threshold
            significant_anomalies = [week for week in result['last_4_weeks_analysis'] if week['anomaly_p_value'] < p_value_threshold]

            if (is_significant_trend or significant_anomalies) and plot_key not in generated_plots:
                group_series = pd.Series(result['full_weekly_series'])
                group_series.index = pd.to_datetime(group_series.index)
                
                city_wide_data = city_wide_map.get(sec_group)
                city_wide_series = None
                if city_wide_data:
                    city_wide_series = pd.Series(city_wide_data['full_weekly_series'])
                    city_wide_series.index = pd.to_datetime(city_wide_series.index)

                sanitized_sec_group = self._sanitize_filename(sec_group)
                plot_filename = f"plot_{h3_index}_{sanitized_sec_group}.png"

                plot_comparative_time_series(
                    group_series=group_series,
                    group_name=h3_index,
                    city_wide_series=city_wide_series,
                    primary_col="H3 Cell",
                    secondary_col=sec_group,
                    output_dir=self.job_dir,
                    anomaly_points=significant_anomalies,
                    filename_override=plot_filename
                )
                generated_plots.add(plot_key)


        output = {
            "status": "success",
            "stage_name": self.name,
            "parameters": stage_params,
            "results": localized_results,
            "city_wide_results": city_wide_results
        }

        self._save_results(output, f"{self.name}.json")
        # Report generation is now handled by a generic, client-side viewer,
        # so we no longer call generate_and_save_report here.
        # self.generate_and_save_report(output, df)
        return output
