"""Feature engineering for the behavioral model.

Ported from the ML project (ML/features.py). The saved models in `ml_models/` were trained on exactly
these columns, so any change here requires retraining (POST /api/ml/train or scripts/train_model.py).
"""
import numpy as np
import pandas as pd

NUMERIC_FEATURES = [
    "amount", "amount_log", "tenor_days", "tenor_months",
    "interest_rate", "market_interest_rate", "rate_difference", "rate_difference_abs", "rate_ratio",
    "client_rating",
    "transaction_year", "transaction_month", "transaction_quarter", "transaction_dayofweek",
    "maturity_month", "maturity_quarter",
]
CATEGORICAL_FEATURES = [
    "customer_segment", "product_type", "location", "entity", "currency",
    "customer_segment_product", "location_segment", "product_rating",
]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Input columns the feature builder needs (historical log names; live books are mapped onto these).
REQUIRED_COLUMNS = [
    "transaction_date", "contractual_maturity_date", "amount", "interest_rate_pct", "market_interest_rate_pct",
    "client_rating", "customer_segment", "product_type", "location", "entity", "currency",
]

# Readable groups used to explain a prediction (problem statement: tenor, market rate, rate difference, amount).
DRIVER_GROUPS: dict[str, list[str]] = {
    "Tenor": ["tenor_days", "tenor_months"],
    "Market rate": ["market_interest_rate"],
    "Interest rate difference": ["interest_rate", "rate_difference", "rate_difference_abs", "rate_ratio"],
    "Amount": ["amount", "amount_log"],
    "Client rating": ["client_rating"],
    "Product and segment": ["customer_segment", "product_type", "customer_segment_product", "product_rating"],
    "Location and currency": ["location", "entity", "currency", "location_segment"],
    "Booking and maturity timing": [
        "transaction_year", "transaction_month", "transaction_quarter", "transaction_dayofweek",
        "maturity_month", "maturity_quarter",
    ],
}
FEATURE_TO_GROUP = {f: g for g, features in DRIVER_GROUPS.items() for f in features}


def create_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    df["contractual_maturity_date"] = pd.to_datetime(df["contractual_maturity_date"], errors="coerce")

    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["interest_rate"] = pd.to_numeric(df["interest_rate_pct"], errors="coerce")
    df["market_interest_rate"] = pd.to_numeric(df["market_interest_rate_pct"], errors="coerce")
    df["client_rating"] = pd.to_numeric(df["client_rating"], errors="coerce")

    df["tenor_days"] = (df["contractual_maturity_date"] - df["transaction_date"]).dt.days
    df["tenor_months"] = df["tenor_days"] / 30.44
    df["amount_log"] = np.log1p(df["amount"].clip(lower=0))

    df["rate_difference"] = df["market_interest_rate"] - df["interest_rate"]
    df["rate_difference_abs"] = df["rate_difference"].abs()
    df["rate_ratio"] = np.where(df["interest_rate"] != 0, df["market_interest_rate"] / df["interest_rate"], 0)

    df["transaction_year"] = df["transaction_date"].dt.year
    df["transaction_month"] = df["transaction_date"].dt.month
    df["transaction_quarter"] = df["transaction_date"].dt.quarter
    df["transaction_dayofweek"] = df["transaction_date"].dt.dayofweek
    df["maturity_month"] = df["contractual_maturity_date"].dt.month
    df["maturity_quarter"] = df["contractual_maturity_date"].dt.quarter

    for column in ("customer_segment", "product_type", "location", "entity", "currency"):
        df[column] = df[column].astype(str).str.strip()

    df["customer_segment_product"] = df["customer_segment"] + "_" + df["product_type"]
    df["location_segment"] = df["location"] + "_" + df["customer_segment"]
    df["product_rating"] = df["product_type"] + "_" + df["client_rating"].astype(str)

    df[NUMERIC_FEATURES] = df[NUMERIC_FEATURES].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    for column in NUMERIC_FEATURES:
        if df[column].isna().any():
            df[column] = df[column].fillna(df[column].median())
    for column in CATEGORICAL_FEATURES:
        df[column] = df[column].astype(str).replace("nan", "Unknown")
    return df


def create_target(df: pd.DataFrame) -> pd.DataFrame:
    """Keep closed contracts only and flag those closed before contractual maturity."""
    df = df[df["actual_closure_date"].notna()].copy()
    closure = pd.to_datetime(df["actual_closure_date"])
    df["early_exit"] = (closure < pd.to_datetime(df["contractual_maturity_date"])).astype(int)
    return df
