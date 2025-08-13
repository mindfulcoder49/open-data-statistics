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
import time

class Stage4H3Anomaly(BaseAnalysisStage):
    def __init__(self, job_id: str, config: dict, redis_client=None, data_url: str = None):
        super().__init__(job_id, config)
        self.redis_client = redis_client
        self.data_url = data_url

    @property
    def name(self) -> str:
        return "stage4_h3_anomaly"

    def get_reporter(self) -> Optional[BaseReporter]:
        """
        Stage 4 uses a dynamic, client-side viewer instead of a static report.
        Therefore, it does not have a Python-based reporter.
        """
        return None

    def _update_progress(self, progress: int, stage_detail: str):
        """Updates the job progress in Redis if a client is available."""
        if not self.redis_client:
            return
        try:
            status = {
                "status": "processing",
                "current_stage": self.name,
                "progress": progress,
                "stage_detail": stage_detail
            }
            self.redis_client.set(f"job_status:{self.job_id}", json.dumps(status))
        except Exception as e:
            # Log the error but don't fail the stage
            print(f"Warning: Could not update job progress for {self.job_id}: {e}")

    def _analyze_time_series(
        self, 
        group_df: pd.DataFrame, 
        timestamp_col: str, 
        end_date: pd.Timestamp, 
        analysis_weeks_prior: pd.Timestamp,
        min_trend_events: int,
        p_value_trend_threshold: float
    ) -> Optional[dict]:
        """Analyzes a single time series for anomalies and trends. (Copied from Stage 3)"""
        # Resample the full series for the group first
        full_weekly_counts = group_df.resample('W', on=timestamp_col).size()

        # Filter to only include data up to the dataset's end_date
        weekly_counts = full_weekly_counts[full_weekly_counts.index <= end_date]

        # Determine number of weeks for analysis from the date range
        analysis_weeks = (end_date - analysis_weeks_prior).days / 7
        # Need at least 4 weeks of historical data for a stable baseline
        if len(weekly_counts) < analysis_weeks + 4:
            return None

        # Correctly define recent and historical periods based on the global end_date
        recent_weeks_counts = weekly_counts[weekly_counts.index > analysis_weeks_prior]
        historical_counts = weekly_counts[weekly_counts.index <= analysis_weeks_prior]

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
            if p_value_trend < p_value_trend_threshold:
                trend_description = "Significant " + ("Upward" if slope > 0 else "Downward") + " Trend"
            elif p_value_trend < p_value_trend_threshold * 2: # e.g., 0.1 if threshold is 0.05
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

    def run(self) -> dict:
        """
        Performs H3-based spatial clustering, then univariate anomaly and trend detection
        by processing the source file in chunks to minimize memory usage.
        """
        # Check if stage should be skipped
        skip_existing = self.config.get('skip_existing', False)
        output_path = os.path.join(self.job_dir, f"{self.name}.json")
        if skip_existing and os.path.exists(output_path):
            print(f"Skipping stage {self.name} as output already exists.")
            with open(output_path, 'r') as f:
                return json.load(f)

        if not self.data_url:
            raise ValueError("data_url must be provided to Stage4H3Anomaly constructor for chunk-based processing.")

        self._update_progress(0, "Initializing analysis")

        # --- Get Parameters ---
        stage_params = self.config.get('parameters', {}).get(self.name, {})
        timestamp_col = self.config['timestamp_col']
        lat_col = self.config.get('lat_col')
        lon_col = self.config.get('lon_col')
        h3_resolution = stage_params.get('h3_resolution', 8)
        secondary_col = stage_params.get('secondary_group_col')
        min_trend_events = stage_params.get('min_trend_events', 4)
        filter_col = stage_params.get('filter_col')
        filter_values = stage_params.get('filter_values')
        analysis_weeks = stage_params.get('analysis_weeks', 4)
        p_value_anomaly = stage_params.get('p_value_anomaly', 0.05)
        p_value_trend = stage_params.get('p_value_trend', 0.05)
        generate_plots = stage_params.get('generate_plots', True)
        chunksize = stage_params.get('chunksize', 50000)

        stage_params.update({
            'lat_col': lat_col, 'lon_col': lon_col, 'analysis_weeks': analysis_weeks,
            'p_value_anomaly': p_value_anomaly, 'p_value_trend': p_value_trend,
            'generate_plots': generate_plots
        })

        if not lat_col or not lon_col or not secondary_col:
            raise ValueError("Missing required parameters: 'lat_col', 'lon_col', 'secondary_group_col'")

        # --- Chunk Processing ---
        self._update_progress(1, "Starting data aggregation from source file")
        
        localized_weekly_counts = {}
        city_wide_weekly_counts = {}
        end_date = None
        chunk_num = 0

        for chunk_df in pd.read_csv(self.data_url, chunksize=chunksize, iterator=True):
            chunk_num += 1
            self._update_progress(2, f"Processing chunk {chunk_num}")

            # Clean column names
            chunk_df.columns = chunk_df.columns.str.strip()

            # Apply optional filter
            if filter_col and filter_values:
                filter_col_stripped = filter_col.strip()
                if filter_col_stripped in chunk_df.columns:
                    chunk_df = chunk_df[chunk_df[filter_col_stripped].astype(str).isin(filter_values)].copy()

            if chunk_df.empty:
                continue

            # Process timestamp and find the latest date across all chunks
            chunk_df[timestamp_col] = pd.to_datetime(chunk_df[timestamp_col], errors='coerce')
            chunk_df.dropna(subset=[timestamp_col], inplace=True)
            if not chunk_df.empty:
                chunk_max_date = chunk_df[timestamp_col].max()
                if end_date is None or chunk_max_date > end_date:
                    end_date = chunk_max_date

            # Clean geographic coordinates
            chunk_df[lat_col] = pd.to_numeric(chunk_df[lat_col], errors='coerce')
            chunk_df[lon_col] = pd.to_numeric(chunk_df[lon_col], errors='coerce')
            chunk_df.dropna(subset=[lat_col, lon_col], inplace=True)
            chunk_df = chunk_df[chunk_df[lat_col].between(-90, 90) & chunk_df[lon_col].between(-180, 180)]
            chunk_df = chunk_df[~((chunk_df[lat_col] == 0) & (chunk_df[lon_col] == 0))]
            chunk_df = chunk_df[~((chunk_df[lat_col] == -1) & (chunk_df[lon_col] == -1))]

            if chunk_df.empty:
                continue

            # Add H3 index
            h3_col = f"h3_index_{h3_resolution}"
            chunk_df[h3_col] = chunk_df.apply(lambda row: h3.latlng_to_cell(row[lat_col], row[lon_col], h3_resolution), axis=1)

            # --- Aggregate Localized Counts ---
            chunk_localized = chunk_df.groupby([h3_col, secondary_col, pd.Grouper(key=timestamp_col, freq='W')]).size()
            for (h3_idx, sec_grp, week), count in chunk_localized.items():
                key = (h3_idx, sec_grp)
                if key not in localized_weekly_counts:
                    localized_weekly_counts[key] = {}
                localized_weekly_counts[key][week] = localized_weekly_counts[key].get(week, 0) + count

            # --- Aggregate City-Wide Counts ---
            chunk_city_wide = chunk_df.groupby([secondary_col, pd.Grouper(key=timestamp_col, freq='W')]).size()
            for (sec_grp, week), count in chunk_city_wide.items():
                if sec_grp not in city_wide_weekly_counts:
                    city_wide_weekly_counts[sec_grp] = {}
                city_wide_weekly_counts[sec_grp][week] = city_wide_weekly_counts[sec_grp].get(week, 0) + count

        if end_date is None:
            self._update_progress(100, "Completed (No valid data found)")
            return {"status": "success", "stage_name": self.name, "parameters": stage_params, "results": [], "city_wide_results": []}

        analysis_weeks_prior = end_date - pd.Timedelta(weeks=analysis_weeks)
        total_groups = len(localized_weekly_counts) + len(city_wide_weekly_counts)
        processed_groups = 0
        last_update_time = time.time()

        # --- 1. Localized Analysis (from aggregated data) ---
        localized_results = []
        self._update_progress(10, f"Analyzing {len(localized_weekly_counts)} localized groups")
        for (h3_index, group2), weekly_data in localized_weekly_counts.items():
            group_series = pd.Series(weekly_data).sort_index()
            group_df = pd.DataFrame({'timestamp': group_series.index, 'count': group_series.values})
            # Create dummy rows for resample to work correctly
            dummy_df = pd.DataFrame([{'timestamp': ts, 'size': c} for ts, c in weekly_data.items()])

            analysis_result = self._analyze_time_series(dummy_df.rename(columns={'timestamp': timestamp_col, 'size': 'dummy'}), timestamp_col, end_date, analysis_weeks_prior, min_trend_events, p_value_trend)
            if analysis_result:
                analysis_result[h3_col] = h3_index
                analysis_result[secondary_col] = group2
                lat, lon = h3.cell_to_latlng(h3_index)
                analysis_result['lat'] = lat
                analysis_result['lon'] = lon
                localized_results.append(analysis_result)
            
            processed_groups += 1
            current_time = time.time()
            if current_time - last_update_time > 2 or processed_groups % 100 == 0:
                progress = 10 + int(80 * (processed_groups / total_groups))
                self._update_progress(progress, f"Analysis: Processed {processed_groups}/{total_groups} groups")
                last_update_time = current_time

        # --- 2. City-wide Analysis (from aggregated data) ---
        city_wide_results = []
        self._update_progress(90, f"Analyzing {len(city_wide_weekly_counts)} city-wide groups")
        for group2, weekly_data in city_wide_weekly_counts.items():
            dummy_df = pd.DataFrame([{'timestamp': ts, 'size': c} for ts, c in weekly_data.items()])
            analysis_result = self._analyze_time_series(dummy_df.rename(columns={'timestamp': timestamp_col, 'size': 'dummy'}), timestamp_col, end_date, analysis_weeks_prior, min_trend_events, p_value_trend)
            if analysis_result:
                analysis_result[secondary_col] = group2
                analysis_result['primary_group_name'] = "City-Wide"
                city_wide_results.append(analysis_result)
            
            processed_groups += 1
            current_time = time.time()
            if current_time - last_update_time > 2 or processed_groups % 100 == 0:
                progress = 10 + int(80 * (processed_groups / total_groups))
                self._update_progress(progress, f"Analysis: Processed {processed_groups}/{total_groups} groups")
                last_update_time = current_time

        # --- Generate plots for significant findings ---
        if generate_plots:
            self._update_progress(95, "Generating plots for significant findings")
            city_wide_map = {item[secondary_col]: item for item in city_wide_results}
            
            generated_plots = set()
            for result in localized_results:
                sec_group = result[secondary_col]
                h3_index = result[h3_col]
                plot_key = (h3_index, sec_group)

                is_significant_trend = result['trend_analysis']['p_value'] is not None and result['trend_analysis']['p_value'] < p_value_trend
                significant_anomalies = [week for week in result['last_4_weeks_analysis'] if week['anomaly_p_value'] < p_value_anomaly]

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

        self._update_progress(100, "Finalizing results")
        output = {
            "status": "success",
            "stage_name": self.name,
            "parameters": stage_params,
            "results": localized_results,
            "city_wide_results": city_wide_results
        }

        self._save_results(output, f"{self.name}.json")
        return output
