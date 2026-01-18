import pandas as pd
import numpy as np
from scipy import stats
import os
import json
import logging
import matplotlib.pyplot as plt
from typing import Optional, Tuple
from core.storage import JsonStorageModel, ImageStorageModel

logger = logging.getLogger(__name__)

# --- Visualization Functions (Updated to return Figure objects instead of saving) ---

def plot_raw_and_aggregated_data(df: pd.DataFrame, timestamp_col: str) -> plt.Figure:
    """Generates overview plots."""
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 18))

    # 1. Plot weekly aggregated data
    weekly_counts = df.resample('W', on=timestamp_col).size()
    ax1.plot(weekly_counts.index, weekly_counts.values, 'o-', label='Weekly Total Incidents', color='teal')
    ax1.set_title("Weekly Aggregated Incident Counts (All Data)", fontsize=14)
    ax1.set_ylabel("Incident Count")
    ax1.legend()
    ax1.tick_params(axis='x', rotation=45)

    # 2. Plot distribution by day of the week
    day_of_week_counts = df[timestamp_col].dt.day_name().value_counts()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_of_week_counts = day_of_week_counts.reindex(days)
    ax2.bar(day_of_week_counts.index, day_of_week_counts.values, color='skyblue')
    ax2.set_title("Total Incidents by Day of Week", fontsize=14)
    ax2.set_ylabel("Total Incident Count")
    ax2.tick_params(axis='x', rotation=45)

    # 3. Plot distribution by hour of the day
    hour_of_day_counts = df[timestamp_col].dt.hour.value_counts().sort_index()
    ax3.bar(hour_of_day_counts.index, hour_of_day_counts.values, color='salmon')
    ax3.set_title("Total Incidents by Hour of Day", fontsize=14)
    ax3.set_xlabel("Hour of Day (0-23)")
    ax3.set_ylabel("Total Incident Count")
    ax3.set_xticks(range(24))

    plt.tight_layout(pad=3.0)
    return fig

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

def plot_trend_time_series(
    weekly_counts: pd.Series,
    trend_analysis: dict,
    primary_col: str,
    secondary_col: str,
    output_dir: str
) -> str:
    """Generates and saves a plot of the time series with a trend line for the last 4 weeks."""
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(weekly_counts.index, weekly_counts.values, 'o-', label='Weekly Counts', color='gray', alpha=0.7)

    if len(weekly_counts.index) >= 4:
        last_4_weeks_start = weekly_counts.index[-4]
        last_4_weeks_end = weekly_counts.index[-1]
        ax.axvspan(last_4_weeks_start, last_4_weeks_end, color='yellow', alpha=0.2, label='Trend Analysis Window')

        recent_counts = weekly_counts.loc[last_4_weeks_start:]
        time_steps = np.arange(len(recent_counts))
        slope = trend_analysis['slope']
        intercept = recent_counts.mean() - slope * np.mean(time_steps)
        trend_line = slope * time_steps + intercept
        ax.plot(recent_counts.index, trend_line, 'r--', label=f"Trend (Slope: {slope:.2f})")

    ax.set_title(f"Weekly Incidents & Trend: {secondary_col}\nin {primary_col}", fontsize=16)
    ax.set_xlabel("Date")
    ax.set_ylabel("Incident Count")
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()

    safe_primary = "".join(c for c in primary_col if c.isalnum())
    safe_secondary = "".join(c for c in secondary_col if c.isalnum())[:50]
    filename = f"plot_trend_{safe_primary}_{safe_secondary}.png"
    filepath = os.path.join(output_dir, filename)
    
    plt.savefig(filepath)
    plt.close(fig)
    return filename

