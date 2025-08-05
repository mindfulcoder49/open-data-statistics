import matplotlib.pyplot as plt
import pandas as pd
import os
import numpy as np

def plot_trend_time_series(
    weekly_counts: pd.Series,
    trend_analysis: dict,
    primary_col: str,
    secondary_col: str,
    output_dir: str
) -> str:
    """
    Generates and saves a plot of the time series with a trend line for the last 4 weeks.
    """
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
    """
    Generates and saves a plot of the time series with historical fit and anomalies.
    """
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
