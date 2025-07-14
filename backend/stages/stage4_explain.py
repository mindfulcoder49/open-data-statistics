import pandas as pd
import statsmodels.api as sm
from .base_stage import BaseAnalysisStage
from core.feature_engineering import create_temporal_features

class Stage4Explain(BaseAnalysisStage):
    @property
    def name(self) -> str:
        return "stage4_explain"

    def run(self, df: pd.DataFrame) -> dict:
        """
        Runs the Negative Binomial Regression analysis.
        """
        # 1. Aggregate data to a time series (e.g., daily counts)
        timestamp_col = self.config['timestamp_col']
        df_agg = df.resample('D', on=timestamp_col).size().reset_index(name='incident_count')

        # 2. Engineer Features
        df_with_features = create_temporal_features(df_agg, timestamp_col)

        # 3. Define Model Formula
        dependent_var = 'incident_count'
        # Example: Use features specified in the request, or default
        stage_params = self.config.get('parameters', {}).get(self.name, {})
        independent_vars = stage_params.get('features_to_include', ['is_weekend', 'day_of_week'])

        Y = df_with_features[dependent_var]
        X = df_with_features[independent_vars]
        X = sm.add_constant(X) # Add intercept

        # 4. Fit the Model
        model = sm.GLM(Y, X, family=sm.families.NegativeBinomial())
        results = model.fit()

        # 5. Format the Output
        output = self._format_statsmodels_results(results)

        # 6. Save results (simulation) and return the output dictionary
        self._save_results(output, f"{self.name}.json")
        return output

    def _format_statsmodels_results(self, results) -> dict:
        """
        Parses the statsmodels results object into a clean JSON-serializable dictionary.
        """
        coefficients = []
        for var, param in results.params.items():
            coefficients.append({
                "variable": var,
                "coefficient": param,
                "std_error": results.bse[var],
                "p_value": results.pvalues[var],
            })

        return {
            "status": "success",
            "model_type": "Negative Binomial Regression",
            "summary": {
                "pseudo_r_squared": results.prsquared,
                "log_likelihood": results.llf,
                "aic": results.aic,
            },
            "coefficients": coefficients,
        }