def plot_anomaly_time_series(
    weekly_counts: pd.Series,
    historical_dist,
    anomaly_points: list,
    primary_col: str,
    secondary_col: str,
    output_dir: str
) -> str:
    """Generates and saves a plot of the time series with historical fit and anomalies."""
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(weekly_counts.index, weekly_counts.values, 'o-', label='Weekly Counts', color='gray', alpha=0.7)

    expected_mean = historical_dist.mean()
    ci_upper_bound = historical_dist.ppf(0.95)
    ax.axhline(expected_mean, color='blue', linestyle='--', label=f'Historical Mean ({expected_mean:.2f})')
    ax.axhline(ci_upper_bound, color='red', linestyle=':', label=f'95% Confidence Bound ({ci_upper_bound:.2f})')

    for point in anomaly_points:
        ts = pd.to_datetime(point['week'])
        ax.plot(ts, point['count'], 'ro', markersize=10, label=f"Anomaly on {point['week']}")

    if not weekly_counts.empty:
        last_4_weeks_start = weekly_counts.index[-4] if len(weekly_counts.index) >= 4 else weekly_counts.index[0]
        ax.axvspan(last_4_weeks_start, weekly_counts.index[-1], color='yellow', alpha=0.2, label='Analysis Window')

    ax.set_title(f"Weekly Incidents: {secondary_col}\nin {primary_col}", fontsize=16)
    ax.set_xlabel("Date")
    ax.set_ylabel("Incident Count")
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()

    safe_primary = "".join(c for c in primary_col if c.isalnum())
    safe_secondary = "".join(c for c in secondary_col if c.isalnum())[:50]
    filename = f"plot_{safe_primary}_{safe_secondary}.png"
    filepath = os.path.join(output_dir, filename)
    
    plt.savefig(filepath)
    plt.close(fig)
    return filename

# --- Reporter Class (Consolidated) ---

