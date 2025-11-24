import pandas as pd
import numpy as np
from scipy import stats
import h3
import os
import json
import re
import matplotlib.pyplot as plt
from typing import Optional, List
import time
import tempfile
from itertools import groupby
from core.storage import JsonStorageModel, ImageStorageModel

# --- Visualization Functions (Consolidated) ---

def plot_comparative_time_series(
    group_series: pd.Series,
    group_name: str,
    city_wide_series: Optional[pd.Series],
    primary_col: str,
    secondary_col: str,
    anomaly_points: Optional[list] = None
) -> plt.Figure:
    """Generates a plot comparing a specific group's time series to the city-wide equivalent."""
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(15, 7))

    # Plot the specific group's data
    ax.plot(group_series.index, group_series.values, 'o-', label=f'{primary_col}: {group_name}', color='blue', linewidth=2)

    # If city-wide data is available, plot it on a secondary y-axis
    if city_wide_series is not None:
        ax2 = ax.twinx()
        ax2.plot(city_wide_series.index, city_wide_series.values, 's--', label='City-Wide', color='gray', alpha=0.7)
        ax.set_ylabel(f'Incident Count ({group_name})', color='blue')
        ax2.set_ylabel('Incident Count (City-Wide)', color='gray')
        ax.tick_params(axis='y', labelcolor='blue')
        ax2.tick_params(axis='y', labelcolor='gray')
        lines, labels = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax2.legend(lines + lines2, labels + labels2, loc=0)
    else:
        ax.set_ylabel('Incident Count')
        ax.legend(loc=0)

    # Highlight anomalous points on the primary series
    if anomaly_points:
        for point in anomaly_points:
            ts = pd.to_datetime(point['week'])
            y_value = point.get('deseasonalized_count', point.get('count'))
            if y_value is not None:
                ax.plot(ts, y_value, 'ro', markersize=12, alpha=0.8, label=f"Anomaly on {point['week']}")

    ax.set_title(f"Comparison for '{secondary_col}': {group_name} vs. City-Wide", fontsize=16)
    ax.set_xlabel("Date")
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig

# --- Reporter Class (Consolidated) ---

