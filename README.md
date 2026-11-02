# india-mandi-arrivals

Open extracts of India's agricultural **mandi arrivals and prices** (Agmarknet) joined with official **crop area,
production, yield, MSP, procurement, prices and trade** (UPAG), plus the stdlib-only collectors that fetch them and
the analysis scripts that turn them into insight tables (CSV, `reports/INSIGHTS.md`), Excel workbooks and SVG charts.

> Status: active. Data is an unofficial point-in-time extract of Government of India open data (GODL-India);
> check figures against the portals before relying on them. Not investment or policy advice.

## What it does
- Collects Agmarknet masters, state x commodity x month prices and arrivals, and a sampled market x day panel.
- Collects UPAG area/production/yield (state, district, all-India), MSP, WPI, FCI procurement, trade and the crop calendar.
- Joins the two to show how much of a state's output passes through mandis, how often mandi prices sit below MSP,
  which crops and states have the steadiest and most volatile prices, and which mandis dominate each crop.
- Clusters states by crop-area mix and commodities by price behaviour (k-means); builds 16 crop profiles.
- Rebuilds the Excel workbooks and charts behind the masaladeutsch posts of 24 October 2026.

## Quick start
```bash
git clone https://github.com/herrrickshaw/india-mandi-arrivals.git
cd india-mandi-arrivals
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # analysis only; collectors need just the standard library
python analysis/build_insights.py          # writes reports/*.csv and reports/INSIGHTS.md from data/
```

Refreshing the data from the portals (live network, resumable):
```bash
python3 collectors/agmarknet_collect.py masters
python3 collectors/agmarknet_collect.py state-monthly --from 2019-01 --to 2026-10
python3 collectors/agmarknet_collect.py market-sample --from 2025-11-01 --to 2026-10-23 --step 6
python3 collectors/upag_collect.py all
python analysis/clusters.py && python analysis/crop_profiles.py
```

## How it works
| Stage | Module | Output |
|---|---|---|
| HTTP clients (throttled, 429 back-off) | `indiagri/agmarknet.py`, `indiagri/upag.py` | parsed JSON |
| Pure row logic (merge, filter, de-duplicate) | `indiagri/transform.py` | row dicts |
| Gzipped CSV writer and JSON response cache | `indiagri/io.py` | `data/**/*.csv.gz`, `.cache/` |
| Collectors (CLI) | `collectors/agmarknet_collect.py`, `collectors/upag_collect.py` | `data/agmarknet/`, `data/upag/` |
| Analysis | `analysis/build_insights.py`, `clusters.py`, `crop_profiles.py` | `reports/` |
| Workbooks and charts | `analysis/workbooks/*.py`, `analysis/post_charts.py`, `analysis/crop_charts.py` | `.xlsx`, `.json`, `.svg` |

Design notes:
- Every API response is cached under `.cache/` (gitignored), so an interrupted run resumes.
- Agmarknet returns HTTP 429 when called quickly: the client allows one request per 1.5 s and backs off.
  A full `state-monthly` refresh takes about an hour.
- Agmarknet arrival rows carry no `cmdt_id` (price rows do), so state-monthly rows are keyed on commodity name.
  Dashboard paging uses a `page` field in the request body, not the query string.
- UPAG reports are Plotly Dash pages; the collectors call their data callbacks directly. That is an internal UI
  contract, so a redeploy of upag.gov.in can change it. Endpoint catalogues (parameters, coverage, how to
  re-capture a callback) are in [`docs/agmarknet_api.md`](docs/agmarknet_api.md) and [`docs/upag_api.md`](docs/upag_api.md).
- Endpoints that need a login or captcha (lot-wise trades, some reports) are deliberately not wrapped.
- Fields naming officials or giving phone numbers or emails are dropped on write (`PRIVATE_FIELDS` in `indiagri/io.py`).

## Repository layout
| Path | Purpose |
|---|---|
| `indiagri/` | API clients, pure transforms and I/O helpers (stdlib only) |
| `collectors/` | CLI collectors writing `data/` |
| `analysis/` | Insight tables, clustering, crop profiles, `workbooks/` and chart scripts |
| `data/` | Tracked gzipped CSV extracts (`agmarknet/`, `upag/`, `external/`) |
| `crosswalks/` | Agmarknet to UPAG commodity and state name maps, with unit conversions |
| `reports/` | Generated insight tables and `INSIGHTS.md` |
| `docs/` | Endpoint catalogues for both portals |
| `tests/` | Offline pytest suite |