class Stage3Reporter:
    """
    Generates a scholarly HTML report from the Stage 3 Univariate Anomaly results,
    including data visualizations and robust statistical explanations.
    """
    def __init__(self, job_id, image_storage):
        self.job_id = job_id
        self.image_storage = image_storage

    @property
    def file_extension(self) -> str:
        return "html"

    def generate_report(self, data: dict, df: Optional[pd.DataFrame] = None) -> str:
        params = data.get('parameters', {})
        primary_col_name = params.get('primary_group_col', 'Primary Group')
        secondary_col_name = params.get('secondary_group_col', 'Secondary Group')
        timestamp_col_name = data.get('parameters', {}).get('timestamp_col', self._find_timestamp_col(df))
        results = data.get('results', [])
        city_wide_results = data.get('city_wide_results', [])
        job_dir = os.path.dirname(data.get('__filepath__', '.'))

        if not results and not city_wide_results:
            return "<h1>Scholarly Report on Univariate Time Series Analysis</h1><p>No results were generated.</p>"

        # Combine localized and city-wide results for unified processing
        for r in results:
            r['primary_group_name'] = r[primary_col_name]
        
        report_df = pd.DataFrame(results + city_wide_results)
        
        p_value_threshold = 0.05
        
        report_lines = self._generate_header_and_methodology(primary_col_name, secondary_col_name, p_value_threshold)

        report_lines.append("<h2>2. Analysis by Group</h2>")

        if df is not None and timestamp_col_name:
            report_lines.append("<h3>2.1 Overall Data Overview</h3>")
            report_lines.append("<p>The following plot shows the weekly aggregated counts and distributions by day and hour for the entire dataset. This provides a high-level context for the detailed findings below.</p>")
            
            fig = plot_raw_and_aggregated_data(df, timestamp_col_name)
            filename = "plot_initial_aggregation.png"
            self.image_storage.save_plot(self.job_id, filename, fig)
            
            # In S3 mode, we might need a signed URL, but for now assume relative path works with API proxy
            report_lines.append(f'<img src="results/{filename}" alt="Initial Data Aggregation" style="width:100%; max-width:800px;">')
            report_lines.append("<h3>2.2 Summary of Significant Findings</h3>")
        else:
            report_lines.append("<h3>2.1 Summary of Significant Findings</h3>")

        all_findings = []
        for _, row in report_df.iterrows():
            trend_p = row['trend_analysis']['p_value']
            if trend_p is not None and trend_p < p_value_threshold:
                all_findings.append({'type': 'Trend', 'group': row['primary_group_name'], 'details': row})
            
            for week in row['last_4_weeks_analysis']:
                anomaly_p = week['anomaly_p_value']
                if anomaly_p is not None and anomaly_p < p_value_threshold:
                    if row['historical_weekly_avg'] < 1 and week['count'] == 1:
                        continue
                    finding = {'type': 'Anomaly', 'group': row['primary_group_name'], 'details': row.to_dict(), 'week_details': week}
                    all_findings.append(finding)

        if not all_findings:
            report_lines.append("<p>No statistically significant trends or anomalies were detected.</p>")
        else:
            city_wide_map = {item[secondary_col_name]: item for item in city_wide_results}
            
            # Sort all findings by primary group, then by p-value
            sorted_findings = sorted(all_findings, key=lambda x: (
                x['group'], 
                x['details']['trend_analysis']['p_value'] if x['type'] == 'Trend' else x['week_details']['anomaly_p_value']
            ))

            # --- Generate Summary Table ---
            report_lines.append('<table><thead><tr>'
                                f'<th>{primary_col_name}</th><th>{secondary_col_name}</th><th>Finding Type</th><th>Date/Period</th>'
                                '<th>Details</th><th>P-Value</th><th>Z-Score / Slope</th>'
                                '</tr></thead><tbody>')
            for finding in sorted_findings:
                details = finding['details']
                row_html = f"<tr><td>{details['primary_group_name']}</td><td>{details[secondary_col_name]}</td>"
                if finding['type'] == 'Trend':
                    trend = details['trend_analysis']
                    p_val = trend['p_value']
                    row_html += f"<td>Trend</td><td>Last 4 Weeks</td><td>{trend['description']}</td><td>{p_val:.4g}</td><td>{trend['slope']:.2f}</td>"
                else: # Anomaly
                    week = finding['week_details']
                    p_val = week['anomaly_p_value']
                    row_html += f"<td>Anomaly</td><td>{week['week']}</td><td>Count: {week['count']} (vs avg {details['historical_weekly_avg']:.2f})</td><td>{p_val:.4g}</td><td>{week['z_score']:.2f}</td>"
                row_html += "</tr>"
                report_lines.append(row_html)
            report_lines.append('</tbody></table>')

            # --- Detailed Breakdown, Grouped by Primary Column ---
            if df is not None and timestamp_col_name:
                report_lines.append("<h3>2.3 Detailed Analysis of Findings</h3>")
            else:
                report_lines.append("<h3>2.2 Detailed Analysis of Findings</h3>")

            current_group = None
            for i, finding in enumerate(sorted_findings):
                details = finding['details']
                group_name = details['primary_group_name']
                
                if group_name != current_group:
                    if current_group is not None: report_lines.append("</div>") # Close previous group div
                    report_lines.append(f'<div class="finding-group"><h4>Group: {group_name}</h4>')
                    current_group = group_name

                sec_group = details[secondary_col_name]
                city_wide_data = city_wide_map.get(sec_group)
                
                finding_id = f"finding-{i+1}"
                report_lines.append(f'<div class="finding-card" id="{finding_id}">')

                if finding['type'] == 'Trend':
                    trend_details = details['trend_analysis']
                    p_val = trend_details['p_value']
                    report_lines.append(f"<h5>Finding {i+1}: Trend in '{sec_group}' for {details['primary_group_name']}</h5><ul>")
                    report_lines.append(f"<li><strong>Description</strong>: {trend_details['description']}</li>")
                    report_lines.append(f"<li><strong>Weekly Change (Slope)</strong>: {trend_details['slope']:.2f}</li>")
                    report_lines.append(f"<li><strong>Significance (p-value)</strong>: {p_val:.4g}</li>")
                    
                    if city_wide_data and details['primary_group_name'] != 'City-Wide':
                        cw_trend = city_wide_data['trend_analysis']
                        report_lines.append(f"<li><strong>City-Wide Context</strong>: The trend for '{sec_group}' across all groups is: <strong>{cw_trend['description']}</strong> (p-value: {cw_trend['p_value']:.4g}, slope: {cw_trend['slope']:.2f}).</li>")
                    report_lines.append("</ul>")
                    plot_filename = self._generate_comparative_plot(details, city_wide_data, primary_col_name, secondary_col_name)
                    report_lines.append(f'<img src="results/{plot_filename}" alt="Time series for {sec_group}" style="width:100%; max-width:600px;">')

                else: # Anomaly
                    week_details = finding['week_details']
                    p_val = week_details['anomaly_p_value']
                    report_lines.append(f"<h5>Finding {i+1}: Anomaly in '{sec_group}' for {details['primary_group_name']}</h5><ul>")
                    report_lines.append(f"<li><strong>Date</strong>: {week_details['week']}</li>")
                    report_lines.append(f"<li><strong>Observed Count</strong>: {week_details['count']} (Historical Avg: {details['historical_weekly_avg']:.2f})</li>")
                    report_lines.append(f"<li><strong>Magnitude (Z-Score)</strong>: {week_details['z_score']:.2f}</li>")
                    report_lines.append(f"<li><strong>Significance (p-value)</strong>: {p_val:.4g}</li>")
                    
                    if city_wide_data and details['primary_group_name'] != 'City-Wide':
                        cw_week_data = next((w for w in city_wide_data['last_4_weeks_analysis'] if w['week'] == week_details['week']), None)
                        if cw_week_data:
                            cw_p_val = cw_week_data['anomaly_p_value']
                            status = "significant" if cw_p_val < p_value_threshold else "not significant"
                            report_lines.append(f"<li><strong>City-Wide Context</strong>: The same week was <strong>{status}</strong> for '{sec_group}' across all groups (p-value: {cw_p_val:.4g}).</li>")
                    report_lines.append("</ul>")
                    plot_filename = self._generate_comparative_plot(details, city_wide_data, primary_col_name, secondary_col_name, anomaly_points=[week_details])
                    report_lines.append(f'<img src="results/{plot_filename}" alt="Time series for {sec_group}" style="width:100%; max-width:600px;">')
                
                report_lines.append('</div>') # Close finding-card
            
            if current_group is not None: report_lines.append("</div>") # Close final group div

        report_lines.extend(self._generate_appendix())
        return "\n".join(report_lines)

    def _find_timestamp_col(self, df: Optional[pd.DataFrame]) -> Optional[str]:
        """Helper to find a timestamp column if not explicitly provided."""
        if df is None:
            return None
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                return col
        return None

    def _generate_comparative_plot(self, group_data: dict, city_wide_data: Optional[dict], primary_col: str, secondary_col: str, anomaly_points: Optional[list] = None) -> str:
        """Helper to generate and save a comparative plot."""
        group_series = pd.Series(group_data['full_weekly_series'])
        group_series.index = pd.to_datetime(group_series.index)

        city_wide_series = None
        if city_wide_data and group_data['primary_group_name'] != 'City-Wide':
            city_wide_series = pd.Series(city_wide_data['full_weekly_series'])
            city_wide_series.index = pd.to_datetime(city_wide_series.index)

        fig = plot_comparative_time_series(
            group_series=group_series,
            group_name=group_data['primary_group_name'],
            city_wide_series=city_wide_series,
            primary_col=primary_col,
            secondary_col=group_data[secondary_col],
            anomaly_points=anomaly_points
        )
        
        safe_primary = "".join(c for c in group_data['primary_group_name'] if c.isalnum())
        safe_secondary = "".join(c for c in group_data[secondary_col] if c.isalnum())[:50]
        filename = f"plot_compare_{safe_primary}_{safe_secondary}.png"
        
        self.image_storage.save_plot(self.job_id, filename, fig)
        return filename

    def _generate_header_and_methodology(self, primary_col, secondary_col, p_thresh):
        # Basic CSS for better readability
        style = """
<style>
    body { font-family: sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; }
    h1, h2, h3, h4, h5 { color: #2c3e50; }
    h1 { font-size: 2.5em; }
    h2 { border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; }
    h3 { border-bottom: 1px solid #ecf0f1; padding-bottom: 8px; }
    code { background-color: #ecf0f1; padding: 2px 5px; border-radius: 4px; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 20px; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background-color: #f2f2f2; }
    tr:nth-child(even) { background-color: #f9f9f9; }
    .finding-group { border: 1px solid #ccc; border-radius: 5px; padding: 15px; margin-bottom: 20px; background-color: #fafafa; }
    .finding-card { border: 1px solid #e0e0e0; border-radius: 5px; padding: 15px; margin-bottom: 15px; background-color: #fff; }
    img { margin-top: 10px; }
</style>
"""
        return [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head><meta charset='UTF-8'><title>Univariate Time Series Analysis Report</title>" + style + "</head>",
            "<body>",
            f"<h1>Scholarly Report on Univariate Time Series Analysis</h1>",
            "<h2>Executive Summary</h2>",
            "<p>This report presents a statistical analysis of incident frequency over time, aimed at identifying significant deviations from historical norms (anomalies) and detecting emerging patterns (trends). The dataset was disaggregated into distinct time series based on the categorical variables "
            f"<code>{primary_col}</code> and <code>{secondary_col}</code>. Each resulting time series was modeled and evaluated independently as a separate experiment. This approach is designed to be a comprehensive screening tool, flagging every potential signal for review without applying statistical corrections for multiple comparisons. A noise reduction filter was applied to exclude statistically significant but operationally minor events, such as a single incident occurring in a category that averages less than one event per week. The findings detailed herein represent all events and trends that met the significance threshold, providing a broad set of items for further investigation.</p>",
            "<hr>",
            "<h2>1. Methodology</h2>",
            "The analytical approach comprises several sequential steps: data preparation, model selection, and independent significance testing.",
            "<h3>1.1. Data Preparation and Aggregation</h3>",
            "<p>The raw incident data was first partitioned into subgroups based on unique combinations of the "
            f"<code>{primary_col}</code> and <code>{secondary_col}</code> fields. For each subgroup, a time series was constructed by resampling the data into weekly incident counts. A minimum of eight weeks of data was required for a subgroup to be included in the analysis.</p>",
            "<h3>1.2. Probabilistic Model Selection</h3>",
            "<p>For each time series, a choice was made between the Poisson and Negative Binomial (NB) distributions to model the historical weekly counts. The model selection was based on an empirical test for overdispersion: if the variance of the historical weekly counts was greater than the mean, the more flexible Negative Binomial distribution was chosen. Otherwise, the Poisson model was used.</p>",
            "<h3>1.3. Anomaly and Trend Detection</h3>",
            "<p>Anomalies were identified by calculating an <strong>anomaly p-value</strong> for each of the last four weeks against the fitted historical model. To quantify the magnitude of each anomaly, a <strong>z-score</strong> was also computed. Trends were assessed by fitting a simple linear regression model to the last four weeks of data, yielding a <strong>trend p-value</strong>.</p>",
            "<h3>1.4. Significance Testing</h3>",
            "<p>Each time series for each subgroup is treated as an independent hypothesis test. This analysis intentionally avoids corrections for multiple comparisons (e.g., Bonferroni, FDR) to maximize sensitivity and ensure all potentially significant events are surfaced for review. The goal is to provide a comprehensive screen rather than a confirmatory analysis.</p>"
            f"<p>A conventional significance level (alpha) of <strong>{p_thresh}</strong> is used. A finding is reported as statistically significant if its p-value is less than this threshold.</p>",
            "<h3>1.5. Noise Reduction</h3>",
            "<p>For time series with very low frequency (a historical average of less than one event per week), a single event can be flagged as a statistically significant anomaly. To improve the signal-to-noise ratio of the results, such findings are filtered out. An anomaly is only reported if the observed count is greater than 1, or if the historical average is 1 or greater.</p>"
        ]

    def _generate_appendix(self):
        return [
            "<hr><h2>Appendix: Definition of Terms</h2>",
            "<ul>",
            "<li><strong>Poisson Distribution</strong>: A discrete probability distribution for the counts of events that occur randomly in a given interval of time or space.</li>",
            "<li><strong>Negative Binomial Distribution</strong>: A generalization of the Poisson distribution that allows for overdispersion, where the variance is greater than the mean.</li>",
            "<li><strong>P-value</strong>: The probability of obtaining test results at least as extreme as the results actually observed, under the assumption that the null hypothesis is correct.</li>",
            "<li><strong>Z-score</strong>: A measure of how many standard deviations an observation or data point is from the mean of a distribution. It provides a standardized measure of an anomaly's magnitude.</li>",
            "</ul>",
            "</body></html>"
        ]

