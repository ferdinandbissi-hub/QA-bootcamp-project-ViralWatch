"""
day3_ml-fundamentals.py — ViralWatch Day 3

Question this script answers, per health zone, per day:
    "Will this health zone report at least one new confirmed case
     in the next 7 days?"

This is a binary classification problem: one row per (zone, date).

What this script does, in order:
  1. Load Day 2's cleaned zone-level data
  2. Engineer features that are honest about what was known AT the time
     of prediction (no future information allowed in — this is the
     single easiest way to accidentally cheat on outbreak data)
  3. Join in travel-time-to-treatment-centre and population-density
     features from the raw data sources (documents clearly if missing)
  4. Build the label by looking 7 days into the future
  5. Split train/test BY DATE, not randomly (a random split lets the
     model "see the future" and gives a falsely optimistic score)
  6. Train a baseline scikit-learn model, evaluate honestly against
     class imbalance (precision/recall/F1, PR curve — NOT accuracy)
  7. Train a small Keras network, plot training vs validation loss to
     diagnose overfitting, evaluate the same way
  8. Save everything Day 4 needs

Run with:
    source venv/bin/activate
    python src/day3_ml-fundamentals.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
    precision_recall_curve,
    PrecisionRecallDisplay,
    average_precision_score,
)

# -----------------------------------------------------------------------
# Paths — adjust RAW_DIR if your folder structure differs
# -----------------------------------------------------------------------
RAW_DIR = Path(
    "/home/student25/Documents/Coop_program/Quantum Arise/Week1-Bootcamp/"
    "ViralWatch/QA-bootcamp-project-ViralWatch/data/raw/Ebola_DRC_2026"
)
IN_DIR = Path("data/processed")
OUT_DIR = Path("data/processed")
PLOTS_DIR = Path("notebooks/plots")
MODELS_DIR = Path("models")
OUT_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

PREDICTION_WINDOW_DAYS = 7   # "will this zone see a new case in the next N days?"
TRAIN_FRACTION = 0.70        # first 70% of the date range -> train, rest -> test

# =========================================================================
# STEP 1: Load Day 2's cleaned zone-level data
# =========================================================================
zone = pd.read_csv(IN_DIR / "zone_cases_cleaned.csv")
zone["date"] = pd.to_datetime(zone["date"])
zone = zone.sort_values(["nom_clean", "date"]).reset_index(drop=True)

print(f"[1/8] Loaded {len(zone)} zone-day rows, "
      f"{zone['nom_clean'].nunique()} zones, "
      f"{zone['date'].min().date()} to {zone['date'].max().date()}")

# =========================================================================
# STEP 2: Engineer causal features (only using data up to & including
# each row's own date — nothing from the future)
# =========================================================================
# 2a. Days since the zone's first recorded case ("zone age")
first_case_date = zone.groupby("nom_clean")["date"].transform("min")
zone["days_since_first_case"] = (zone["date"] - first_case_date).dt.days

# 2b. Rolling 7-day new-case count (causal: sum of the last 7 days
#     up to and including the current row)
zone["rolling_7d_new_cases"] = (
    zone.groupby("nom_clean")["new_cases"]
    .transform(lambda s: s.rolling(window=7, min_periods=1).sum())
)

# 2c. Days since the zone last reported a new case (0 = reported today).
#     A zone that hasn't moved in a while is a different risk profile
#     than one that just had a case yesterday.
def days_since_last_case(group: pd.DataFrame) -> pd.Series:
    last_case_date = pd.NaT
    out = []
    for date, new_cases in zip(group["date"], group["new_cases"]):
        if pd.notna(last_case_date):
            out.append((date - last_case_date).days)
        else:
            out.append(np.nan)  # no prior case yet recorded for this zone
        if new_cases and new_cases > 0:
            last_case_date = date
    return pd.Series(out, index=group.index)

zone["days_since_last_case"] = (
    zone.groupby("nom_clean", group_keys=False).apply(days_since_last_case)
)
# If a zone has never had a "new case" event recorded yet by this row,
# treat it conservatively as "a long time" rather than inventing a number.
zone["days_since_last_case"] = zone["days_since_last_case"].fillna(
    zone["days_since_first_case"]
)

# rt_proxy from Day 2 is already causal (built from a rolling window
# ending at the current row) — safe to use as-is.

print(f"[2/8] Engineered causal features: days_since_first_case, "
      f"rolling_7d_new_cases, days_since_last_case (rt_proxy reused from Day 2)")

# =========================================================================
# STEP 3: Join population density
# =========================================================================
geojson_path = RAW_DIR / "build" / "drc_health_zones.geojson"

pop_density = {}

if geojson_path.exists():
    with open(geojson_path) as f:
        geo = json.load(f)

    for feat in geo["features"]:
        props = feat["properties"]
        name = props.get("nom")

        # Population density from WorldPop
        wp = props.get("worldpop", {}).get("pop_density", {})
        pd_val = wp.get("pop_density")

        if name and pd_val is not None:
            pop_density[name] = pd_val

    print(
        f"      Loaded population density for "
        f"{len(pop_density)} zones from geojson"
    )

else:
    print(
        f"      WARNING: {geojson_path} not found — "
        f"population_density will be missing"
    )

# Match population density to each health zone
zone["population_density"] = zone["nom_clean"].map(pop_density)

# Check and handle missing population-density values
n_missing = zone["population_density"].isna().sum()

zone["population_density_was_missing"] = (
    zone["population_density"].isna().astype(int)
)

if n_missing == len(zone):

    print(
        f"      WARNING: population_density is missing for ALL rows — "
        f"filled with 0. Fix the data source before trusting this feature."
    )

    zone["population_density"] = 0.0

elif n_missing:

    print(
        f"      population_density: "
        f"{n_missing}/{len(zone)} rows missing "
        f"({zone['population_density'].isna().mean():.1%}) "
        f"— median-imputed for modelling"
    )

    zone["population_density"] = zone["population_density"].fillna(
        zone["population_density"].median()
    )

print(f"[3/8] Joined population_density")

# =========================================================================
# STEP 4: Build the label — 7-day-forward case onset
# =========================================================================
# For each zone-day, look FORWARD up to PREDICTION_WINDOW_DAYS days: did
# new_cases sum to > 0 in that window? This is the only place in the
# script allowed to look at the future, because it's the target, not a
# feature.
def label_forward_window(group: pd.DataFrame) -> pd.Series:
    group = group.sort_values("date")
    dates = group["date"].to_numpy()
    new_cases = group["new_cases"].to_numpy()
    labels = np.zeros(len(group), dtype=int)
    has_full_window = np.zeros(len(group), dtype=bool)
    for i, d in enumerate(dates):
        window_end = d + np.timedelta64(PREDICTION_WINDOW_DAYS, "D")
        mask = (dates > d) & (dates <= window_end)
        labels[i] = 1 if new_cases[mask].sum() > 0 else 0
        # only trust rows where we actually have data extending to the
        # end of the window (otherwise "0" might just mean "no data yet")
        has_full_window[i] = dates.max() >= window_end
    return pd.Series(labels, index=group.index), pd.Series(has_full_window, index=group.index)

labels, full_window = [], []
for zone_name, group in zone.groupby("nom_clean"):
    lab, fw = label_forward_window(group)
    labels.append(lab)
    full_window.append(fw)
zone["label_next_7d_onset"] = pd.concat(labels).sort_index()
zone["has_full_future_window"] = pd.concat(full_window).sort_index()

n_before = len(zone)
model_df = zone[zone["has_full_future_window"]].copy()
print(f"[4/8] Built 7-day-forward label. Dropped {n_before - len(model_df)} rows near the "
      f"end of the dataset with no full future window to check (can't be labelled honestly). "
      f"Remaining: {len(model_df)} rows. "
      f"Class balance: {model_df['label_next_7d_onset'].mean():.1%} positive")

# =========================================================================
# STEP 5: Time-based train/test split
# =========================================================================
model_df = model_df.sort_values("date")
cutoff_idx = int(len(model_df) * TRAIN_FRACTION)
cutoff_date = model_df["date"].sort_values().iloc[cutoff_idx]

train_df = model_df[model_df["date"] < cutoff_date]
test_df = model_df[model_df["date"] >= cutoff_date]

FEATURES = [
    "cumulative_confirmed_cases",
    "days_since_first_case",
    "population_density",
]
TARGET = "label_next_7d_onset"

# rt_proxy still has some NaNs early in each zone's series (no prior week
# to compare against yet) — median-impute for modelling, same honesty
# principle as Step 3.
for df in (train_df, test_df):
    df["rt_proxy"] = df["rt_proxy"].fillna(train_df["rt_proxy"].median())

X_train, y_train = train_df[FEATURES], train_df[TARGET]
X_test, y_test = test_df[FEATURES], test_df[TARGET]

print(f"[5/8] Time-based split at {cutoff_date.date()}: "
      f"{len(train_df)} train rows ({train_df[TARGET].mean():.1%} positive), "
      f"{len(test_df)} test rows ({test_df[TARGET].mean():.1%} positive)")

# =========================================================================
# STEP 6: Baseline scikit-learn model
# =========================================================================
baseline = RandomForestClassifier(
    n_estimators=300,
    max_depth=6,
    class_weight="balanced",   # correct for the class imbalance, don't fake accuracy
    random_state=42,
)
baseline.fit(X_train, y_train)

y_pred = baseline.predict(X_test)
y_proba = baseline.predict_proba(X_test)[:, 1]

print("\n[6/8] Baseline (RandomForest) — classification report:")
print(classification_report(y_test, y_pred, target_names=["no new case", "new case"]))

ap_baseline = average_precision_score(y_test, y_proba)
print(f"      Average precision (area under PR curve): {ap_baseline:.3f}")

cm = confusion_matrix(y_test, y_pred)
ConfusionMatrixDisplay(cm, display_labels=["no new case", "new case"]).plot(cmap="Purples")
plt.title("Baseline (RandomForest) — Confusion Matrix")
plt.tight_layout()
plt.savefig(PLOTS_DIR / "04_baseline_confusion_matrix.png", dpi=150)
plt.close()

precision, recall, _ = precision_recall_curve(y_test, y_proba)
PrecisionRecallDisplay(precision=precision, recall=recall).plot()
plt.title(f"Baseline (RandomForest) — PR Curve (AP={ap_baseline:.3f})")
plt.tight_layout()
plt.savefig(PLOTS_DIR / "05_baseline_pr_curve.png", dpi=150)
plt.close()

importances = pd.Series(baseline.feature_importances_, index=FEATURES).sort_values()
plt.figure(figsize=(8, 5))
importances.plot.barh(color="#8a5cf6")
plt.title("Baseline (RandomForest) — Feature Importances")
plt.tight_layout()
plt.savefig(PLOTS_DIR / "06_baseline_feature_importance.png", dpi=150)
plt.close()

print(f"      Saved confusion matrix, PR curve, and feature-importance plots")

# =========================================================================
# STEP 7: Small Keras network
# =========================================================================
import tensorflow as tf
from tensorflow import keras
from sklearn.preprocessing import StandardScaler

assert not X_train.isna().any().any(), "NaNs remain in training features — fix before scaling!"
assert not X_test.isna().any().any(), "NaNs remain in test features — fix before scaling!"

# Neural nets are sensitive to feature scale (unlike trees) — standardise
# using train-set statistics only, so no test-set information leaks in.
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

n_pos = y_train.sum()
n_neg = len(y_train) - n_pos
class_weight = {0: 1.0, 1: n_neg / max(n_pos, 1)}  # balance via loss weighting

keras.utils.set_random_seed(42)
model = keras.Sequential([
    keras.layers.Input(shape=(X_train_scaled.shape[1],)),
    keras.layers.Dense(32, activation="relu"),
    keras.layers.Dropout(0.3),
    keras.layers.Dense(16, activation="relu"),
    keras.layers.Dropout(0.3),
    keras.layers.Dense(1, activation="sigmoid"),
])
model.compile(
    optimizer="adam",
    loss="binary_crossentropy",
    metrics=[keras.metrics.AUC(name="pr_auc", curve="PR")],
)

early_stop = keras.callbacks.EarlyStopping(
    monitor="val_loss", patience=8, restore_best_weights=True
)

history = model.fit(
    X_train_scaled, y_train,
    validation_split=0.15,   # carved out of TRAIN only, still chronological-ish
    epochs=100,
    batch_size=64,
    class_weight=class_weight,
    callbacks=[early_stop],
    verbose=0,
)

print(f"\n[7/8] Keras model trained for {len(history.history['loss'])} epochs "
      f"(early stopping {'triggered' if len(history.history['loss']) < 100 else 'not triggered'})")

# Training curves — this is the actual point of the exercise: can we see
# overfitting happening and react to it?
plt.figure(figsize=(8, 5))
plt.plot(history.history["loss"], label="train loss")
plt.plot(history.history["val_loss"], label="validation loss")
plt.xlabel("Epoch")
plt.ylabel("Binary cross-entropy loss")
plt.title("Keras — Training vs Validation Loss")
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(PLOTS_DIR / "07_keras_training_curves.png", dpi=150)
plt.close()

keras_proba = model.predict(X_test_scaled, verbose=0).ravel()
keras_pred = (keras_proba >= 0.5).astype(int)

print("      Keras — classification report:")
print(classification_report(y_test, keras_pred, target_names=["no new case", "new case"]))

ap_keras = average_precision_score(y_test, keras_proba)
print(f"      Average precision (area under PR curve): {ap_keras:.3f} "
      f"(baseline was {ap_baseline:.3f})")

cm_keras = confusion_matrix(y_test, keras_pred)
ConfusionMatrixDisplay(cm_keras, display_labels=["no new case", "new case"]).plot(cmap="Blues")
plt.title("Keras — Confusion Matrix")
plt.tight_layout()
plt.savefig(PLOTS_DIR / "08_keras_confusion_matrix.png", dpi=150)
plt.close()

precision_k, recall_k, _ = precision_recall_curve(y_test, keras_proba)
PrecisionRecallDisplay(precision=precision_k, recall=recall_k).plot()
plt.title(f"Keras — PR Curve (AP={ap_keras:.3f})")
plt.tight_layout()
plt.savefig(PLOTS_DIR / "09_keras_pr_curve.png", dpi=150)
plt.close()

print(f"      Saved training-curve, confusion matrix, and PR curve plots")

# =========================================================================
# STEP 8: Save everything Day 4 needs
# =========================================================================
model_df.to_csv(OUT_DIR / "zone_day_features_labelled.csv", index=False)

import joblib
joblib.dump(baseline, MODELS_DIR / "baseline_random_forest.joblib")
model.save(MODELS_DIR / "keras_next7d_onset.keras")
joblib.dump(scaler, MODELS_DIR / "keras_feature_scaler.joblib")

print(f"\n[8/8] Saved labelled feature table to {OUT_DIR}/zone_day_features_labelled.csv "
      f"and both models to {MODELS_DIR}/")
print("\n=== Day 3 complete ===")
