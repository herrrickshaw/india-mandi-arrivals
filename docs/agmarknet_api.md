# Agmarknet 2.0 public API catalogue

Base: `https://api.agmarknet.gov.in/v1/`. Surveyed 2026-10-24 from the SPA bundle
(`static/js/main.c1f86740.js` + its 281 lazy chunks) and one test call per endpoint.
Raw responses: `samples/` (client smoke test) and `samples/probes/r1..r11/` (discovery calls,
including the 403/captcha refusals). Client: `agmarknet_client.py` (stdlib only).

Conventions
- Send `User-Agent: Mozilla/5.0`. JSON bodies need `Content-Type: application/json`.
- Rate limit: 429 (HTML body) when hit fast. `dashboard-data/` is the sensitive one: it gave
  sustained 429s while another job was calling it with two threads; GET endpoints kept answering
  in the same period, so the limit looks per-endpoint. Keep to 1 request every 1.5 s or slower overall.
- Three access classes:
  - **Public**: 200 without any header. These are listed below.
  - **Auth**: 403 `{"detail":"Authorization header missing"}`. Skipped.
  - **Captcha**: 400 `{"code":"TOKEN_OR_CAPTCHA_REQUIRED"}`, needs `captcha_key` + `captcha`
    (from `/captcha/generator`) or a login token. Skipped (no captcha solving).
- Sentinel ids: 100000 all groups, 100001 all commodities, 100002 all markets, 100004 all market
  types, 100005 All India, 100006 all states, 100007/100008 districtwise or all districts,
  100009/100010 marketwise or all markets, 100011 all grades. These differ slightly between
  filter sets, so read the relevant `*filters` response first.
- Units: prices are Rs./Quintal. Arrivals are in metric tonnes in the price-trend reports. In
  dashboard-data the unit is per commodity (`arrival_unit_name` in the commodity master, e.g.
  Tonne, Nos, Bales).

---------------------------------------------------------------------------------------------

## 1. Master lists (all public, GET, no paging needed)

| Endpoint | Returns | Notes |
|---|---|---|
| `daily-price-arrival/filters` | **One-shot bundle**: `cmdt_data` 605 (id, name, group), `cmdt_group_data` 16, `grade_data` 18, `variety_data` 2154 (with cmdt_id), `state_data` 37, `district_data` 751 (state_id), `market_data` 4176 (state_id, district_id), `type_data`, `range_data` (price/arrival from 2021-01-01; max 1-year window) | Best single master call (~525 KB) |
| `dashboard-filters/?dashboard_name=<n>` | Same shape, scoped to a dashboard. Valid `n`: `cumm_faq`, `cumm_arrival`, `cumm_price`, `cumm_data`, `market_details`, `statewise_price_arrival`, `marketwise_price_arrival`, `season_price_arrival`, `commodity_msp`, `prevailing_market_below_msp` (the `_sp` suffix is invalid) | Shows which commodities each dashboard supports (e.g. `commodity_msp` lists MSP crops only) |
| `commodities?page=N&page_size=500` | 605 commodities with `varieties[]`, `grades[]`, `arrival_unit_name`, `price_unit_name`, `is_msp`, `comm_code`, `importance`, multilingual names | Ignores page_size: every page returns all 605 and `next_page` is always set. De-dupe by id |
| `Commoditygroup?page_size=500` | 16 groups (desc, status) | |
| `commodity/commodity-group` | 16 groups (id, name, group_code) | |
| `commodity/grade` | 17 grades (FAQ, Grade A/B/C, ranges...) | `grade?...` is auth |
| `commodity/unit` | 37 units (Bag-100kg, Tonne, Nos...) | `units?...` is auth |
| `commodity/variety` | 2154 varieties (id, name), no commodity link | Link via `daily-price-arrival/filters.variety_data` or `commodities[].varieties` |
| `location/state?page_size=100` | 36 states with nested `districts[]` (LGD codes, district_code), state codes, zone, contact emails, multilingual names | |
| `market-district-state` | 4175 markets: market_id, name, district_id/name, state_id/name | Flat list |
| `dashboard-market-filter` | **4906 markets** with `mkt_address` (often has PIN), `mkt_category` (Principal/Sub Market Yard, Farmer Consumer, Private, Regulated, Other), `mkt_area_served`, `api_allowed_market`, `status` | Richest market list; includes inactive markets |
| `list-market-category`, `market-category-filter` | 4 or 6 market categories (FCM, PMY, PVT, SMY, RMY, Other) | |
| `dashboard-commodities-filter` | 608 commodities as the home dashboard shows them (pseudo groups such as 9999 MSP Commodities) | |
| `dashboard-season-filter` | Kharif and Rabi marketing seasons | |
| `gis-mapping/filters` | 27 MSP commodities with `is_msp`, markets with `market_category_id`, `msp_type` (Above/Below MSP), report types (Reported, Non-reported, Nil-transaction, Holiday markets), date note (2021 onward) | The atlas data calls themselves need a captcha |
| `guest-msp-commodity`, `all-type-report/msp-commoditygroup-filter`, `all-type-report/commoditygroup-filter`, `all-type-report/state-api-filter` | Small filter lists (MSP groups; states with an API integration: CG, KA, MP, MH...) | |
| `price-trend/{year,state,month,week,district}-filter` | Per-commodity availability: `?commodity=1` (year/state), `&year=` (month), `&month=` (week 1–4), `&state=` (district) | Wheat: 2021–2026 |
| `agmarknet-live-date` | `11-07-2025`, the date the new portal went live | Possibly the boundary of native (not migrated) data |
| `market-profile/months`, `market-profile/market-profile-functionaries`, `market-profile-dropdown?category_id=1|2&subcategory_id=` | Lookups for the market-profile fields | |

