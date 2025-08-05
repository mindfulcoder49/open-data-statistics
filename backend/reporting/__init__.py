from .stage3_reporter import Stage3Reporter
from .stage4_reporter import Stage4Reporter

# This map acts as a registry for available report generators.
# To add a new reporter, import it and add it to this dictionary.
# The key should match the stage_name from the analysis pipeline.
AVAILABLE_REPORTERS = {
    "stage3_univariate_anomaly": Stage3Reporter,
    "stage4_h3_anomaly": Stage4Reporter,
}