class Stage4Reporter:
    """
    Generates an HTML report for Stage 4 by populating a static template
    which uses JavaScript to load and render the results dynamically.
    """

    @property
    def file_extension(self) -> str:
        return "html"

    def generate_report(self, data: dict, df: Optional[pd.DataFrame] = None) -> str:
        params = data.get('parameters', {})
        h3_resolution = params.get('h3_resolution', 'N/A')
        secondary_col_name = params.get('secondary_group_col', 'Secondary Group')
        p_value_threshold = 0.05

        # Determine the path to the template file
        # Assumes the template is in a 'templates' subdirectory next to this file
        # Since we moved the reporter to stages/, we need to adjust the path or assume templates are in backend/reporting/templates
        # For now, let's assume the templates folder is still in reporting/templates
        template_path = os.path.join(os.path.dirname(__file__), '..', 'reporting', 'templates', 'stage4_report_template.html')

        try:
            with open(template_path, 'r') as f:
                template_str = f.read()
        except FileNotFoundError:
            return "<h1>Error</h1><p>Report template not found.</p>"

        # Generate methodology and appendix content
        methodology = self._generate_methodology(secondary_col_name, h3_resolution, p_value_threshold)
        appendix = self._generate_appendix()

        # Replace placeholders in the template
        report_content = template_str.replace('{{METHODOLOGY}}', "\n".join(methodology))
        report_content = report_content.replace('{{APPENDIX}}', "\n".join(appendix))

        return report_content

    def _generate_methodology(self, secondary_col, h3_res, p_thresh):
        return [
            "<h2>1. Methodology</h2>",
            "The analytical approach comprises several sequential steps: spatial aggregation, data preparation, model selection, and independent significance testing.",
            "<h3>1.1. Spatial Aggregation and Data Preparation</h3>",
            f"<p>Raw incident data points were assigned to a hexagonal H3 cell based on their latitude and longitude coordinates, using H3 resolution <code>{h3_res}</code>. The data was then further partitioned into subgroups based on unique combinations of the H3 cell and the "
            f"<code>{secondary_col}</code> field. For each subgroup, a time series was constructed by resampling the data into weekly incident counts. A minimum of eight weeks of data was required for a subgroup to be included in the analysis.</p>",
            "<h3>1.2. Probabilistic Model Selection and Anomaly/Trend Detection</h3>",
            "<p>The methodology for model selection (Poisson vs. Negative Binomial), anomaly detection (p-value and z-score for the last four weeks), and trend detection (linear regression on the last four weeks) is identical to that used in the standard univariate analysis. Please refer to that report for detailed descriptions.</p>",
            "<h3>1.3. Significance Testing and Noise Reduction</h3>",
            f"<p>Each time series is treated as an independent hypothesis test. A conventional significance level (alpha) of <strong>{p_thresh}</strong> is used. A finding is reported as statistically significant if its p-value is less than this threshold. To reduce noise, anomalies are only reported for low-frequency series if the observed count is greater than 1.</p>"
        ]

    def _generate_appendix(self):
        return [
            "<hr><h2>Appendix: Definition of Terms</h2>",
            "<ul>",
            "<li><strong>H3</strong>: A geospatial indexing system that partitions the world into hexagonal cells. It allows for efficient spatial analysis at various resolutions.</li>",
            "<li><strong>Leaflet.js</strong>: An open-source JavaScript library for mobile-friendly interactive maps.</li>",
            "<li><strong>Poisson Distribution</strong>: A discrete probability distribution for the counts of events that occur randomly in a given interval of time or space.</li>",
            "<li><strong>Negative Binomial Distribution</strong>: A generalization of the Poisson distribution that allows for overdispersion, where the variance is greater than the mean.</li>",
            "<li><strong>P-value</strong>: The probability of obtaining test results at least as extreme as the results actually observed, under the assumption that the null hypothesis is correct.</li>",
            "<li><strong>Z-score</strong>: A measure of how many standard deviations an observation or data point is from the mean of a distribution. It provides a standardized measure of an anomaly's magnitude.</li>",
            "</ul>"
        ]

# --- Main Stage Class ---

