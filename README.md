# ViralWatch

**AI-powered viral haemorrhagic fever outbreak early-warning system**, built end-to-end over one week on live data from the 2026 Bundibugyo virus disease outbreak in the Democratic Republic of Congo.

ViralWatch ingests daily INSP situation-report data, cleans it, engineers epidemiological features, trains a next-7-day case-onset classifier and a One-Class SVM anomaly detector, extracts structured signal from WHO bulletins via NLP, and serves all of it through a live FastAPI service and a cross-border watchlist dashboard focused on the Nord-Kivu / Sud-Kivu health zones bordering Rwanda.

---

## Why this project exists

On 15 May 2026, the DRC declared its 17th Ebola outbreak, caused by Bundibugyo virus — a species with no licensed vaccine or approved treatment. WHO declared a Public Health Emergency of International Concern two days later. One of the critical gaps in the response: the outbreak signal existed weeks before laboratory confirmation. ViralWatch is built to close that gap — surfacing anomalous zone-level patterns and bulletin-level severity signals before they're obvious from raw case counts alone.

---

## Architecture

```
                    ┌─────────────────────┐
                    │   INSP SitRep PDFs   │  (manually transcribed upstream
                    │   WHO DON bulletins  │   by INRB-UMIE / INSP)
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Day 2: pandas +     │  cleans zone-name typos,
                    │   NumPy cleaning      │  handles "ND" missing values,
                    │   (src/day2_...py)    │  builds Rt-proxy feature
                    └──────────┬───────────┘
                               │  data/processed/*.csv
              ┌────────────────┼────────────────┐
              ▼                                  ▼
   ┌──────────────────────┐         ┌──────────────────────────┐
   │  Day 3: scikit-learn  │         │  Day 4: One-Class SVM     │
   │  + Keras classifier   │         │  anomaly detector          │
   │  (src/day3_...py)     │         │  + Hugging Face NLP        │
   │  → models/*.joblib    │         │  (src/day4_...py)          │
   │    models/*.keras     │         │  → data/processed/*.json   │
   └──────────┬────────────┘         └──────────┬─────────────────┘
              │                                   │
              └────────────────┬──────────────────┘
                                ▼
                    ┌──────────────────────┐
                    │   data/db/            │  SQL joins: zones →
                    │   viralwatch.db        │  daily cases → features
                    └──────────┬───────────┘
                                ▼
                    ┌──────────────────────┐
                    │  Day 5: FastAPI        │  /predict/{zone}
                    │  (api/main.py)         │  /earlywarning
                    │  serves models + DB     │  /briefing
                    │  + dashboard (mounted)  │  /dashboard/  (static)
                    └──────────────────────┘
```

---

## Repository structure

```
QA-bootcamp-project-ViralWatch/
├── api/
│   ├── __init__.py
│   ├── main.py            # FastAPI app: 3 endpoints + mounts /dashboard/
│   ├── schemas.py         # Pydantic request/response contracts
│   └── dependencies.py    # DB connection + model loading (once, at startup)
├── dashboard/
│   └── index.html         # Cross-border watchlist, single static file
├── data/
│   ├── raw/Ebola_DRC_2026/
│   │   ├── data/insp_sitrep/processed/*.csv
│   │   ├── data/aliases.csv
│   │   └── build/drc_health_zones.geojson
│   ├── processed/
│   │   ├── zone_cases_cleaned.csv           # Day 2 output
│   │   ├── national_cleaned.csv             # Day 2 output
│   │   ├── zone_day_features_labelled.csv   # Day 3 output
│   │   ├── zone_anomaly_scores.csv          # Day 4 SVM output
│   │   └── nlp_bulletin_extractions.json    # Day 4 NLP output
│   └── db/
│       └── viralwatch.db      # SQLite: health_zones, daily_cases, anomaly_scores
├── models/
│   ├── baseline_random_forest.joblib
│   ├── keras_feature_scaler.joblib
│   └── keras_next7d_onset.keras
├── notebooks/plots/            # All matplotlib output (Day 2 + Day 3 + Day 4)
├── src/
│   ├── day2_cleaning_and_analysis.py
│   ├── day3_ml-fundamentals.py
│   ├── day4_nlp_extraction.py
│   └── day4_anomaly_detection.py
├── requirements.txt
└── README.md
```

---

## One-command setup

```bash
git clone <repo-url>
cd QA-bootcamp-project-ViralWatch
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running the full system

Everything — API and dashboard — is served from one process:

```bash
uvicorn api.main:app --reload --port 8000
```

Then open:
- **`http://127.0.0.1:8000/dashboard/`** — the cross-border watchlist dashboard
- **`http://127.0.0.1:8000/docs`** — interactive Swagger API documentation

If you want to change data or retrain (see Day-by-day section below for what each script does):

```bash
python src/day2_cleaning_and_analysis.py   # re-clean raw sitrep data
python src/day3_ml-fundamentals.py          # retrain classifier + baseline
python src/day4_anomaly_detection.py        # retrain anomaly detector
python src/day4_nlp_extraction.py           # re-run NLP on WHO bulletins
```

**Important:** any time you retrain, `uvicorn --reload` will NOT pick up the change automatically — it only watches `.py` files, not `.joblib` / `.keras` / `.db` files, which are loaded once at startup. Stop (`Ctrl+C`) and restart uvicorn after retraining.

---

## Day-by-day summary