## Data sources
| Source | What is taken | Access route | Licence / caveat |
|---|---|---|---|
| [Agmarknet](https://agmarknet.gov.in/) (Directorate of Marketing & Inspection) | Prices, arrivals, masters | Public JSON API, no login | GODL-India; scraped by collector |
| [UPAG](https://upag.gov.in/) (Dept. of Agriculture & Farmers Welfare) | APY, MSP, WPI, FCI, trade, calendar | Public Dash callbacks and REST subset | GODL-India; scraped by collector |
| Dept. of Fertilizers urea sales | `data/external/urea_state_2025_26.csv` | Tabulated in [this post](https://masaladeutsch.blogspot.com/2026/08/379-kilos-hectare-in-punjab-44-in.html) | Secondary source |
| [DataMeet maps](https://github.com/datameet/maps) | State boundaries for `post_charts.py` | Supplied by the caller as a GeoJSON path | Not stored in repo |

### Canonical data files
Each file is the one authoritative copy of that dataset in this repo.

| File | Source / report | Grain | Coverage |
|---|---|---|---|
| `data/agmarknet/state_monthly.csv.gz` | Agmarknet `statewise_price_arrival_sp` | commodity x state x month: weighted-average price (Rs/qtl) and arrivals (t) | 455 commodities reported in the window, Jan 2019 – Oct 2026 (203,798 rows) |
| `data/agmarknet/market_daily_sample.csv.gz` | Agmarknet `market_details_sp` | market x commodity x day: arrivals (t), modal price | 23 field crops, every 6th day, Nov 2025 – Oct 2026 (60 days) |
| `data/agmarknet/masters/*.csv.gz` | Agmarknet master lists | commodities (605), groups, grades, units, varieties (2,154), states, districts (750), markets (4,175), market directory (4,906 with address and category) | current |
| `data/upag/apy_state.csv.gz` | UPAG `statewiseapy` | state x season x crop x crop year: area, production, yield | 1997-98 – 2025-26 (latest = advance estimates) |
| `data/upag/apy_district.csv.gz` | UPAG district APY dataset | district x season x crop x crop year | food grains, oilseeds, commercial crops, 2015-16 – 2024-25 |
| `data/upag/apy_all_india.csv.gz` | UPAG `allindiaapy` | crop x season x crop year | 1966-67 – 2025-26 |
| `data/upag/msp.csv.gz` | UPAG MSP statement (CACP) | crop x marketing year | 2010-11 – 2026-27 |
| `data/upag/wpi_monthly.csv.gz` | UPAG WPI report | 41 agri items x month | Apr 2012 – Sep 2026 |
| `data/upag/fci_procurement.csv.gz` | UPAG FCI procurement | state x marketing year, rice and wheat | 2016-17 – 2025-26 |
| `data/upag/trade.csv.gz` | UPAG DGCIS trade | commodity x fiscal year, exports and imports | 2015-16 – 2025-26 |
| `data/upag/crop_calendar.csv.gz` | UPAG domestic crop calendar | state x crop x month (colour-coded sowing/harvest) | current |
| `data/external/urea_state_2025_26.csv` | Department of Fertilizers 2025-26 urea sales by state, as tabulated in [this post](https://masaladeutsch.blogspot.com/2026/08/379-kilos-hectare-in-punjab-44-in.html) | state: urea sales (LMT), share of cropped area, kg urea per hectare | 2025-26, 18 states |

Units are as published: prices Rs/quintal, arrivals tonnes, production lakh tonnes (cotton in 170 kg
bales), area lakh hectares, yield kg/ha.

`crosswalks/` maps Agmarknet commodity and state names to UPAG's, including the conversions needed
to compare them (paddy x 0.67 to milled rice; cotton not comparable: seed cotton vs lint bales).

`crosswalks/` maps Agmarknet commodity and state names to UPAG's, including the conversions needed to compare
them (paddy x 0.67 to milled rice; cotton not comparable: seed cotton vs lint bales).

### Insight tables (`reports/`)
`python analysis/build_insights.py` writes:

| File | What it shows |
|---|---|
| `arrivals_share_of_production.csv` | mandi arrivals / production, state x crop x crop year (July–June) |
| `mandi_vs_msp.csv` | each state-month mandi price against the MSP of the matching marketing year |
| `volatility_seasonality.csv` | typical monthly price move (median absolute change since 2023), cheapest and dearest months, peak arrival month |
| `yield_trends.csv` | all-India yield growth by crop, on three-year averages |
| `area_by_crop.csv` | all-India area by crop, latest year vs ten years earlier |
| `top_mandis.csv` | estimated annual arrivals per mandi and its main crop |
| `state_crop_clusters.csv`, `state_cluster_centroids.csv` | k-means (k = 5) of states by crop-area mix, latest three crop years (`analysis/clusters.py`) |
| `crop_profiles.csv`, `crop_top_states.csv`, `crop_top_districts.csv`, `crop_state_yield_gaps.csv` | 16 crops: production, area and yield growth 2003-06 to 2023-26 split into area and yield, year-on-year volatility, records, top states and districts, state yield gaps (`analysis/crop_profiles.py`; charts via `analysis/crop_charts.py outdir/`) |
| `crop_price_clusters.csv` | k-means (k = 4) of 217 commodities by typical monthly price move, seasonal spread and peak-month arrival share |
| `INSIGHTS.md` | headline tables from all of the above |

### Workbooks and blog charts
Scripts read only from `data/` and `reports/`; workbook formulas recalculate in Excel or LibreOffice.

| Script | Output |
|---|---|
| `analysis/workbooks/statewise_rice_maize.py out.xlsx` | state-wise maize, rice and broken-rice prices: seasonality, dip months, six-month carry test, spread vs all-India |
| `analysis/workbooks/crop_ranking.py out.xlsx out.json` | 23 crops x state: arrivals, typical monthly price move, trimmed price range, ranks |
| `analysis/workbooks/mandi_leaders.py out.xlsx out.json` | top mandis nationally, per crop, per state and per state-crop (from the market sample) |
| `analysis/post_charts.py states.geojson outdir/` | the seven charts of "India's Farm Map in Seven Charts" (area, yields, state maps, k-means maps and scatter, seasonality, urea vs yield); boundaries from [DataMeet](https://github.com/datameet/maps) |

## Configuration
No environment variables and no credentials. Tunables are constants at the top of the modules:
`MIN_INTERVAL`, `MAX_RETRIES`, `TIMEOUT` in `indiagri/agmarknet.py`; `BATCH_SIZE` and `CORE` (the 23 field crops
used for the market sample) in `collectors/agmarknet_collect.py`. Raw responses are cached in `.cache/`.

## Testing
```bash
pip install pytest ruff
ruff check indiagri collectors tests
pytest -q
```
The suite is offline: network calls are stubbed and no live portal is contacted.

## Limitations and known issues
- **Arrivals are what markets report.** Markets that report irregularly are understated. Grain bought
  directly by government agencies or traded outside APMCs is missing. Agmarknet widened its market
  coverage from November 2025, so recent arrivals are not comparable with earlier years.
- **Shares above 100%** of production usually mean grain arriving from other states, or paddy
  purchased at support price being recorded as arrivals (Chhattisgarh), not an error in either source.
- **Some state series barely move** (for example paddy in Odisha) because markets report the support
  price. Treat near-zero volatility as a reporting pattern, not a market fact.
- **Prices mix varieties and grades** within a commodity. UPAG's latest year is an advance estimate.
- `cumm_arrival_sp` (district cumulative arrivals) does not reconcile with market-level data and is not
  used. Lot-wise trades and some reports need a login or captcha and are out of scope.
- The market sample is every 6th day. Annual figures are sampled tonnes x 6, which is fine for
  ranking but approximate in level.
- UPAG's latest crop year is an advance estimate; the redeploy risk of the Dash callbacks is noted above.
- `analysis/` is not yet under ruff or unit tests (Phase 2).

## Related repositories
None required; the analysis posts are on [masaladeutsch](https://masaladeutsch.blogspot.com/).

## Licence
Code: MIT (`LICENSE`). Data: Government of India open data, re-published under GODL-India with attribution; see
[`DATA_LICENSE.md`](DATA_LICENSE.md). The GitHub repo is the primary copy of the data; files are kept small
(gzipped CSV, no Git LFS) and everything can be rebuilt from the portals with the collectors above.
