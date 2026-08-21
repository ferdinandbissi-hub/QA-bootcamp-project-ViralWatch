"""
day4_anomaly_detection.py — ViralWatch Day 4, Session 11 (midday)

Goal: train a One-Class SVM on "normal, early" reporting patterns per health
zone, then test whether it flags each zone's later acceleration in cases —
BEFORE that acceleration is obvious from the raw case count alone.

IMPORTANT NOTE ON DATES (read this before the Friday demo):
The project brief describes testing whether the SVM would have flagged an
April 24-May 5 signal window before the May 15 lab confirmation. Our actual
case-count data starts May 14 -- one day before confirmation -- so there is
no true pre-outbreak daily data to train on nationally. We adapted the
exercise to match the health-zone framing already in the brief ("detect
health zones showing anomalous case patterns"): each zone's own first two
weeks of reporting is used as its "baseline / normal" period, and we test
whether the SVM flags that zone's later acceleration before it's obvious
from raw counts. This is a documented, honest adaptation -- explain it in
your README and Friday demo rather than implying it matches April 24-May 5.

Run with:
    source venv/bin/activate
    python src/day4_anomaly_detection.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import precision_recall_curve, average_precision_score
from pathlib import Path

IN_PATH = Path("data/processed/zone_cases_cleaned.csv")
PLOTS_DIR = Path("notebooks/plots")
OUT_DIR = Path("data/processed")
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_DAYS = 14   # first N days per zone = "normal early reporting"
SURGE_THRESHOLD = 2.0  # rt_proxy > this = "true" surge, used ONLY for evaluation,
                        # never shown to the SVM during training

# =========================================================================
# STEP 1: Load Day 2's cleaned zone-level data
# =========================================================================
df = pd.read_csv(IN_PATH)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["nom_clean", "date"]).reset_index(drop=True)

# day_idx = how many days into THIS zone's own outbreak we are (0 = its first
# recorded day), not a calendar date -- this is what makes the baseline
# per-zone rather than one fixed national date.
df["day_idx"] = df.groupby("nom_clean").cumcount()

print(f"[1/6] Loaded {len(df)} zone-day rows, {df['nom_clean'].nunique()} zones")

# =========================================================================
# STEP 2: Build features that are available from day 0 (no NaN warm-up)
# =========================================================================
# rt_proxy needs 14 days of history before it's defined (see Day 2), so we
# do NOT use it as a training feature here -- it would be undefined for
# every single baseline row. We use it later, ONLY to build an evaluation
# label, never as a model input.
df["rolling_3d_new_cases"] = (
    df.groupby("nom_clean")["new_cases"]
    .transform(lambda s: s.rolling(3, min_periods=1).mean())
)

FEATURES = ["new_cases", "rolling_3d_new_cases"]
print(f"[2/6] Built features (available from day 0): {FEATURES}")

# =========================================================================
# STEP 3: Keep only zones with enough history to have both a baseline
#          period AND a later period to test against
# =========================================================================
zone_lengths = df.groupby("nom_clean").size()
usable_zones = zone_lengths[zone_lengths >= BASELINE_DAYS + 7].index
n_dropped = df["nom_clean"].nunique() - len(usable_zones)
df = df[df["nom_clean"].isin(usable_zones)].copy()
print(f"[3/6] Kept {len(usable_zones)} zones with >= {BASELINE_DAYS + 7} days of data "
      f"({n_dropped} zones dropped -- too little history to have both a baseline "
      f"and a later test period)")

baseline_mask = df["day_idx"] < BASELINE_DAYS
test_mask = ~baseline_mask

# =========================================================================
# STEP 4: Train the One-Class SVM on baseline rows ONLY
# =========================================================================
# The SVM never sees any "later" data during training -- exactly mimicking
# a real early-warning system that only has early data available at the time.
scaler = StandardScaler()
X_baseline = scaler.fit_transform(df.loc[baseline_mask, FEATURES])

# nu = expected fraction of outliers even WITHIN the baseline period itself
# (reporting noise, one-off spikes) -- 0.1 is a common default starting point.
svm = OneClassSVM(kernel="rbf", nu=0.1, gamma="scale")
svm.fit(X_baseline)

print(f"[4/6] Trained One-Class SVM on {baseline_mask.sum()} baseline rows "
      f"from {len(usable_zones)} zones (never saw any post-baseline data)")

# =========================================================================
# STEP 5: Score every row. Higher anomaly_score = more anomalous.
# =========================================================================
X_all = scaler.transform(df[FEATURES])
# decision_function: positive = "normal" (inside the learned boundary),
# negative = "anomalous". We flip the sign so higher = more anomalous,
# which is the more intuitive convention for an early-warning score.
df["anomaly_score"] = -svm.decision_function(X_all)

# =========================================================================
# STEP 6: Evaluate -- does the anomaly score flag real surges?
# =========================================================================
# "True" surge label, for evaluation ONLY (never used in training):
# rt_proxy > SURGE_THRESHOLD means this zone's case count has more than
# doubled week-over-week. We can only evaluate rows where rt_proxy is
# defined (needs 14 days of prior history) AND that are in the test period.
eval_rows = df[test_mask & df["rt_proxy"].notna()].copy()
eval_rows["true_surge"] = (eval_rows["rt_proxy"] > SURGE_THRESHOLD).astype(int)

print(f"[5/6] Scored all {len(df)} rows. Evaluating on {len(eval_rows)} test rows "
      f"with a defined rt_proxy ({eval_rows['true_surge'].sum()} are true surges, "
      f"rt_proxy > {SURGE_THRESHOLD})")

precision, recall, thresholds = precision_recall_curve(
    eval_rows["true_surge"], eval_rows["anomaly_score"]
)
avg_precision = average_precision_score(eval_rows["true_surge"], eval_rows["anomaly_score"])

print(f"[6/6] Average precision (area under PR curve): {avg_precision:.3f}")
print(f"      (a random/no-skill detector would score close to "
      f"{eval_rows['true_surge'].mean():.3f}, the true-surge base rate)")

# --- Plot 1: PR curve ---
plt.figure(figsize=(7, 6))
plt.plot(recall, precision, color="#b3261e")
plt.axhline(eval_rows["true_surge"].mean(), color="gray", linestyle="--",
            label=f"No-skill baseline ({eval_rows['true_surge'].mean():.2f})")
plt.xlabel("Recall")
plt.ylabel("Precision")
plt.title(f"One-Class SVM — Precision-Recall Curve\nAverage Precision = {avg_precision:.3f}")
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(PLOTS_DIR / "04_svm_pr_curve.png", dpi=150)
plt.close()

# --- Plot 2: example zone timeline -- pick the zone with the most rows,
# so the "before vs after" pattern is clearest to show in the demo ---
example_zone = df.groupby("nom_clean").size().idxmax()
zdf = df[df["nom_clean"] == example_zone].sort_values("date")

fig, ax1 = plt.subplots(figsize=(11, 5))
ax1.bar(zdf["date"], zdf["new_cases"], color="#8a5cf6", alpha=0.5, label="New cases")
ax1.set_ylabel("New confirmed cases")
ax1.set_xlabel("Date")

ax2 = ax1.twinx()
ax2.plot(zdf["date"].to_numpy(), zdf["anomaly_score"].to_numpy(), color="#b3261e", marker="o", markersize=3,
          label="Anomaly score")
ax2.axvline(zdf.iloc[BASELINE_DAYS]["date"], color="black", linestyle="--", alpha=0.5)
ax2.text(zdf.iloc[BASELINE_DAYS]["date"], ax2.get_ylim()[1] * 0.9,
          "  baseline ends", fontsize=9)
ax2.set_ylabel("Anomaly score (higher = more anomalous)")

fig.suptitle(f"ViralWatch — Anomaly Score Over Time: {example_zone}")
fig.legend(loc="upper left", bbox_to_anchor=(0.08, 0.88))
plt.tight_layout()
plt.savefig(PLOTS_DIR / "05_svm_example_zone_timeline.png", dpi=150)
plt.close()

# Save scored data for the SQL step and the FastAPI /earlywarning endpoint later
df.to_csv(OUT_DIR / "zone_anomaly_scores.csv", index=False)

print(f"\nSaved: {PLOTS_DIR}/04_svm_pr_curve.png")
print(f"Saved: {PLOTS_DIR}/05_svm_example_zone_timeline.png (example zone: {example_zone})")
print(f"Saved: {OUT_DIR}/zone_anomaly_scores.csv")
print("\n=== Day 4 midday (anomaly detection) complete ===")
