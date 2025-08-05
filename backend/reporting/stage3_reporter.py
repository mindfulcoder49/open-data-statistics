from .base_reporter import BaseReporter
import pandas as pd
import os
from .visualizations.common import plot_comparative_time_series, plot_raw_and_aggregated_data
from .visualizations.stage3 import plot_anomaly_time_series, plot_trend_time_series
from scipy import stats
import numpy as np
from typing import Optional

class Stage3Reporter(BaseReporter):
    """
    Generates a scholarly HTML report from the Stage 3 Univariate Anomaly results,
    including data visualizations and robust statistical explanations.
    """

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
            initial_plot_filename = plot_raw_and_aggregated_data(df, timestamp_col_name, job_dir)
            report_lines.append(f'<img src="{initial_plot_filename}" alt="Initial Data Aggregation" style="width:100%; max-width:800px;">')
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
                    plot_filename = self._generate_comparative_plot(details, city_wide_data, primary_col_name, secondary_col_name, job_dir)
                    report_lines.append(f'<img src="{plot_filename}" alt="Time series for {sec_group}" style="width:100%; max-width:600px;">')

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
                    plot_filename = self._generate_comparative_plot(details, city_wide_data, primary_col_name, secondary_col_name, job_dir, anomaly_points=[week_details])
                    report_lines.append(f'<img src="{plot_filename}" alt="Time series for {sec_group}" style="width:100%; max-width:600px;">')
                
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

    def _generate_comparative_plot(self, group_data: dict, city_wide_data: Optional[dict], primary_col: str, secondary_col: str, job_dir: str, anomaly_points: Optional[list] = None) -> str:
        """Helper to generate a comparative plot for a given finding."""
        group_series = pd.Series(group_data['full_weekly_series'])
        group_series.index = pd.to_datetime(group_series.index)

        city_wide_series = None
        if city_wide_data and group_data['primary_group_name'] != 'City-Wide':
            city_wide_series = pd.Series(city_wide_data['full_weekly_series'])
            city_wide_series.index = pd.to_datetime(city_wide_series.index)

        return plot_comparative_time_series(
            group_series=group_series,
            group_name=group_data['primary_group_name'],
            city_wide_series=city_wide_series,
            primary_col=primary_col,
            secondary_col=group_data[secondary_col],
            output_dir=job_dir,
            anomaly_points=anomaly_points
        )

    def _generate_plot_for_trend(self, trend_data: dict, primary_col: str, secondary_col: str, job_dir: str) -> str:
        """Helper to generate a plot for a given trend and return the filename."""
        # Reconstruct the weekly counts for plotting from the full series
        weekly_counts = pd.Series(trend_data['full_weekly_series'])
        weekly_counts.index = pd.to_datetime(weekly_counts.index)

        return plot_trend_time_series(
            weekly_counts=weekly_counts,
            trend_analysis=trend_data['trend_analysis'],
            primary_col=f"{primary_col}: {trend_data[primary_col]}",
            secondary_col=trend_data[secondary_col],
            output_dir=job_dir
        )

    def _generate_plot_for_anomaly(self, anomaly_data: dict, primary_col: str, secondary_col: str, job_dir: str) -> str:
        """Helper to generate a plot for a given anomaly and return the filename."""
        row = anomaly_data['details']
        
        # Reconstruct the distribution for plotting
        if row['model_used'].startswith('Poisson'):
            dist = stats.poisson(mu=row['historical_weekly_avg'])
        else:
            var = row['historical_weekly_var']
            avg = row['historical_weekly_avg']
            # Basic safety checks for NB parameter calculation
            if var > avg and avg > 0:
                p = avg / var
                n = avg * p / (1 - p)
                if not (np.isfinite(p) and np.isfinite(n) and 0 < p <= 1 and n > 0):
                     dist = stats.poisson(mu=avg) # Fallback
                else:
                     dist = stats.nbinom(n=n, p=p)
            else:
                dist = stats.poisson(mu=avg) # Fallback

        # Reconstruct the weekly counts for plotting
        weekly_counts = pd.Series(row['full_weekly_series'])
        weekly_counts.index = pd.to_datetime(weekly_counts.index)

        return plot_anomaly_time_series(
            weekly_counts=weekly_counts,
            historical_dist=dist,
            anomaly_points=[anomaly_data['week_details']],
            primary_col=f"{primary_col}: {row[primary_col]}",
            secondary_col=row[secondary_col],
            output_dir=job_dir
        )

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
