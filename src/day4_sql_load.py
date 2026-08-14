"""
day4_sql_load.py — ViralWatch Day 4, afternoon session

Loads everything built so far (Day 2 cleaned case data, Day 4 anomaly
scores, the health-zone reference list) into a single SQLite database,
with proper JOINs linking:

    health_zones  -->  daily_cases  -->  anomaly_scores

This database is what Friday's FastAPI endpoints will query.

Run with:
    source venv/bin/activate
    python src/day4_sql_load.py
"""

import sqlite3
import json
import pandas as pd
from pathlib import Path

RAW_DIR = Path("/home/student25/Documents/Coop_program/Quantum Arise/Week1-Bootcamp/ViralWatch/QA-bootcamp-project-ViralWatch/data/raw/Ebola_DRC_2026")
PROCESSED_DIR = Path("data/processed")
DB_PATH = Path("data/viralwatch.db")

# =========================================================================
# STEP 1: Build the health_zones reference table from the geojson
# =========================================================================
# This is the "dimension" table -- one row per zone, with static/reference
# attributes. daily_cases and anomaly_scores will each have MANY rows per
# zone (one per date), and JOIN back to this table on zone name.
with open(RAW_DIR / "build" / "drc_health_zones.geojson") as f:
    geojson = json.load(f)

zone_rows = []
for feat in geojson["features"]:
    props = feat["properties"]
    zone_rows.append({
        "nom": props.get("nom"),
        "province": props.get("province"),
        "population_density": props.get("worldpop", {}).get("pop_density", {}).get("pop_density"),
        "healthsite_density": props.get("grid3_healthsites", {}).get("healthsite_density", {}).get("healthsite_density"),
        "gdp_per_capita": props.get("gdp_pc", {}).get("gdp_pc", {}).get("gdp_pc"),
    })
health_zones = pd.DataFrame(zone_rows)
print(f"[1/5] Built health_zones reference table: {len(health_zones)} zones")

# =========================================================================
# STEP 2: Load Day 2's cleaned daily case/death data
# =========================================================================
daily_cases = pd.read_csv(PROCESSED_DIR / "zone_cases_cleaned.csv")
# The file has both the original messy "nom" and the cleaned "nom_clean" --
# select nom_clean explicitly and drop the original to avoid a duplicate
# "nom" column after renaming.
daily_cases = daily_cases[["nom_clean", "date", "cumulative_confirmed_cases",
                            "new_cases", "rt_proxy", "cumulative_confirmed_deaths"]]
daily_cases = daily_cases.rename(columns={"nom_clean": "nom"})
print(f"[2/5] Loaded daily_cases: {len(daily_cases)} zone-day rows")

# =========================================================================
# STEP 3: Load Day 4's anomaly scores
# =========================================================================
anomaly_scores = pd.read_csv(PROCESSED_DIR / "zone_anomaly_scores.csv")
anomaly_scores = anomaly_scores[["nom_clean", "date", "anomaly_score"]].rename(
    columns={"nom_clean": "nom"}
)
print(f"[3/5] Loaded anomaly_scores: {len(anomaly_scores)} zone-day rows")

# =========================================================================
# STEP 4: Write all three tables into a single SQLite database
# =========================================================================
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(DB_PATH)

health_zones.to_sql("health_zones", conn, if_exists="replace", index=False)
daily_cases.to_sql("daily_cases", conn, if_exists="replace", index=False)
anomaly_scores.to_sql("anomaly_scores", conn, if_exists="replace", index=False)

# Indexes make the JOINs below (and the FastAPI queries on Friday) fast --
# without one, SQLite has to scan every row of daily_cases/anomaly_scores
# every time it looks up a zone.
conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_cases_nom ON daily_cases(nom)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_scores_nom ON anomaly_scores(nom)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_health_zones_nom ON health_zones(nom)")
conn.commit()

print(f"[4/5] Wrote 3 tables to {DB_PATH}: health_zones, daily_cases, anomaly_scores")

# =========================================================================
# STEP 5: Example JOIN queries -- health zones -> daily cases -> features
# =========================================================================
# Query A: full picture for the most recent date -- every zone's latest
# case count, growth rate, anomaly score, AND its static features
# (population density, healthsite access) in one row. This is basically
# the SQL that will power the /earlywarning endpoint on Friday.
query_a = """
SELECT
    h.nom,
    h.province,
    h.population_density,
    h.healthsite_density,
    d.date,
    d.cumulative_confirmed_cases,
    d.new_cases,
    d.rt_proxy,
    a.anomaly_score
FROM health_zones h
JOIN daily_cases d ON h.nom = d.nom
JOIN anomaly_scores a ON h.nom = a.nom AND d.date = a.date
WHERE d.date = (SELECT MAX(date) FROM daily_cases)
ORDER BY a.anomaly_score DESC
LIMIT 10;
"""
result_a = pd.read_sql(query_a, conn)
print(f"\n[5/5] Example query A -- top 10 zones by anomaly score on the latest date:")
print(result_a.to_string(index=False))

# Query B: North Kivu / South Kivu cross-border watchlist (matches the
# project brief's focus on zones bordering Rwanda) -- their full case
# history joined with province info, most recent day first.
# Note: the geojson uses French province names (Nord-Kivu, Sud-Kivu),
# matching the DRC's official administrative naming -- not the English
# "North/South Kivu" used in your project brief's prose.
query_b = """
SELECT h.nom, h.province, d.date, d.new_cases, d.rt_proxy, a.anomaly_score
FROM health_zones h
JOIN daily_cases d ON h.nom = d.nom
JOIN anomaly_scores a ON h.nom = a.nom AND d.date = a.date
WHERE h.province IN ('Nord-Kivu', 'Sud-Kivu')
ORDER BY d.date DESC, a.anomaly_score DESC
LIMIT 10;
"""
result_b = pd.read_sql(query_b, conn)
print(f"\nExample query B -- North/South Kivu cross-border watchlist (most recent 10 rows):")
print(result_b.to_string(index=False))

conn.close()
print(f"\n=== Day 4 afternoon (SQL) complete. Database saved to {DB_PATH} ===")