class Stage4H3Anomaly:
    def __init__(self, job_id: str, config: dict, results_dir: str, redis_client=None, data_sources: list = None):
        self.job_id = job_id
        self.config = config
        self.redis_client = redis_client
        self.data_sources = data_sources
        self.job_dir = os.path.join(results_dir, self.job_id)
        os.makedirs(self.job_dir, exist_ok=True)
        self.json_storage = JsonStorageModel()
        self.image_storage = ImageStorageModel()

    @property
    def name(self) -> str:
        return "stage4_h3_anomaly"

    def get_reporter(self) -> Optional[object]:
        """
        Stage 4 uses a dynamic, client-side viewer instead of a static report.
        However, we provide the reporter class here for consistency.
        """
        return Stage4Reporter()

    def _save_results(self, results: dict, filename: str) -> str:
        """
        Helper method to save a dictionary as JSON to the local results directory.
        Returns the path to the saved file.
        """
        print(f"Saving results for job {self.job_id} to storage: {filename}")
        return self.json_storage.save(self.job_id, filename, results)

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
        analysis_weeks_trend: List[int],
        analysis_weeks_anomaly: int,
        min_trend_events: int,
        p_value_trend_threshold: float
    ) -> Optional[dict]:
        """Analyzes a single time series for anomalies and trends. (Copied from Stage 3)"""
        # --- FIX: Handle pre-aggregated data vs. raw event data ---
        # If a 'count' column exists, we are working with pre-aggregated data and must sum it.
        # Otherwise, we are working with raw events and must count the rows (.size()).
        if 'count' in group_df.columns:
            full_weekly_counts = group_df.resample('W', on=timestamp_col)['count'].sum()
        else:
            full_weekly_counts = group_df.resample('W', on=timestamp_col).size()

        # Filter to only include data up to the dataset's end_date
        weekly_counts = full_weekly_counts[full_weekly_counts.index <= end_date]

        # Determine the historical period based on the longer of the two analysis windows
        max_analysis_weeks = max(max(analysis_weeks_trend), analysis_weeks_anomaly)
        
        # Need at least 4 weeks of historical data for a stable baseline
        if len(weekly_counts) < max_analysis_weeks + 4:
            return None

        # Define historical vs. recent periods
        historical_period_end_date = end_date - pd.Timedelta(weeks=max_analysis_weeks)
        historical_counts = weekly_counts[weekly_counts.index <= historical_period_end_date]

        if historical_counts.sum() == 0: # Skip groups with no historical data
            return None

        # Define the specific "recent" windows for anomaly and trend detection
        anomaly_period_start_date = end_date - pd.Timedelta(weeks=analysis_weeks_anomaly)
        recent_anomaly_counts = weekly_counts[weekly_counts.index > anomaly_period_start_date]

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

        # --- Anomaly Detection for the specified anomaly window ---
        anomaly_analysis_results = []
        for week_timestamp, count in recent_anomaly_counts.items():
            # p-value is P(X >= count), calculated using the survival function P(X > count-1)
            p_value = dist.sf(count - 1) if count > 0 else 1.0
            
            # Calculate z-score for effect size
            mean = dist.mean()
            std_dev = dist.std()
            z_score = (count - mean) / std_dev if std_dev > 0 else 0

            anomaly_analysis_results.append({
                "week": week_timestamp.strftime('%Y-%m-%d'),
                "count": int(count),
                "anomaly_p_value": float(p_value),
                "z_score": float(z_score)
            })

        # --- Trend Detection on the specified trend window ---
        trend_analysis_results = {}
        for trend_weeks in sorted(analysis_weeks_trend):
            trend_period_start_date = end_date - pd.Timedelta(weeks=trend_weeks)
            recent_trend_counts = weekly_counts[weekly_counts.index > trend_period_start_date]

            counts = recent_trend_counts.values
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
            
            slope_val = slope if slope is not None and np.isfinite(slope) else None
            p_val = p_value_trend if p_value_trend is not None and np.isfinite(p_value_trend) else None

            trend_analysis_results[f"{trend_weeks}_weeks"] = {
                "slope": slope_val,
                "p_value": p_val,
                "description": trend_description
            }

        # Convert weekly_counts to a JSON-serializable format (dict with string keys)
        full_weekly_series_dict = {
            ts.strftime('%Y-%m-%d'): int(count) 
            for ts, count in weekly_counts.items()
        }

        return {
            "model_used": model_choice,
            "historical_weekly_avg": float(historical_avg),
            "historical_weekly_var": float(historical_var),
            "full_weekly_series": full_weekly_series_dict,
            "anomaly_analysis": anomaly_analysis_results,
            "trend_analysis": trend_analysis_results
        }

    def _sanitize_filename(self, name: str) -> str:
        """Removes characters that are invalid for filenames."""
        return re.sub(r'[\\/*?:"<>|]',"", name)

    def run(self, df: Optional[pd.DataFrame] = None) -> dict:
        """
        Performs H3-based spatial clustering, then univariate anomaly and trend detection
        by processing the source files in chunks and streaming results to disk to minimize memory usage.
        The 'df' parameter is ignored in this stage.
        """
        # Check if stage should be skipped
        skip_existing = self.config.get('skip_existing', False)
        filename = f"{self.name}.json"
        if skip_existing and self.json_storage.exists(self.job_id, filename):
            print(f"Skipping stage {self.name} as output already exists.")
            return self.json_storage.load(self.job_id, filename)

        if not self.data_sources:
            raise ValueError("data_sources list must be provided to Stage4H3Anomaly constructor for multi-file processing.")

        self._update_progress(0, "Initializing analysis")

        # --- Get Parameters ---
        stage_params = self.config.get('parameters', {}).get(self.name, {})
        h3_resolution = stage_params.get('h3_resolution', 8)
        min_trend_events = stage_params.get('min_trend_events', 4)
        filter_col = stage_params.get('filter_col')
        filter_values = stage_params.get('filter_values')
        analysis_weeks_trend = stage_params.get('analysis_weeks_trend', [4])
        analysis_weeks_anomaly = stage_params.get('analysis_weeks_anomaly', 4)
        p_value_anomaly = stage_params.get('p_value_anomaly', 0.05)
        p_value_trend = stage_params.get('p_value_trend', 0.05)
        plot_generation = stage_params.get('plot_generation', 'both') # Replaces generate_plots
        save_full_series = stage_params.get('save_full_series', False)
        chunksize = stage_params.get('chunksize', 50000)

        # We no longer get column names from global config, they are per-source.
        # We store the other params for the report.
        stage_params.update({
            'analysis_weeks_trend': analysis_weeks_trend,
            'analysis_weeks_anomaly': analysis_weeks_anomaly,
            'p_value_anomaly': p_value_anomaly,
            'p_value_trend': p_value_trend,
            'plot_generation': plot_generation,
            'save_full_series': save_full_series
        })

        # --- Create a temporary file for disk-based aggregation ---
        # We keep this local because it's an intermediate processing step, not a final result
        temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv', dir=self.job_dir)
        temp_filename = temp_file.name
        # Write header for the temp file
        temp_file.write("h3_index,secondary_group,week,count\n")
        
        end_date = None
        total_files = len(self.data_sources)
        
        try:
            # --- PASS 1: AGGREGATE TO DISK ---
            self._update_progress(1, "Starting data aggregation to temporary file")
            
            for file_idx, source_config in enumerate(self.data_sources):
                data_url = source_config['data_url']
                timestamp_col = source_config['timestamp_col']
                lat_col = source_config['lat_col']
                lon_col = source_config['lon_col']
                secondary_col = source_config['secondary_group_col']
                
                file_name = data_url.split('/')[-1]
                self._update_progress(
                    int(5 + 40 * (file_idx / total_files)), 
                    f"Aggregating file {file_idx + 1}/{total_files}: {file_name}"
                )

                for chunk_df in pd.read_csv(data_url, chunksize=chunksize, iterator=True, low_memory=False):
                    chunk_df.columns = chunk_df.columns.str.strip()

                    rename_map = {
                        timestamp_col: '__timestamp',
                        lat_col: '__lat',
                        lon_col: '__lon',
                        secondary_col: '__secondary_group'
                    }
                    if not all(col in chunk_df.columns for col in rename_map.keys()):
                        print(f"Skipping chunk in {file_name} due to missing columns.")
                        continue
                    
                    chunk_df = chunk_df.rename(columns=rename_map)

                    if filter_col and filter_values:
                        if '__secondary_group' in chunk_df.columns:
                            chunk_df = chunk_df[chunk_df['__secondary_group'].astype(str).isin(filter_values)].copy()

                    if chunk_df.empty:
                        continue

                    chunk_df['__timestamp'] = pd.to_datetime(chunk_df['__timestamp'], errors='coerce')
                    chunk_df.dropna(subset=['__timestamp'], inplace=True)
                    if not chunk_df.empty:
                        chunk_max_date = chunk_df['__timestamp'].max()
                        if end_date is None or chunk_max_date > end_date:
                            end_date = chunk_max_date

                    chunk_df['__lat'] = pd.to_numeric(chunk_df['__lat'], errors='coerce')
                    chunk_df['__lon'] = pd.to_numeric(chunk_df['__lon'], errors='coerce')
                    chunk_df.dropna(subset=['__lat', '__lon'], inplace=True)
                    chunk_df = chunk_df[chunk_df['__lat'].between(-90, 90) & chunk_df['__lon'].between(-180, 180)]
                    chunk_df = chunk_df[~((chunk_df['__lat'] == 0) & (chunk_df['__lon'] == 0))]
                    chunk_df = chunk_df[~((chunk_df['__lat'] == -1) & (chunk_df['__lon'] == -1))]

                    if chunk_df.empty:
                        continue

                    h3_col = f"h3_index_{h3_resolution}"
                    chunk_df[h3_col] = chunk_df.apply(lambda row: h3.latlng_to_cell(row['__lat'], row['__lon'], h3_resolution), axis=1)

                    # Aggregate and write localized counts
                    chunk_localized = chunk_df.groupby([h3_col, '__secondary_group', pd.Grouper(key='__timestamp', freq='W')]).size().reset_index(name='count')
                    chunk_localized.rename(columns={h3_col: 'h3_index', '__secondary_group': 'secondary_group', '__timestamp': 'week'}, inplace=True)
                    chunk_localized.to_csv(temp_file, mode='a', header=False, index=False)

                    # Aggregate and write city-wide counts (using a placeholder for h3_index)
                    chunk_city_wide = chunk_df.groupby(['__secondary_group', pd.Grouper(key='__timestamp', freq='W')]).size().reset_index(name='count')
                    chunk_city_wide['h3_index'] = 'city-wide'
                    chunk_city_wide.rename(columns={'__secondary_group': 'secondary_group', '__timestamp': 'week'}, inplace=True)
                    chunk_city_wide[['h3_index', 'secondary_group', 'week', 'count']].to_csv(temp_file, mode='a', header=False, index=False)

            temp_file.close() # Close the file to ensure all writes are flushed

            if end_date is None:
                self._update_progress(100, "Completed (No valid data found)")
                final_output = {"status": "success", "stage_name": self.name, "parameters": stage_params, "results": [], "city_wide_results": []}
                self._save_results(final_output, f"{self.name}.json")
                return final_output

            # --- PASS 2: ANALYZE FROM DISK ---
            self._update_progress(50, "Aggregating unique groups and analyzing")
            
            agg_df = pd.read_csv(temp_filename)
            final_counts_df = agg_df.groupby(['h3_index', 'secondary_group', 'week'])['count'].sum().reset_index()
            final_counts_df['week'] = pd.to_datetime(final_counts_df['week'])

            localized_groups = final_counts_df[final_counts_df['h3_index'] != 'city-wide'].groupby(['h3_index', 'secondary_group'])
            city_wide_groups = final_counts_df[final_counts_df['h3_index'] == 'city-wide'].groupby('secondary_group')
            
            # Instead of streaming to a file, we build the result object in memory to pass to JsonStorageModel
            # This supports the abstraction requirement (e.g. saving to DB later)
            final_results_list = []
            city_wide_results_list = []
            localized_results_for_plotting = []

            total_groups = len(localized_groups) + len(city_wide_groups)
            processed_groups = 0
            last_update_time = time.time()

            self._update_progress(55, f"Analyzing {len(localized_groups)} localized groups")
            for (h3_index, group2), group_df in localized_groups:
                analysis_result = self._analyze_time_series(
                    group_df.rename(columns={'week': '__timestamp'}), '__timestamp', end_date, 
                    analysis_weeks_trend, analysis_weeks_anomaly, min_trend_events, p_value_trend
                )
                
                if analysis_result:
                    analysis_result[f"h3_index_{h3_resolution}"] = h3_index
                    # Ensure secondary group is a native Python type
                    analysis_result['secondary_group'] = group2.item() if isinstance(group2, np.generic) else group2
                    lat, lon = h3.cell_to_latlng(h3_index)
                    analysis_result['lat'] = lat
                    analysis_result['lon'] = lon
                    
                    result_to_save = analysis_result.copy()
                    if not save_full_series:
                        del result_to_save['full_weekly_series']

                    final_results_list.append(result_to_save)
                    localized_results_for_plotting.append(analysis_result)

                processed_groups += 1
                current_time = time.time()
                if current_time - last_update_time > 2 or processed_groups % 100 == 0:
                    progress = 55 + int(40 * (processed_groups / total_groups))
                    self._update_progress(progress, f"Analysis: Processed {processed_groups}/{total_groups} groups")
                    last_update_time = current_time
            
            self._update_progress(95, f"Analyzing {len(city_wide_groups)} city-wide groups")
            for group2, group_df in city_wide_groups:
                analysis_result = self._analyze_time_series(
                    group_df.rename(columns={'week': '__timestamp'}), '__timestamp', end_date, 
                    analysis_weeks_trend, analysis_weeks_anomaly, min_trend_events, p_value_trend
                )
                if analysis_result:
                    # Ensure secondary group is a native Python type
                    analysis_result['secondary_group'] = group2.item() if isinstance(group2, np.generic) else group2
                    analysis_result['primary_group_name'] = "City-Wide"
                    city_wide_results_list.append(analysis_result)
                    
                    result_to_save = analysis_result.copy()
                    if not save_full_series:
                        del result_to_save['full_weekly_series']

            # --- Generate plots for significant findings ---
            if plot_generation != 'none':
                self._update_progress(98, "Generating plots for significant findings")
                city_wide_map = {item['secondary_group']: item for item in city_wide_results_list}
                
                generated_plots = set()
                h3_col = f"h3_index_{h3_resolution}"
                for result in localized_results_for_plotting:
                    sec_group = result['secondary_group']
                    h3_index = result[h3_col]
                    plot_key = (h3_index, sec_group)

                    is_significant_trend = False
                    if 'trend_analysis' in result and isinstance(result['trend_analysis'], dict):
                        for trend_result in result['trend_analysis'].values():
                            if trend_result.get('p_value') is not None and trend_result['p_value'] < p_value_trend:
                                is_significant_trend = True
                                break
                    
                    significant_anomalies = [week for week in result['anomaly_analysis'] if week['anomaly_p_value'] < p_value_anomaly]

                    # Determine if a plot should be generated based on the new setting
                    should_plot = False
                    if plot_generation == 'both' and (is_significant_trend or significant_anomalies):
                        should_plot = True
                    elif plot_generation == 'trends' and is_significant_trend:
                        should_plot = True
                    elif plot_generation == 'anomalies' and significant_anomalies:
                        should_plot = True

                    if should_plot and plot_key not in generated_plots:
                        group_series = pd.Series(result['full_weekly_series'])
                        group_series.index = pd.to_datetime(group_series.index)
                    
                        city_wide_data = city_wide_map.get(sec_group)
                        city_wide_series = None
                        if city_wide_data:
                            city_wide_series = pd.Series(city_wide_data['full_weekly_series'])
                            city_wide_series.index = pd.to_datetime(city_wide_series.index)

                        sanitized_sec_group = self._sanitize_filename(str(sec_group))
                        plot_filename = f"plot_{h3_index}_{sanitized_sec_group}.png"

                        fig = plot_comparative_time_series(
                            group_series=group_series,
                            group_name=h3_index,
                            city_wide_series=city_wide_series,
                            primary_col="H3 Cell",
                            secondary_col=sec_group,
                            anomaly_points=significant_anomalies
                        )
                        self.image_storage.save_plot(self.job_id, plot_filename, fig)
                        generated_plots.add(plot_key)

            self._update_progress(100, "Finalizing results")
            
            final_output = {
                "status": "success",
                "stage_name": self.name,
                "parameters": stage_params,
                "results": final_results_list,
                "city_wide_results": city_wide_results_list
            }
            self._save_results(final_output, f"{self.name}.json")
            return final_output

        finally:
            # --- Cleanup ---
            # Ensure the temporary file is deleted
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