Auth-only masters (skipped): `grade?`, `units?`, `variety?`, `market`, `list-market`, `holiday-type`,
`msp-cmdt` (MSP values), `season-state`, `language`, `commodity-varieties`, `commodity-dropdown-msp`,
`all-type-report/grade-filter`, `market-holiday` (admin list), `belowmsp-filters`, `pms-filters`.

---------------------------------------------------------------------------------------------

## 2. `POST dashboard-data/` (public)

Body `{"dashboard": <name>, ...fields, "limit": <=500, "page": N, "format": "json"}`. The bundle builds
these fields (only the ones that apply to each dashboard are sent): `date` (YYYY-MM-DD), `from_date`/`to_date`
(only for `cumm_arrival_sp`, `cumm_price_sp`, `statewise_price_arrival_sp`), `group[]`, `commodity[]`,
`variety` (marketwise/season only), `state` (scalar for statewise/marketwise/season, else list),
`district[]`, `market[]`, `market_type[]`, `grades[]`, `season[]`, `year` (season: scalar or list),
`type` (`statewise_price_arrival_sp` 100016 price / 100017 arrival; `cumm_data_sp` 100004 or 100005),
`status` (comma-joined reporting statuses), `min_qty`/`max_qty`, `downloadreport`
("true"/"false"), `downloadformat`. Response: `{status, data:{records:[...], ...}, pagination:{total_count,
total_pages, current_page, next_page, items_per_page}}`.

Verified in the smoke test (`samples/*.json`):

| dashboard | Key fields | Grain | Record fields |
|---|---|---|---|
| `statewise_price_arrival_sp` | commodity[], type 100016/100017, from_date, to_date | state × commodity, weighted over the window | as_on, one/two/three_yr_ago, deviation_percent_* (one call gives four years of the same window) |
| `market_details_sp` | commodity[] (many allowed), date | **market × commodity × day** | mkt_id, mkt_name, district, state, status (Reported or Non-reported Markets), arrival_qty, modal_price_wt, units. Wheat on one day: 945 rows |
| `marketwise_price_arrival` | commodity[], from/to | all-India × commodity, last 3 report days | as_on/1/2-day-ago price and arrival, **msp_price (current year)**, trend |
| `cumm_arrival_sp` | commodity[], state[], from/to | district cumulative arrivals | as_on, one/two/three_yr_ago, trend |

