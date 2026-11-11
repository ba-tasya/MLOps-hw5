import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


DROP_COLUMNS = ['transaction_time', 'name_1', 'name_2', 'street']
EARTH_RADIUS = 6371.0


def distance_km(lat1, lon1, lat2, lon2):
    """Reads: client and merchant coordinates.
    Writes: nothing, returns distance in km.
    Rerun is safe: pure calculation, no data is changed.
    """
    lat1, lon1, lat2, lon2 = (np.radians(value) for value in (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)

    return 2 * EARTH_RADIUS * np.arcsin(np.sqrt(a))


def add_time_features(df):
    """Reads: transaction_time column.
    Writes: time feature columns to df.
    Rerun is safe: columns are recalculated from the same data.
    """
    time = pd.to_datetime(df["transaction_time"])

    df["year"] = time.dt.year
    df["month"] = time.dt.month
    df["day"] = time.dt.day
    df["hour"] = time.dt.hour
    df["minute"] = time.dt.minute
    df["day_of_week"] = time.dt.dayofweek
    df["weekend"] = (time.dt.dayofweek >= 5).astype(int)
    df["is_night"] = ((time.dt.hour >= 22) | (time.dt.hour < 6)).astype(int)

    return df


def add_amount_features(df):
    """Reads: amount and population_city columns.
    Writes: log_amount and log_population columns to df.
    Rerun is safe: columns are recalculated from the same data.
    """
    df["log_amount"] = np.log1p(df["amount"])
    df["log_population"] = np.log1p(df["population_city"])

    return df


def add_merchant_features(df):
    """Reads: coordinates and cat_id columns.
    Writes: haversine and is_online columns to df.
    Rerun is safe: columns are recalculated from the same data.
    """
    df["haversine"] = distance_km(df["lat"], df["lon"], df["merchant_lat"], df["merchant_lon"])
    df["is_online"] = df["cat_id"].astype(str).str.endswith("_net").astype(int)

    return df


# Main preprocessing function
def run_preproc(input_df):
    """Reads: raw transactions dataframe.
    Writes: nothing, returns a new dataframe with features.
    Rerun is safe: works on a copy, input data is not changed.
    """
    # Add features
    output_df = input_df.copy()
    output_df = add_time_features(output_df)
    output_df = add_amount_features(output_df)
    output_df = add_merchant_features(output_df)
    output_df = output_df.drop(columns=[column for column in DROP_COLUMNS if column in output_df.columns])
    logger.info('Added new features. Output shape: %s', output_df.shape)

    # Return resulting dataset
    return output_df
