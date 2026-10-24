# india-mandi-arrivals

Open extracts of India's agricultural **mandi arrivals and prices** (Agmarknet) joined with official
**crop area, production, yield, MSP, procurement, prices and trade** (UPAG). Every dataset here is
pulled from public, login-free endpoints of the two government portals by small, resumable,
stdlib-only collectors, and analysis scripts turn them into insight tables.

- **Agmarknet** (Directorate of Marketing & Inspection): what reaches regulated wholesale markets
  (APMCs/mandis), and at what price, by market, district, state and day.
- **UPAG** (Unified Portal for Agricultural Statistics, Dept. of Agriculture & Farmers Welfare): what
  was grown (area, production, yield by state and district), MSP, WPI, FCI procurement, trade and the
  crop calendar.

Joining them answers questions neither portal answers alone: how much of a state's output passes
through mandis, how often mandi prices sit below MSP, which crops and states have the steadiest and
most volatile prices, and which mandis dominate each crop. See [`reports/INSIGHTS.md`](reports/INSIGHTS.md).

## What's in `data/` (canonical files)

Each file below is the one authoritative copy of that dataset in this repo; there are no duplicates.

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

## Insight tables (`reports/`)

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
| `crop_price_clusters.csv` | k-means (k = 4) of 217 commodities by typical monthly price move, seasonal spread and peak-month arrival share |
| `INSIGHTS.md` | headline tables from all of the above |

## Running it

```bash
python3 collectors/agmarknet_collect.py masters
python3 collectors/agmarknet_collect.py state-monthly --from 2019-01 --to 2026-10
python3 collectors/agmarknet_collect.py market-sample --from 2025-11-01 --to 2026-10-23 --step 6
python3 collectors/upag_collect.py all
pip install -r requirements.txt && python analysis/build_insights.py && python analysis/clusters.py
```

Collectors need only the Python standard library. Responses are cached under `.cache/` (gitignored), so
an interrupted run resumes. Agmarknet returns HTTP 429 when called quickly: the client throttles to
about one request every 1.5 s and backs off. A full refresh of `state-monthly` takes about an hour.

Endpoint catalogues, with parameters, coverage and caveats, are in
[`docs/agmarknet_api.md`](docs/agmarknet_api.md) and [`docs/upag_api.md`](docs/upag_api.md).
UPAG's reports are Plotly Dash pages, and the collectors call their data callbacks directly. That is an
internal UI contract, so a redeploy of upag.gov.in can change it; the catalogue explains how to
re-capture a callback.

## Caveats

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

## Data licence and backup

Code: MIT. Data: Government of India open data, re-published under GODL-India with attribution. See
[`DATA_LICENSE.md`](DATA_LICENSE.md). Fields naming officials or giving phone numbers or emails are
dropped. The GitHub repo is the primary copy of the data; the files are kept small (gzipped CSV, no
Git LFS), and everything can be rebuilt from the source portals with the collectors above.
