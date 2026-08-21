"""
api/dependencies.py — loads the SQLite DB connection and Day 3/4 model
artifacts ONCE at startup, instead of reopening/reloading them on every
request. FastAPI's lifespan hook (in main.py) populates this module's
globals; each endpoint just reads them.
"""

import json
import sqlite3
from datetime import date as date_type
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "sql" / "viralwatch.db"
MODELS_DIR = BASE_DIR / "models"
NLP_PATH = BASE_DIR / "data" / "processed" / "nlp_bulletin_extractions.json"

CROSS_BORDER_PROVINCES = {"Nord-Kivu", "Sud-Kivu"}

# Single source of truth for feature order, must match training exactly.
# Shared here so the scaler/RF model input and any future retraining
# script can be kept in sync instead of drifting apart.
FEATURE_ORDER = [
    "cumulative_confirmed_cases",
    "days_since_first_case",
    "population_density",
]

# Populated by lifespan() in main.py at startup
state: dict = {
    "db": None,
    "scaler": None,
    "rf_model": None,
    "keras_model": None,
    "rt_proxy_fallback": 1.0,  # overwritten at startup with the real median
}


def get_db() -> sqlite3.Connection:
    """Return the shared DB connection, with rows addressable by column name."""
    if state["db"] is None:
        raise RuntimeError("DB connection not initialized — did startup run?")
    return state["db"]


def load_artifacts() -> None:
    """Called once from FastAPI's lifespan startup."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    state["db"] = conn

    state["scaler"] = joblib.load(MODELS_DIR / "keras_feature_scaler.joblib")
    state["rf_model"] = joblib.load(MODELS_DIR / "baseline_random_forest.joblib")

    # Day 3 median-imputes missing rt_proxy at TRAIN time (early rows in
    # each zone's series have no prior week to compare against yet). We
    # mirror that here for live predictions on zones/dates with no
    # rt_proxy yet, using the overall DB median as a practical stand-in
    # for "the train-set median" (a reasonable approximation, not an
    # exact match to whatever the original training split's median was).
    row = conn.execute(
        "SELECT rt_proxy FROM daily_cases WHERE rt_proxy IS NOT NULL"
    ).fetchall()
    if row:
        values = sorted(r["rt_proxy"] for r in row)
        state["rt_proxy_fallback"] = values[len(values) // 2]

    # Imported lazily so the rest of the API can still start even if
    # tensorflow isn't installed in some other environment (e.g. a slimmer
    # deploy target that only serves /earlywarning and /briefing).
    import tensorflow as tf
    state["keras_model"] = tf.keras.models.load_model(
        MODELS_DIR / "keras_next7d_onset.keras"
    )


def close_artifacts() -> None:
    if state["db"] is not None:
        state["db"].close()


def predict_zone_features(
    cumulative_confirmed_cases: float,
    days_since_first_case: int,
    population_density: float,
) -> tuple[float, float]:

    X = pd.DataFrame(
        [[
            cumulative_confirmed_cases,
            days_since_first_case,
            population_density,
        ]],
        columns=FEATURE_ORDER,
    )

    X_scaled = state["scaler"].transform(X)

    keras_prob = float(
        state["keras_model"].predict(X_scaled, verbose=0)[0][0]
    )

    rf_prob = float(
        state["rf_model"].predict_proba(X)[0][1]
    )

    return keras_prob, rf_prob


def compute_zone_trend_features(case_rows: list) -> dict:
    """Given a zone's full daily_cases history (ordered by date, each row
    with new_cases and rt_proxy), compute the trend features live — the
    same features engineered in Day 3's Step 2, applied to whatever the
    zone's most recent date is.

    case_rows: list of sqlite3.Row with 'date', 'new_cases', 'rt_proxy'
    """
    if not case_rows:
        return {
            "rolling_7d_new_cases": 0.0,
            "days_since_last_case": 0,
            "rt_proxy": state["rt_proxy_fallback"],
        }

    # rolling_7d_new_cases: sum of the last up-to-7 rows' new_cases,
    # mirroring pandas' .rolling(7, min_periods=1).sum() used in training
    last_7 = case_rows[-7:]
    rolling_7d = sum((r["new_cases"] or 0) for r in last_7)

    # days_since_last_case: days between the most recent date and the most
    # recent date with new_cases > 0. Falls back to "days since first case"
    # (i.e. the full zone history) if the zone has never reported a new
    # case day, matching training's fillna behavior.
    latest_date = date_type.fromisoformat(case_rows[-1]["date"])
    last_case_date = None
    for r in reversed(case_rows):
        if (r["new_cases"] or 0) > 0:
            last_case_date = date_type.fromisoformat(r["date"])
            break
    if last_case_date is not None:
        days_since_last_case = (latest_date - last_case_date).days
    else:
        first_date = date_type.fromisoformat(case_rows[0]["date"])
        days_since_last_case = (latest_date - first_date).days

    latest_rt_proxy = case_rows[-1]["rt_proxy"]
    if latest_rt_proxy is None:
        latest_rt_proxy = state["rt_proxy_fallback"]

    return {
        "rolling_7d_new_cases": float(rolling_7d),
        "days_since_last_case": int(days_since_last_case),
        "rt_proxy": float(latest_rt_proxy),
    }


def load_nlp_briefings() -> list[dict]:
    if not NLP_PATH.exists():
        return []
    with open(NLP_PATH, encoding="utf-8") as f:
        return json.load(f)
