"""
day2_cleaning_and_analysis.py — ViralWatch Day 2

What this script does, in order:
  1. Load the national daily case/death counts
  2. Load the health-zone level daily case/death counts
  3. Clean health-zone names using aliases.csv (fixes typos/spelling variants)
  4. Handle missing values (the deaths file has "ND" = "non disponible" = not available)
  5. Join health-zone data to the official zone list (from the geojson) to catch
     any zone name that still doesn't match
  6. Build an Rt-proxy feature with NumPy (rough proxy for how fast a zone's
     case count is growing week-over-week)
  7. Produce 3 plots: epidemic curve, health-zone breakdown, CFR trend
  8. Save a cleaned dataset to data/processed/ for Day 3 to use

Run with:
    source venv/bin/activate
    python src/day2_cleaning_and_analysis.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from pathlib import Path

# -----------------------------------------------------------------------
# Paths — adjust RAW_DIR if your folder structure differs
# -----------------------------------------------------------------------
RAW_DIR = Path("/home/ferdinand/Documents/Coop_program/Quantum_Arise/Week1_Bootcamp/ViralWatch/QA-bootcamp-project-ViralWatch/data/raw/Ebola_DRC_2026")
OUT_DIR = Path("data/processed")
PLOTS_DIR = Path("notebooks/plots")
OUT_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

SITREP = RAW_DIR / "data" / "insp_sitrep" / "processed"

# =========================================================================
# STEP 1: Load national daily cumulative cases and deaths
# =========================================================================
national_cases = pd.read_csv(SITREP / "insp_sitrep__national_cumulative_confirmed_cases__daily.csv")
national_deaths = pd.read_csv(SITREP / "insp_sitrep__national_cumulative_confirmed_deaths__daily.csv")

national_cases["date"] = pd.to_datetime(national_cases["date"])
national_deaths["date"] = pd.to_datetime(national_deaths["date"])

national = national_cases.merge(
    national_deaths[["date", "national_cumulative_confirmed_deaths"]],
    on="date",
    how="outer",
).sort_values("date").reset_index(drop=True)

print(f"[1/8] National data loaded: {len(national)} days, "
      f"{national['date'].min().date()} to {national['date'].max().date()}")

# =========================================================================
# STEP 2: Load health-zone level cases and deaths
# =========================================================================
zone_cases = pd.read_csv(SITREP / "insp_sitrep__cumulative_confirmed_cases__daily.csv")
zone_deaths = pd.read_csv(SITREP / "insp_sitrep__cumulative_confirmed_deaths__daily.csv")

print(f"[2/8] Zone-level data loaded: {len(zone_cases)} case rows, "
      f"{len(zone_deaths)} death rows, "
      f"{zone_cases['nom'].nunique()} unique zone names (before cleaning)")

# Some rows have no zone name at all (nom is blank). A case count with no
# zone attached can't be used in a zone-level analysis or joined to the
# zone reference list, and we have no reliable way to guess which zone it
# belongs to — so we drop these rows rather than invent an answer.
# We log exactly how many were dropped so the decision is documented, not hidden.
n_before = len(zone_cases)
zone_cases = zone_cases.dropna(subset=["nom"])
n_dropped = n_before - len(zone_cases)
if n_dropped:
    print(f"      Dropped {n_dropped} case rows with no health-zone name "
          f"(cannot be attributed to a zone)")

n_before = len(zone_deaths)
zone_deaths = zone_deaths.dropna(subset=["nom"])
n_dropped = n_before - len(zone_deaths)
if n_dropped:
    print(f"      Dropped {n_dropped} death rows with no health-zone name")

# =========================================================================
# STEP 3: Clean health-zone names using aliases.csv
# =========================================================================
# aliases.csv maps a messy/observed spelling to the correct canonical name.
# Example row: observed_name=Rwmapara, canonical_nom=Rwampara
aliases = pd.read_csv(RAW_DIR / "data" / "aliases.csv")
alias_map = dict(zip(aliases["observed_name"], aliases["canonical_nom"]))

def clean_zone_name(name: str) -> str:
    """Replace a messy/alternate zone name with its canonical version, if known."""
    name = str(name).strip()
    return alias_map.get(name, name)  # if not in the map, leave it as-is

zone_cases["nom_clean"] = zone_cases["nom"].apply(clean_zone_name)
zone_deaths["nom_clean"] = zone_deaths["nom"].apply(clean_zone_name)

n_fixed = (zone_cases["nom"] != zone_cases["nom_clean"]).sum()
print(f"[3/8] Cleaned zone names: {n_fixed} rows had a name fixed via aliases.csv, "
      f"now {zone_cases['nom_clean'].nunique()} unique zones")

# =========================================================================
# STEP 4: Handle missing values
# =========================================================================
# The sitrep files use "ND" (French: "non disponible") for missing values,
# and at least one row has a stray trailing character (e.g. "17-" instead
# of "17" — another manual-transcription artefact). pd.to_numeric with
# errors="coerce" turns ANY value it can't parse into NaN, which covers
# both cases safely, without guessing at a "corrected" number.
# We do NOT fill missing values with 0 — that would be dishonest, since
# "not reported" is different from "zero cases/deaths".
zone_cases["cumulative_confirmed_cases"] = pd.to_numeric(
    zone_cases["cumulative_confirmed_cases"], errors="coerce"
)
n_missing_cases = zone_cases["cumulative_confirmed_cases"].isna().sum()

zone_deaths["cumulative_confirmed_deaths"] = pd.to_numeric(
    zone_deaths["cumulative_confirmed_deaths"], errors="coerce"
)
n_missing_deaths = zone_deaths["cumulative_confirmed_deaths"].isna().sum()

print(f"[4/8] Converted non-numeric values (e.g. 'ND', stray characters) to NaN: "
      f"{n_missing_cases} of {len(zone_cases)} case rows and "
      f"{n_missing_deaths} of {len(zone_deaths)} death rows are missing (not reported)")

# The Rt-proxy calculation in Step 6 needs a continuous numeric series per
# zone, so we drop rows where the case count itself is missing (can't
# compute new-cases-per-day around a gap). Deaths are allowed to stay
# missing since CFR is calculated at the national level, not per-zone.
zone_cases = zone_cases.dropna(subset=["cumulative_confirmed_cases"])

# The raw sitrep CSVs contain at least one stray bracket character in a
# date cell (e.g. "2026-06-25]" instead of "2026-06-25") — a transcription
# artefact from manually-copied PDF tables. We strip stray non-date
# characters before parsing, and log how many rows were affected, rather
# than silently dropping them.
def clean_date_str(s: str) -> str:
    return str(s).strip().strip("]").strip("[").strip()

for df in (zone_cases, zone_deaths):
    before = df["date"].copy()
    df["date"] = df["date"].apply(clean_date_str)
    n_dirty = (before.astype(str) != df["date"]).sum()
    if n_dirty:
        print(f"      Cleaned {n_dirty} malformed date value(s), e.g. stray brackets from PDF transcription")

zone_cases["date"] = pd.to_datetime(zone_cases["date"])
zone_deaths["date"] = pd.to_datetime(zone_deaths["date"])

# =========================================================================
# STEP 5: Join to the official health-zone reference list
# =========================================================================
# The geojson build file contains the official list of health zones (used
# for the boundary/shapefile data). We use it here just to validate our
# zone names — any zone_clean name NOT in this list still needs fixing.
with open(RAW_DIR / "build" / "drc_health_zones.geojson") as f:
    geojson = json.load(f)

official_zones = set(feat["properties"]["nom"] for feat in geojson["features"])
print(f"[5/8] Official zone list loaded: {len(official_zones)} zones")

unmatched = sorted(set(zone_cases["nom_clean"]) - official_zones)
if unmatched:
    print(f"      WARNING: {len(unmatched)} zone names still don't match the "
          f"official list (may need adding to aliases.csv): {unmatched[:10]}"
          + (" ..." if len(unmatched) > 10 else ""))
else:
    print("      All zone names matched the official list.")

# =========================================================================
# STEP 6: Build an Rt-proxy feature with NumPy
# =========================================================================
# Rt (effective reproduction number) needs detailed case-generation-interval
# data we don't have. Instead we build a simple PROXY: the ratio of new
# cases this week vs new cases last week, per zone. > 1 means the zone's
# outbreak is accelerating; < 1 means it's slowing down.
zone_cases = zone_cases.sort_values(["nom_clean", "date"])

def compute_rt_proxy(group: pd.DataFrame) -> pd.DataFrame:
    """For one health zone: compute new cases per day, then a 7-day-window
    growth ratio using NumPy."""
    cum = group["cumulative_confirmed_cases"].to_numpy(dtype=float)
    # np.diff gives day-to-day new cases from cumulative counts
    new_cases = np.diff(cum, prepend=cum[0])
    new_cases = np.clip(new_cases, 0, None)  # negative diffs = data revisions, floor at 0

    # rolling 7-value sum using NumPy convolution (a fast way to do a moving sum)
    window = 7
    kernel = np.ones(window)
    # 'full' convolution then trim so the output lines up with the input dates
    rolling_sum = np.convolve(new_cases, kernel, mode="full")[: len(new_cases)]

    # this-week vs previous-week ratio, shifted by the window size
    prev_week = np.roll(rolling_sum, window)
    prev_week[:window] = np.nan  # no valid "previous week" for the first days
    with np.errstate(divide="ignore", invalid="ignore"):
        rt_proxy = np.where(prev_week > 0, rolling_sum / prev_week, np.nan)

    group = group.copy()
    group["new_cases"] = new_cases
    group["rt_proxy"] = rt_proxy
    return group

# Note: pandas 3.0 no longer passes the grouping column into .apply(), so
# we loop over groups explicitly and re-attach the zone name ourselves.
results = []
for zone_name, group in zone_cases.groupby("nom_clean"):
    processed = compute_rt_proxy(group)
    processed["nom_clean"] = zone_name
    results.append(processed)
zone_cases = pd.concat(results, ignore_index=True)
print(f"[6/8] Rt-proxy computed. Zones currently trending up (rt_proxy > 1): "
      f"{zone_cases[zone_cases['date'] == zone_cases['date'].max()].query('rt_proxy > 1')['nom_clean'].nunique()}")

# =========================================================================
# STEP 7: Produce 3 plots
# =========================================================================

# --- Plot 1: Epidemic curve (national cumulative confirmed cases over time) ---
plt.figure(figsize=(10, 5))
plt.plot(national["date"], national["national_cumulative_confirmed_cases"],
         marker="o", markersize=3, color="#b3261e")
plt.title("ViralWatch — National Cumulative Confirmed Cases Over Time")
plt.xlabel("Date")
plt.ylabel("Cumulative confirmed cases")
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(PLOTS_DIR / "01_epidemic_curve.png", dpi=150)
plt.close()

# --- Plot 2: Health-zone case breakdown (top 15 zones by latest case count) ---
latest_date = zone_cases["date"].max()
latest_by_zone = (
    zone_cases[zone_cases["date"] == latest_date]
    .sort_values("cumulative_confirmed_cases", ascending=False)
    .head(15)
)
plt.figure(figsize=(10, 6))
plt.barh(latest_by_zone["nom_clean"], latest_by_zone["cumulative_confirmed_cases"],
         color="#8a5cf6")
plt.gca().invert_yaxis()  # highest case count at the top
plt.title(f"ViralWatch — Top 15 Health Zones by Confirmed Cases ({latest_date.date()})")
plt.xlabel("Cumulative confirmed cases")
plt.tight_layout()
plt.savefig(PLOTS_DIR / "02_health_zone_breakdown.png", dpi=150)
plt.close()

# --- Plot 3: Case-fatality ratio (CFR) trend over time, national level ---
national["cfr"] = (
    national["national_cumulative_confirmed_deaths"]
    / national["national_cumulative_confirmed_cases"]
) * 100  # as a percentage

plt.figure(figsize=(10, 5))
plt.plot(national["date"], national["cfr"], marker="o", markersize=3, color="#1e6fb3")
plt.title("ViralWatch — National Case-Fatality Ratio (CFR) Trend")
plt.xlabel("Date")
plt.ylabel("CFR (%)")
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(PLOTS_DIR / "03_cfr_trend.png", dpi=150)
plt.close()

print(f"[7/8] Saved 3 plots to {PLOTS_DIR}/")

# =========================================================================
# STEP 8: Save cleaned data for Day 3
# =========================================================================
zone_cases_out = zone_cases.merge(
    zone_deaths[["nom_clean", "date", "cumulative_confirmed_deaths"]],
    on=["nom_clean", "date"],
    how="left",
)
zone_cases_out.to_csv(OUT_DIR / "zone_cases_cleaned.csv", index=False)
national.to_csv(OUT_DIR / "national_cleaned.csv", index=False)

print(f"[8/8] Cleaned data saved to {OUT_DIR}/")
print("\n=== Day 2 complete ===")
