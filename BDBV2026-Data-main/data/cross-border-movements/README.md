# Cross-border passenger volumes (Uganda PoEs)

Mean **daily** and **weekly** passenger volumes at selected **Points of Entry (PoEs)** on the Uganda–DRC border, taken from sitreps cited in the [Imperial College London report on the 2026 DRC Ebola outbreak](https://www.imperial.ac.uk/mrc-global-infectious-disease-analysis/research-themes/preparedness-and-response-to-emerging-threats/report-ebola-18-05-2026/) (18 May 2026). PoEs are geocoded on the **Uganda** side of the border and assigned to the **nearest DRC health zone** for integration with other outbreak layers.

This vector dataset is merged into `build/drc_health_zones.geojson` as `cross_border__poe_passengers__static.csv` (property path `cross_border.poe_passengers` in the build snapshot).

------------------------------------------------------------------------

## Files

| File | Description |
|----|----|
| `processed/cross_border__poe_passengers__static.csv` | Per-zone PoE counts and summed mean passenger volumes |
| `raw/cross-border.csv` | Seven PoEs with sitrep counts and mean daily/weekly passengers |
| `poe_coordinates.csv` | Hand-curated WGS84 coordinates per PoE (Uganda-side OSM/Nominatim) |
| `process.py` | Nearest-zone assignment and aggregation |
| `metadata.yaml` | Provenance, licence, and pipeline notes |

**Coverage:** **7** PoEs → **7** DRC health zones (one PoE per zone in the current extract).\
**Provinces in raw data:** Ituri (4 PoEs), Nord Kivu (3 PoEs).\
**Temporal scope:** Static snapshot (means over sitreps with observations, not a daily time series).

------------------------------------------------------------------------

## Method

1. **Source table** — `raw/cross-border.csv` lists each PoE with:
   - province label,
   - number of sitreps contributing an observation,
   - mean weekly passengers **entering Uganda** through that PoE,
   - mean daily passengers (derived in the source).
2. **Geocoding** — `poe_coordinates.csv` supplies latitude/longitude per PoE name (Uganda side). Coordinates were looked up via OpenStreetMap / Nominatim; see `source_url` and `notes` per row. **Reviewers should treat coordinates as approximate.**
3. **Zone assignment** — For each PoE point, `process.py` finds the **nearest** DRC health-zone polygon from `data/shapefiles/DRC_Health_zones.shp` (WGS84, `shapely` STRtree). Because PoE points lie in Uganda, nearest-polygon correctly selects the DRC zone served by that crossing (e.g. Mpondwe, Uganda → **Mutwanga** or **Beni** area zone depending on geometry).
4. **Aggregation** — Metrics are **summed** when multiple PoEs map to the same zone (not applicable in the current seven-PoE extract; one PoE per zone).
5. **Export** — Contract vector file with columns `nom`, `n_poes`, `mean_daily_passengers`, `mean_weekly_passengers`, `poe_names` (pipe-separated list).

**Units**

- `mean_daily_passengers`, `mean_weekly_passengers`: **passenger counts** (means as reported in the Imperial/sitrep summary, rounded to integers on write).
- `n_poes`: count of PoEs assigned to that zone.

**What this is not**

- Not DRC-side exit counts; the raw metric is passengers **entering Uganda**.
- Not a complete inventory of all border crossings in eastern DRC.
- Not GPS-traced individual movements; sitrep-reported aggregates only.

------------------------------------------------------------------------

## CSV format

**Processed vector** (`cross_border__poe_passengers__static.csv`):

| Column | Description |
|----|----|
| `nom` | Canonical health zone name |
| `n_poes` | Number of PoEs assigned to this zone |
| `mean_daily_passengers` | Sum of mean daily passengers across PoEs in the zone |
| `mean_weekly_passengers` | Sum of mean weekly passengers across PoEs in the zone |
| `poe_names` | PoE labels from the raw file, joined with `\|` |

**Example (reading in R):**

``` r
library(here)

poe <- read.csv(
  here("data/cross-border-movements/processed/cross_border__poe_passengers__static.csv"),
  check.names = FALSE
)

# Mahagi zone (Goli crossing)
poe[poe$nom == "Mahagi", ]
```

Zones with no assigned PoE are **omitted** from the file (sparse vector; only border-adjacent zones with data appear).

------------------------------------------------------------------------

## Regenerating outputs

From the **repository root**:

``` bash
python data/cross-border-movements/process.py
```

**Requirements:** Python 3; `pyshp`, `shapely`; repo `tools` package (`tools.lib.schema`). No network access required unless you refresh coordinates.

**Output** (overwritten):

- `processed/cross_border__poe_passengers__static.csv`

Refresh the GeoJSON build after changes:

``` bash
.venv/bin/python -m tools.qa
.venv/bin/python -m tools.build_geojson
```

------------------------------------------------------------------------

## Data quality and limitations

| Issue | Detail |
|----|----|
| **Sparse coverage** | 7 / 519 zones only; most zones have no cross-border passenger field in the GeoJSON. |
| **Hand-curated coordinates** | `poe_coordinates.csv` must list every PoE in `raw/cross-border.csv`; missing names raise a runtime error. |
| **Nearest-zone heuristic** | Assignment uses geometric nearness, not official administrative pairing; verify critical PoE–zone links manually. |
| **Uganda-side points** | Coordinates are on the Uganda side by design; nearest DRC polygon is intentional. |
| **Header fragility** | `process.py` normalises raw column names (case/spacing); substantive column renames in the source CSV will fail with a clear error. |
| **Sitreps sample** | `Number of sitreps with an observation` varies by PoE (1–4 in the current file); means are not weighted by sitrep count in `process.py`. |

**Current zone ↔ PoE mapping (processed extract):**

| Zone (`nom`) | PoE |
|----|----|
| Mahagi | Goli |
| Boga | Ntoroko Main |
| Ariwara | Odramacaku |
| Aru | Vurra |
| Binza | Busanza |
| Kamango | Busunga |
| Mutwanga | Mpondwe |

------------------------------------------------------------------------

## Provenance

- **Report:** [Imperial College London MRC GIDA — Report on the DRC Ebola outbreak, 18 May 2026](https://www.imperial.ac.uk/mrc-global-infectious-disease-analysis/research-themes/preparedness-and-response-to-emerging-threats/report-ebola-18-05-2026/)
- **Retrieved:** 2026-05-18 (`metadata.yaml`)
- **Geometry:** `data/shapefiles/DRC_Health_zones.shp`
- **Coordinates:** `poe_coordinates.csv` (OpenStreetMap / Nominatim)
- **Metadata:** `metadata.yaml`

For project-wide data conventions, see `data/README.md`.
