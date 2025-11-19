import pandas as pd
import os
from typing import Optional

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
        template_path = os.path.join(os.path.dirname(__file__), 'templates', 'stage4_report_template.html')

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
