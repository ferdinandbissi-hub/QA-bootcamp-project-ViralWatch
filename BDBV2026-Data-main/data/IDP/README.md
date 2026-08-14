# IOM DTM internal relocation (displacement) matrices

Origin–destination matrices of **relocated individuals** between health zones in eastern DRC, from the International Organization for Migration ([IOM](https://dtm.iom.int)) Displacement Tracking Matrix (DTM). The underlying survey is **Mobility Tracking Round 14 — Ituri** (January 2026 public release); matrices were pre-aggregated upstream from the IOM workbook and are rewritten here to canonical zone names (`Nom`).

These matrices complement phone-based Flowminder estimates (`data/flowminder/`) and support gravity-style or connectivity analyses where **reported internal relocation** (rather than CDR-derived mobility) is the signal of interest.

------------------------------------------------------------------------

## Files

| File | Description |
|----|----|
| `processed/idp__individuals__static.matrix.csv` | All-time cumulative relocated individuals (zone × zone) |
| `processed/idp__individuals__weekly.matrix.csv` | Weekly relocated individuals by `week_start` |
| `processed/idp__individuals__monthly.matrix.csv` | Monthly relocated individuals (`date` = first day of month) |
| `raw/matrix_individuals_all_time.csv` | Upstream all-time matrix (`origin_hz` + `CD####ZS## \| NAME` columns) |
| `raw/matrix_individuals_by_week.csv` | Upstream weekly matrix (`week_start`, `origin_hz`, …) |
| `raw/matrix_individuals_by_month.csv` | Upstream monthly matrix (`month`, `origin_hz`, …) |
| `process.py` | Map ZSCode labels → canonical `Nom`; collapse duplicate Bunia codes |
| `metadata.yaml` | Provenance, licence, and pipeline notes |

**Dimensions:** **44 × 44** health zones per snapshot (not national 519×519).\
**Coverage:** Zones appearing in the IOM Ituri-round extract (Ituri, Nord-Kivu, and adjacent areas in the raw labels).\
**Temporal scope:** Weekly from **2016-02-15** to **2025-12-22**; monthly from **2016-02-01** to **2025-12-01** (see QA report).

------------------------------------------------------------------------

## Method

1. **Upstream source** — IOM DTM Mobility Tracking Round 14, Ituri (`IOM_DRC_MT_BLA_Ituri_R14_Jan2026`, public v3). The full workbook is cited in `metadata.yaml`; this repo stores **pre-built OD matrices** in `raw/` rather than the zip.
2. **Label parsing** — Row and column headers use `CD####ZS## | UPPER NAME`. `process.py` parses the **ZSCode** prefix and resolves to canonical `Nom` via `tools.lib.schema.zscode_to_canonical()` (authoritative).
3. **Legacy ZSCode** — If a code is absent from the current MoH shapefile (e.g. legacy `CD5401ZS01` for Bunia, merged in the current file into `CD5402ZS02`), the trailing name is title-cased and resolved via `to_canonical()` / `data/aliases.csv`.
4. **Collapse duplicates** — When two raw labels map to the same `Nom` (known case: duplicate Bunia-coded rows), **row and column vectors are summed** so the output matrix remains square on unique zone names.
5. **Export** — Contract filenames under `processed/` with `nom` as the origin key; time-series files add ISO `date` (months normalised to `YYYY-MM-01`).

**Units**

- Cell values: **count of individuals** relocated from origin zone to destination zone in the period (non-negative integers; empty cells treated as 0 on read).

**What this is not**

- Not national full-DRC coverage (44 zones only).
- Not the same methodology as Flowminder CDR relocation estimates.
- Not a symmetric matrix; treat `(i, j)` and `(j, i)` as directed flows unless you explicitly symmetrise.

------------------------------------------------------------------------

## CSV format

**Static matrix** (`idp__individuals__static.matrix.csv`):

- **First column:** `nom` (origin zone).
- **Remaining columns:** destination zone names.
- **Cell `(i, j)`:** all-time relocated individuals from origin `i` to destination `j`.

**Weekly / monthly matrices:**

- **Columns:** `date`, `nom`, then destination zone names (same order as static destinations).
- **Each row:** one origin zone for one time period.

**Example (reading in R):**

``` r
library(here)

static <- read.csv(
  here("data/IDP/processed/idp__individuals__static.matrix.csv"),
  row.names = 1, check.names = FALSE
)

# All-time flow from Bunia to Rwampara
static["Bunia", "Rwampara"]

weekly <- read.csv(
  here("data/IDP/processed/idp__individuals__weekly.matrix.csv"),
  check.names = FALSE
)
# Rows for Bunia in a given week
weekly[weekly$nom == "Bunia" & weekly$date == "2025-12-15", ]
```

Use `check.names = FALSE` when loading so column names are not altered.

------------------------------------------------------------------------

## Regenerating outputs

From the **repository root**:

``` bash
python data/IDP/process.py
```

**Requirements:** Python 3; repo `tools` package on `PYTHONPATH` (script adds repo root). No network access required.

**Outputs** (overwritten under `processed/`):

- `idp__individuals__static.matrix.csv`
- `idp__individuals__weekly.matrix.csv`
- `idp__individuals__monthly.matrix.csv`

Then validate:

``` bash
.venv/bin/python -m tools.qa
```

Matrix outputs are catalogued in `qa/matrix_log.csv` but **not** embedded in `build/drc_health_zones.geojson`.

------------------------------------------------------------------------

## Data quality and limitations

| Issue | Detail |
|----|----|
| **Partial national coverage** | 44 / 519 health zones; zones outside the IOM extract are absent from rows and columns. |
| **Duplicate Bunia in raw** | Raw data include both `CD5401ZS01 \| BUNIA` and `CD5402ZS02 \| BUNIA`; processing sums these into a single **Bunia** row/column. |
| **Directed flows** | Values need not be symmetric between origin and destination. |
| **Survey grain** | Round 14 Ituri-focused DTM release; interpret as **reported relocation** in that monitoring framework, not exhaustive population movement. |
| **ZSCode authority** | Prefer joins on `ZSCode` when matching back to shapefile attributes; `Nom` alone can collide (see `data/shapefiles/README.md`). |

------------------------------------------------------------------------

## Provenance

- **Provider:** [IOM DTM DRC](https://dtm.iom.int/drc) — *IOM DTM (2026). Mobility Tracking Round 14 - Ituri (IOM_DRC_MT_BLA_Ituri_R14_Jan2026, public version 3).*
- **Retrieved:** 2026-01-31 (`metadata.yaml`)
- **Geometry / join key:** `data/shapefiles/DRC_Health_zones.shp` (`Nom`, `ZSCode`)
- **Metadata:** `metadata.yaml`

For project-wide data conventions, see `data/README.md`.