Not verified (dashboard-data was returning 429 under a concurrent bulk job). Fields are taken from the JS:
`cumm_data_sp` (price trend; `type` 100004 price / 100005 arrival; date, state, district, market), `cumm_avg_data_sp`,
`cumm_faq_sp` (price report by grade), `cumm_price_sp` (from/to + date), `commodity_msp_sp` (MSP versus
market price), `season_price_arrival` (scalar or list `year`, `season`, `variety`, `state`),
`prevailing_market_below_msp` (markets trading below MSP). Their filter masters
(`dashboard-filters/?dashboard_name=...`) are all public. These are the public route to MSP comparisons.

**Download**: `downloadreport:"true"` + `downloadformat` (`csv`/`excel`/`pdf`). **Works without auth**. Tested with statewise_price_arrival_sp: csv returns text/csv
(title rows plus a two-level header) and excel returns xlsx (`samples/dashboard_download_*`). The export appears to
return all rows in one file with no paging, which makes it the cheapest bulk path for `market_details_sp`
(one file per day for many commodities). Inferred from the code path, not size-tested.

**cumm_arrival_sp inconsistency (flag)**: for Madhya Pradesh, wheat, 1–30 April 2025, the district rows of
`cumm_arrival_sp` sum to **1.686 Mt** (48 districts). The market rows of `price-trend/wholesale-arrivals-monthly`
(MarketwiseAll, the same month) sum to **2.528 Mt** (270 markets). That is about 33% lower for the same scope. Treat
`cumm_arrival_sp` as not reconcilable until this is explained. Use market-level sources (`market_details_sp`
daily, or price-trend MarketwiseAll monthly) and aggregate them yourself.

Other caveats: `limit` is capped at 500. `next_page` is an absolute URL, but paging works only through
`"page"` in the body. Commodity arrival units vary (check `unit_name_arrival`).

---------------------------------------------------------------------------------------------

## 3. Price-trend analysis reports (public GET, with server-side CSV/XLSX/PDF export)

`GET price-trend/<report>?report_mode=&commodity=&year=&month=[&week=]&state=&district=&export=false`

| `<report>` | Grain | `report_mode` accepted |
|---|---|---|
| `wholesale-prices-monthly` | month | Statewise, Districtwise (state), Marketwise (state+district), MarketwiseAll (state) |
| `wholesale-prices-weekly` | week 1–4 of month | same |
| `wholesale-arrivals-monthly` | month | **Marketwise, MarketwiseAll only** (Statewise or Districtwise → 400 "Invalid report_mode") |
| `wholesale-arrivals-weekly` | week | Marketwise, MarketwiseAll only |
| `varietywise-prices-monthly` | month × variety | Statewise, Districtwise, Marketwise |
| `varietywise-prices-weekly` | week × variety | same |

- Params: `commodity` = commodity id (scalar). `state=0`/`district=0` mean none. `week` 1–4, where
  week 1 = days 1–8 and week 2 = days 9–15 (taken from the column labels). Missing `month` → HTTP 500.
- Response: `{title, data:[{key:'region_info'|'prices'|'arrivals'|'percentage_change', columns:[{key,title}]}],
  rows:[{state|district|market[,variety], prices_<mon>_<yyyy>..., change_over_previous_month,
  change_over_previous_year}]}`. Each row gives the current period, the previous period and the same
  period last year, so one call returns three time points.
- Coverage: years from `price-trend/year-filter` (2021 onward for wheat). One commodity per call.
- **Export without auth**: add `export=true&downloadformat=csv|excel|pdf`. The bundle calls this with
  a plain `fetch()` and no token; tested csv (text/csv) and excel (xlsx), both 200. CSV has a title row
  and then a header row.
- Caveat: `varietywise-prices-monthly` with Statewise (all-India) timed out at 60 s once. Districtwise
  is fast. Use a timeout of 180 s or more.
