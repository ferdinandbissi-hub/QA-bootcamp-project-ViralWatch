# ACLED conflict and violence aggregates

Weekly **province-level** aggregates of armed conflict, political violence, demonstrations, and related events in the Democratic Republic of the Congo (DRC), from [Armed Conflict Location & Event Data (ACLED)](https://acleddata.com). The extract is filtered to outbreak-affected provinces (Ituri, Nord-Kivu, Tshopo) for use as a contextual risk layer alongside mobility and epidemiological data.

This folder is currently a **placeholder**: raw data are stored here, but there is no `process.py` and no QA-passing files under `processed/`. The repository’s canonical join key is **health zone** (`Nom`); the supplied ACLED file is at **ADMIN1 (province)** grain only, so it is **not** merged into `build/drc_health_zones.geojson` until a future pipeline produces zone- or province-grain contract outputs.

------------------------------------------------------------------------

## Files

| File | Description |
|----|----|
| `raw/ACLED_Africa_weekly_agregated_20250502.csv` | Weekly aggregates per province, event type, and sub-event type (untouched download) |
| `metadata.yaml` | Provenance, licence, and pipeline notes |

**No `processed/` outputs yet** — see **Data quality and limitations** and `metadata.yaml` for why.

------------------------------------------------------------------------

## Raw extract

**Source:** ACLED weekly aggregated export for Africa (retrieved **2026-05-02**; see `metadata.yaml`).

**Coverage:**

| Dimension | Value |
|----|----|
| **Geography** | DRC provinces **Ituri**, **Nord-Kivu**, **Tshopo** only |
| **Temporal scope** | Weekly buckets from **2025-11-29** through **2026-05-02** (23 weeks) |
| **Rows** | 346 (one row per week × province × event/sub-event combination) |

**Columns (raw CSV):**

| Column | Description |
|----|----|
| `WEEK` | Week ending date (`YYYY-MM-DD`) |
| `REGION` | ACLED region label (e.g. Middle Africa) |
| `COUNTRY` | Country name |
| `ADMIN1` | Province name |
| `EVENT_TYPE` | Top-level event category (e.g. Battles, Protests, Violence against civilians) |
| `SUB_EVENT_TYPE` | Finer sub-type (e.g. Armed clash, Attack) |
| `EVENTS` | Count of events in that week/province/type bucket |
| `FATALITIES` | Reported fatalities |
| `POPULATION_EXPOSURE` | Population exposure where reported (often empty) |
| `DISORDER_TYPE` | Disorder grouping (e.g. Political violence, Demonstrations) |
| `ID` | Province-level identifier in this extract (three values: one per province) |
| `CENTROID_LATITUDE`, `CENTROID_LONGITUDE` | **Province summary** coordinates (not event locations) |

**Example (reading in R):**

``` r
library(here)

acled <- read.csv(
  here("data/ACLED_conflict/raw/ACLED_Africa_weekly_agregated_20250502.csv"),
  check.names = FALSE
)

# Events in Ituri, week ending 2026-05-02
subset(acled, ADMIN1 == "Ituri" & WEEK == "2026-05-02")
```

------------------------------------------------------------------------

## Method (current state)

1. **Download** — ACLED weekly aggregated export for relevant provinces and date range (academic/non-commercial terms; registration required at [acleddata.com](https://acleddata.com)).
2. **Store** — Place the untouched CSV under `raw/` with a dated filename.
3. **No downstream processing yet** — A future `process.py` (or province-grain contract support; see `docs/superpowers/specs/2026-05-20-province-grain-support-design.md`) would need to:
   - map `ADMIN1` to a supported output grain, and/or
   - ingest **event-level** ACLED data with coordinates for point-in-polygon aggregation to health zones.

**What this is not**

- Not health-zone resolution; do not join to `Nom` via `CENTROID_LATITUDE` / `CENTROID_LONGITUDE` — those columns repeat a **single centroid per province** (three distinct coordinate pairs across all 346 rows), so spatial assignment to zones would be meaningless.
- Not a time series at zone grain; weekly buckets are at province × event-type level only.

------------------------------------------------------------------------

## Regenerating outputs

There is **no** `process.py` in this folder yet. To refresh the raw file:

1. Obtain an updated ACLED weekly aggregate export for the same provinces (or event-level data for zone aggregation).
2. Replace or add under `raw/` and update `metadata.yaml` (`retrieved_on`, filename, notes).
3. When processed outputs exist, run from the repository root:

``` bash
python data/ACLED_conflict/process.py   # not yet implemented
.venv/bin/python -m tools.qa
```

------------------------------------------------------------------------

## Data quality and limitations

| Issue | Detail |
|----|----|
| **Province grain only** | Cannot pass vector/matrix QA at health-zone grain without re-aggregation or province-grain contract files. |
| **Centroid columns** | `CENTROID_*` are province summaries, not per-event geocodes. |
| **Placeholder status** | `metadata.yaml` sets `status: placeholder`; root README lists ACLED as **not in build**. |
| **Licence** | ACLED Terms of Use (academic / non-commercial). See [acleddata.com/terms-of-use](https://acleddata.com/terms-of-use/). |
| **Future work** | Event-level ACLED with lat/lon would allow zone-level counts; province-grain weekly vectors are an alternative if the pipeline supports `ADMIN1` as join key. |

------------------------------------------------------------------------

## Provenance

- **Provider:** [ACLED](https://acleddata.com) — *Raleigh, C., Linke, A., Hegre, H., & Karlsen, J. (2010). Introducing ACLED: An Armed Conflict Location and Event Dataset. Journal of Peace Research.*
- **Raw file:** `raw/ACLED_Africa_weekly_agregated_20250502.csv`
- **Metadata:** `metadata.yaml`

For project-wide data conventions, see `data/README.md`.
