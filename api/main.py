"""
api/main.py — ViralWatch Day 5: FastAPI service

Serves three endpoints on top of the artifacts built Monday-Thursday:
  GET /predict/{zone}   -> Day 3's classifiers (Keras + RF baseline)
  GET /earlywarning     -> Day 4's One-Class SVM anomaly scores (SQLite)
  GET /briefing         -> Day 4's NLP extraction from WHO DON bulletins

Run with:
    source venv/bin/activate
    uvicorn api.main:app --reload --port 8000

Then open http://127.0.0.1:8000/docs for interactive Swagger docs.
"""

from contextlib import asynccontextmanager
from datetime import date as date_type
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import dependencies as deps
from api.schemas import (
    ZonePredictionResponse,
    EarlyWarningResponse,
    EarlyWarningZone,
    BriefingResponse,
    BulletinBriefing,
    CaseDeathCount,
    ParagraphSeverity,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load the DB connection + all three models ONCE, not per-request
    print("Loading DB connection and Day 3/4 model artifacts...")
    deps.load_artifacts()
    print("Ready.")
    yield
    # Shutdown
    deps.close_artifacts()


app = FastAPI(
    title="ViralWatch API",
    description=(
        "AI-powered viral haemorrhagic fever early-warning system — "
        "serves next-7-day onset predictions, anomaly-based early warnings, "
        "and NLP-extracted WHO bulletin briefings for the 2026 DRC Bundibugyo "
        "virus outbreak."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Allows the Day 5 HTML/JS dashboard (served from a different origin/port,
# or opened as a local file) to call these endpoints from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "ViralWatch API",
        "endpoints": ["/predict/{zone}", "/earlywarning", "/briefing", "/docs"],
    }


# =========================================================================
# GET /predict/{zone}
# =========================================================================
@app.get("/predict/{zone}", response_model=ZonePredictionResponse, tags=["prediction"])
def predict_zone(zone: str):
    """Next-7-day new-case-onset probability for one health zone.

    Runs Day 3's Keras network (primary) and the scikit-learn RandomForest
    baseline (for comparison) on that zone's latest known features.
    """
    db = deps.get_db()

    zone_row = db.execute(
        "SELECT nom, province, population_density FROM health_zones WHERE nom = ?",
        (zone,),
    ).fetchone()
    if zone_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"'{zone}' is not a recognized health zone. "
                   f"Check spelling against the official zone list (see Day 2's aliases.csv).",
        )

    case_rows = db.execute(
        "SELECT date, cumulative_confirmed_cases, new_cases, rt_proxy FROM daily_cases "
        "WHERE nom = ? ORDER BY date",
        (zone,),
    ).fetchall()

    if case_rows:
        first_date = date_type.fromisoformat(case_rows[0]["date"])
        latest_row = case_rows[-1]
        latest_date = date_type.fromisoformat(latest_row["date"])
        cumulative_cases = latest_row["cumulative_confirmed_cases"] or 0.0
        days_since_first_case = (latest_date - first_date).days
        has_case_data = True
    else:
        # Zone exists in the official list but has never reported a case —
        # that's a meaningful, valid state, not an error.
        cumulative_cases = 0.0
        days_since_first_case = 0
        has_case_data = False

    trend = deps.compute_zone_trend_features(case_rows)

    keras_prob, rf_prob = deps.predict_zone_features(
        cumulative_confirmed_cases=cumulative_cases,
        days_since_first_case=days_since_first_case,
        population_density=zone_row["population_density"],
        
    )

    return ZonePredictionResponse(
        zone=zone_row["nom"],
        province=zone_row["province"],
        cross_border_watch=zone_row["province"] in deps.CROSS_BORDER_PROVINCES,
        has_case_data=has_case_data,
        cumulative_confirmed_cases=cumulative_cases,
        days_since_first_case=days_since_first_case,
        population_density=zone_row["population_density"],
        next_7d_onset_probability=round(keras_prob, 4),
        baseline_rf_probability=round(rf_prob, 4),
    )


# =========================================================================
# GET /earlywarning
# =========================================================================
@app.get("/earlywarning", response_model=EarlyWarningResponse, tags=["prediction"])
def early_warning(
    limit: int = Query(20, ge=1, le=200, description="Max number of zones to return"),
    cross_border_only: bool = Query(
        False, description="If true, only return Nord-Kivu / Sud-Kivu zones"
    ),
):
    """All zones' most recent anomaly score (Day 4's One-Class SVM), ranked
    highest (most anomalous) first."""
    db = deps.get_db()

    # Latest anomaly_score row per zone, joined to province for the
    # cross-border watchlist filter.
    rows = db.execute(
        """
        SELECT a.nom, a.date, a.anomaly_score, h.province
        FROM anomaly_scores a
        JOIN health_zones h ON h.nom = a.nom
        WHERE a.date = (
            SELECT MAX(date) FROM anomaly_scores WHERE nom = a.nom
        )
        ORDER BY a.anomaly_score DESC
        """
    ).fetchall()

    if not rows:
        raise HTTPException(status_code=503, detail="No anomaly scores available yet.")

    if cross_border_only:
        rows = [r for r in rows if r["province"] in deps.CROSS_BORDER_PROVINCES]

    rows = rows[:limit]
    generated_from_date = max(r["date"] for r in rows) if rows else None

    zones = [
        EarlyWarningZone(
            zone=r["nom"],
            province=r["province"],
            cross_border_watch=r["province"] in deps.CROSS_BORDER_PROVINCES,
            date=r["date"],
            anomaly_score=round(r["anomaly_score"], 4),
            rank=i + 1,
        )
        for i, r in enumerate(rows)
    ]

    return EarlyWarningResponse(
        generated_from_date=generated_from_date,
        zone_count=len(zones),
        zones=zones,
    )


# =========================================================================
# GET /briefing
# =========================================================================
@app.get("/briefing", response_model=BriefingResponse, tags=["nlp"])
def briefing():
    """NLP-extracted summary (locations, case/death counts, severity) from
    the most recent WHO DON bulletin, produced by Day 4's Hugging Face
    pipelines (src/day4_nlp_extraction.py)."""
    all_results = deps.load_nlp_briefings()

    if not all_results:
        raise HTTPException(
            status_code=503,
            detail=(
                "No NLP bulletin extractions found. Run "
                "src/day4_nlp_extraction.py to generate "
                "data/processed/nlp_bulletin_extractions.json, then restart the API."
            ),
        )

    latest = all_results[-1]

    most_severe = None
    if latest["paragraph_severity"]:
        most_severe = max(
            latest["paragraph_severity"],
            key=lambda p: p["confidence"] if p["label"] == "emergency-level crisis" else 0,
        )

    return BriefingResponse(
        latest_bulletin=BulletinBriefing(
            bulletin=latest["bulletin"],
            locations_mentioned=latest["locations_mentioned"],
            case_death_counts=[CaseDeathCount(**c) for c in latest["case_death_counts"]],
            paragraph_severity=[ParagraphSeverity(**p) for p in latest["paragraph_severity"]],
            most_severe_paragraph=ParagraphSeverity(**most_severe) if most_severe else None,
        ),
        bulletin_count=len(all_results),
    )


# =========================================================================
# Serve the dashboard from the SAME process/port as the API.
# One command (`uvicorn api.main:app`), one terminal, no CORS to worry
# about — the dashboard just becomes another route on this server.
# Visit http://127.0.0.1:8000/dashboard/ instead of a separate :8080.
# =========================================================================
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
if DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