# --- Main Stage Class ---

class Stage3UnivariateAnomaly:
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
        return "stage3_univariate_anomaly"

    def get_reporter(self) -> Optional[object]:
        return Stage3Reporter(self.job_id, self.image_storage)

    def generate_and_save_report(self, results: dict, df: pd.DataFrame):
        """Generates and saves the report for the stage, if a reporter is available."""
        reporter = self.get_reporter()
        if reporter:
            # Add filepath to results so reporter knows where to save images
            results['__filepath__'] = os.path.join(self.job_dir, f"{self.name}.json")
            
            report_content = reporter.generate_report(results, df)
            report_filename = f"report_{self.name}.html"
            # For simplicity, I'll use the backend from JsonStorageModel.
            self.json_storage.backend.save_bytes(f"{self.job_id}/{report_filename}", report_content.encode('utf-8'))

    def _analyze_time_series(
        self, 
        group_df: pd.DataFrame, 
        timestamp_col: str, 
        end_date: pd.Timestamp, 
        four_weeks_prior: pd.Timestamp,
        min_trend_events: int,
        group_identifiers: tuple
    ) -> Optional[dict]:
        """Analyzes a single time series for anomalies and trends."""
        # Resample the full series for the group first
        full_weekly_counts = group_df.resample('W', on=timestamp_col).size()

        # Filter to only include data up to the dataset's end_date
        weekly_counts = full_weekly_counts[full_weekly_counts.index <= end_date]

        # Need at least 8 weeks of data for stable history and 4 weeks of trend
        if len(weekly_counts) < 8:
            logger.debug(f"[{self.job_id}] Skipping group {group_identifiers}: not enough data for analysis (found {len(weekly_counts)} weeks, require 8).")
            return None

        # Correctly define recent and historical periods based on the global end_date
        recent_weeks_counts = weekly_counts[weekly_counts.index > four_weeks_prior]
        historical_counts = weekly_counts[weekly_counts.index <= four_weeks_prior]

        if historical_counts.sum() == 0: # Skip groups with no historical data
            logger.debug(f"[{self.job_id}] Skipping group {group_identifiers}: no historical data to model.")
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
        else:
            logger.debug(f"[{self.job_id}] Skipping trend analysis for group {group_identifiers}: not enough data points or events for trend detection.")

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
            analysis_result = self._analyze_time_series(group_df, timestamp_col, end_date, four_weeks_prior, min_trend_events, (group1, group2))
            if analysis_result:
                analysis_result[primary_col] = group1
                analysis_result[secondary_col] = group2
                localized_results.append(analysis_result)

        # 2. City-wide analysis (by secondary column only)
        city_wide_results = []
        for group2, group_df in df.groupby(secondary_col):
            analysis_result = self._analyze_time_series(group_df, timestamp_col, end_date, four_weeks_prior, min_trend_events, (group2,))
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