- Best bulk path for market-level arrivals: `wholesale-arrivals-monthly` with MarketwiseAll and a state
  returns every market in that state for one month in one call (MP wheat, April 2025: about 250 markets).

## 4. Last-week daily prices (public GET)

- `prices-and-arrivals/market-price/lastweek?marketId=&stateId=&commodityId=&includeExcel=false`
  returns the modal price for each of the last 7 days for one market × commodity, one row per variety
  (`"Indore APMC - Malwa Shakti"`). `"NR"` means not reported. `includeExcel=true` returns an xlsx.
- `prices-and-arrivals/commodity-price/lastweek?...` has the same shape, labelled by commodity and variety.
- Granularity: market × variety × day, last 7 days only. Prices only, no arrivals. Useful for variety
  detail at daily grain, but needs one call per market.

## 5. Market metadata (public GET)

- `market-profile-categorywise?category_id=C&subcategory_id=S&market_id=M`. Sections (C,S):
  (1,1) General: **latitude, longitude**, address, establishment year, population served, area served,
  revenue and season category, phone/email; (1,2) Administrative: regulation status and year, staff
  counts, chairman/secretary names and phones; (1,3) Rail/Road; (1,4) Market area: sub-yards, notified
  area, cold storages, processing units; (2,5) Functionaries; (2,6) Transactional methods (system of
  sale, weighment); (2,7) Transport; (3,0) Important commodities; (4,0) Licensed functionaries;
  (5,8) Facilities; (5,9) **Market charges** (market fee %, commission, weighment, hamali);
  (5,10) Financials. `data` is null when a market has not filled that section.
  Caveat: sections (1,1) and (1,2) contain officials' names and personal phone numbers. Do not
  republish those fields in an open-data repo.
- `market-profile-holiday?id=<market_id>` returns `{year, total_no_of_holidays, holiday[]}`. Indore
  and Lasalgaon both returned 0 holidays and `available_years: []`, so this is sparsely populated.
- The combined `market-profile?market=&state=&district=` needs a captcha. Call the categorywise
  endpoint once per section instead.

## 6. Content lists (public, not data)
`whatsnew`, `market-intelligence` (IMC PPTs), `agmarkview`, `faq`, `faq_category`. Their `/<id>/view`
and `/<id>/download` URLs were not tested.

---------------------------------------------------------------------------------------------

## 7. Not public (catalogued, skipped)

Captcha-gated (400 TOKEN_OR_CAPTCHA_REQUIRED):
- `POST daily-price-arrival/report` (the main "Price & Arrival report", any date range ≤1 y)
- `prices-and-arrivals/commodity-market/daily-report-state[-marketwise]`, `commodity-wise/daily-report-state`,
  `date-wise/specific-commodity`, `market-report/specific`, `POST market-report/daily`,
  `POST commodity-market/daily-report-weighted`, `trans-above-msp`, `trans-below-msp`
  (these are the old "all type of reports": daily state/market reports and above/below-MSP transactions)
- `POST all-type-report/all-type-report-agm` (commodity-wise major markets / mandi arrival tables)
- `POST gis-mapping/map-data`, `POST gis-mapping/market-details` (GIS atlas: per-market lat/lng,
  nearby markets, commodity arrival breakdown)
- `market-profile?market=&state=&district=`

Auth-only (403): `all-type-report/commodity-wise-major-market`, `.../commodity-wise-mandi-arrival`,
`.../nil-transactions`, `.../no-entry-report`, `belowmsp-report`, `cmdt-below-msp-report`,
`pms-market-summary`, `msp-cmdt`, `market-holiday`, `documents-repository`, `market-preference`,
`personalized-dashboard*`, all `data-entry/*` (including lot-wise trades and the historic lot-wise
data), `view-submission*`, `approved-data`, `price-trigger*`, user/ticket/admin endpoints.
**Lot-wise (per-trade) data is only reachable through the data-entry and submission endpoints for
logged-in market users. No public path to lot-wise trades was found.**
