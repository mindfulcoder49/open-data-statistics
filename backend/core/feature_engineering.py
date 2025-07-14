import pandas as pd

def create_temporal_features(df: pd.DataFrame, timestamp_col: str) -> pd.DataFrame:
    """
    Engineers time-based features from a timestamp column.
    """
    df[timestamp_col] = pd.to_datetime(df[timestamp_col])
    df['hour_of_day'] = df[timestamp_col].dt.hour
    df['day_of_week'] = df[timestamp_col].dt.dayofweek
    df['is_weekend'] = (df[timestamp_col].dt.weekday >= 5).astype(int)
    # Add more features as needed
    return df