### Day 1 — Git, GitHub, Linux & shell
Team repository set up with branch protection and PR review workflow. Bash script clones the INRB-UMIE dataset, downloads WHO DON PDFs, verifies integrity, and scaffolds the project directories.

### Day 2 — NumPy, pandas, data cleaning & visualization
`src/day2_cleaning_and_analysis.py` loads national + zone-level daily case/death counts from `data/insp_sitrep/`, cleans zone-name spelling variants via `aliases.csv`, converts "ND" (non disponible) and transcription artefacts to proper missing values (never filled with 0 — "not reported" ≠ "zero cases"), validates zone names against the official 519-zone list, and builds an Rt-proxy feature (7-day rolling growth ratio) with NumPy. Produces the epidemic curve, health-zone breakdown, and CFR trend plots.

**Note on zone coverage:** the raw sitrep data only contains rows for zones that have reported at least one case — currently ~48–60 of the DRC's 519 official health zones. This is expected, not a data-loss bug: most of the country has had zero cases in this outbreak.

### Day 3 — ML fundamentals, Keras, training deep models well
`src/day3_ml-fundamentals.py` builds a supervised classifier answering: *"will this health zone report a new case in the next 7 days?"* Engineers causal trend features (`rolling_7d_new_cases`, `days_since_last_case`, reuses Day 2's `rt_proxy`), splits train/test **by date** (not randomly — a random split would leak future information), trains a scikit-learn RandomForest baseline and a small Keras network, and evaluates both with precision/recall/PR-curves rather than raw accuracy (given ~64% class imbalance).

**Two real bugs found and fixed post-integration** (worth knowing if you touch this file):
1. The original `FEATURES` list only included 3 static features (`cumulative_confirmed_cases`, `days_since_first_case`, `population_density`) and silently dropped the 3 engineered trend features — the exact signal a "will this accelerate soon" model needs most.
2. `cumulative_confirmed_cases` and `rolling_7d_new_cases` are heavily right-skewed (mean 70, median 9.5, driven by outbreak-center zones like Bunia at 801 cases) — feeding this raw into the neural net caused saturated near-0%/100% predictions. Fixed with a `log1p` transform before scaling.

Fixing both took Keras's average precision from 0.892 → 0.932, and resolved cases where the Keras and RandomForest models disagreed by 30+ points on the same zone.

**Known limitation:** the training data only ever contains zones with at least some case history (see Day 2 note above). Predictions for zones with zero case history are genuine extrapolations outside the training distribution — expect more model disagreement on those specific zones, and don't over-read a single prediction there.

### Day 4 — NLP, anomaly detection & evaluation, SQL
- `src/day4_nlp_extraction.py`: Hugging Face NER (`dslim/bert-base-NER`) and zero-shot classification (`facebook/bart-large-mnli`) pipelines extract affected locations, case/death counts (regex, paired with context), and per-paragraph severity language from WHO DON bulletins → `data/processed/nlp_bulletin_extractions.json`.
- `src/day4_anomaly_detection.py`: trains a One-Class SVM on each zone's own first 14 days of reporting as its "baseline," then scores every subsequent day for anomalousness — never trained on any post-baseline data, mimicking a real early-warning system that only has early data available at prediction time.

**Documented adaptation:** the project brief describes testing whether the SVM would have flagged the literal April 24–May 5 signal window before the May 15 lab confirmation. Our case-count data starts May 14 — one day before confirmation — so there is no true pre-outbreak national daily data to train on. We adapted the exercise to the health-zone framing already in the brief: each zone's own early reporting period stands in as its baseline, and we test whether the SVM flags that zone's later acceleration before it's obvious from raw counts. This is an honest, documented adaptation — say this explicitly in the demo rather than implying it matches the literal April 24–May 5 window.

- SQLite database (`data/db/viralwatch.db`) with `health_zones`, `daily_cases`, `anomaly_scores` tables, joined by zone name.

### Day 5 — FastAPI, frontend, model serving
`api/main.py` serves three endpoints (`/predict/{zone}`, `/earlywarning`, `/briefing`) backed by the Day 3/4 artifacts, loaded once at startup (not per-request). `dashboard/index.html` is a single static file — no build step — showing the cross-border watchlist, ranked anomaly table, zone-lookup predictor, and latest-bulletin briefing, all fetched live from the API. As of the final setup, the dashboard is mounted directly onto the FastAPI app (`/dashboard/`), so the whole system runs from a single `uvicorn` command.

---

## API reference

| Endpoint | Returns |
|---|---|
| `GET /predict/{zone}` | Next-7-day case-onset probability (Keras + RandomForest baseline) for one health zone |
| `GET /earlywarning?limit=&cross_border_only=` | All zones' latest anomaly score, ranked highest-first |
| `GET /briefing` | NLP-extracted summary of the most recent WHO DON bulletin |
| `GET /docs` | Interactive Swagger documentation (auto-generated) |

Full request/response schemas are in `api/schemas.py` and browsable live at `/docs`.

---

## Data attribution

The INRB-UMIE dataset is maintained by the Institut National de Recherche Biomédicale (INRB) and the Institut National de Santé Publique (INSP), DRC (`github.com/INRB-UMIE/BDBV2026-Data`). Health-zone boundaries from HDX (DRC Health Zones Shapefile). WHO Disease Outbreak News bulletins and ECDC tracker data are freely reusable with attribution. This data is used for internal training purposes only, per the source repository's terms — see `data/raw/Ebola_DRC_2026/README.md` for full terms if publishing any epidemiological findings.

---

## Team

_Add team member names here._
