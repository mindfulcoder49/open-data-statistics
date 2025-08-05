import matplotlib.pyplot as plt
import pandas as pd
import os
from typing import Optional

def plot_raw_and_aggregated_data(df: pd.DataFrame, timestamp_col: str, output_dir: str) -> str:
    """
    Generates overview plots: weekly counts, and distributions by day of week and hour of day.
    """
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
    
    filename = "plot_initial_aggregation.png"
    filepath = os.path.join(output_dir, filename)
    plt.savefig(filepath)
    plt.close(fig)
    return filename

def plot_comparative_time_series(
    group_series: pd.Series,
    group_name: str,
    city_wide_series: Optional[pd.Series],
    primary_col: str,
    secondary_col: str,
    output_dir: str,
    anomaly_points: Optional[list] = None,
    filename_override: Optional[str] = None
) -> str:
    """
    Generates a plot comparing a specific group's time series to the city-wide equivalent.
    """
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

    if filename_override:
        filename = filename_override
    else:
        safe_primary = "".join(c for c in group_name if c.isalnum())
        safe_secondary = "".join(c for c in secondary_col if c.isalnum())[:50]
        filename = f"plot_compare_{safe_primary}_{safe_secondary}.png"
    
    filepath = os.path.join(output_dir, filename)
    
    plt.savefig(filepath)
    plt.close(fig)
    return filename
