from .stage3_univariate_anomaly import Stage3UnivariateAnomaly
from .stage4_h3_anomaly import Stage4H3Anomaly

# This map acts as a registry for available analysis stages.
# To add a new stage, import its class and add it to this dictionary.
# The key must match the 'name' property of the stage class.
AVAILABLE_STAGES = {
    "stage3_univariate_anomaly": Stage3UnivariateAnomaly,
    "stage4_h3_anomaly": Stage4H3Anomaly,
}
