# UPAG (upag.gov.in) data access: endpoint catalogue

Researched 2026-10-24. Read-only. No login, no account. Client: `upag_client.py`. Raw samples: `samples/`.

## Architecture: three backends

| Backend | Base | Auth | Use |
|---|---|---|---|
| React SPA shell | `https://upag.gov.in/` | none | navigation only; every report is an `<iframe>` to the Dash server |
| **Plotly Dash server** | `https://dash.upag.gov.in/` | **none** | **all dashboards/reports. Main public data route.** |
| Portal REST API | `https://api-prd.upag.gov.in/v1/upagapi/` | JWT cookie for most paths | about 6 public GETs (homepage, crop calendar, report catalogue) |
| Official "Open API" | `https://data.upag.gov.in/api/v1/...` (ReDoc at `/redoc`, spec `/api/v1/openapi.json`) | **OAuth2 password login (registered user)** | not used. Spec saved as `samples/data_upag_openapi.json` |

The config block in `main-134b812a.*.js` names `APIBaseURI`, `DashReportUrl`, `OPENAPI`. The endpoint map is the webpack module `37307`, saved as `samples/portal_endpoint_map.js`.

### Gated Open API (for reference)
`POST /v1/upag/api-data-share/sources/{source}` with `{"source_input_object":{"source_name":..,"year":[..],"location_granularity":"state","limit":<=10000,"offset":..}}`.
Sources: dafw_state, dafw_district, mncfc, ieg, dcs (village area), fci_procurement, fci_stock, dgcis, farmers_survey, nsso, cwwg, pmfby_ay, trs, state_reported, **agmarknet, enam**, doca, horticulture, sopa, wpi, ncdex, pink_sheet. Also `/apy/statewise`, `/apy/districtwise`, `/crop/production`, `/crop/master`.
All need a Bearer token from `/login` (username/password issued by DA&FW). This is the cleanest bulk route if the project applies for credentials. Unauthenticated calls return 401 or 404.

## How the Dash route works

Every report page (`https://dash.upag.gov.in/<page>?t=&stateID=0&rtab=x&rtype=reports`) has:
- a `<prefix>-filters-store` (dict of selected filters), and
- one "data" callback whose only input is `<prefix>-filters-store.data`. Its output includes a `*store.data` / `*idstore.data` holding **tidy long-format JSON rows** (the AG-Grid feed).

You call that callback directly:
```
POST https://dash.upag.gov.in/_dash-update-component
Content-Type: application/json
{"output": "<exact registered multi-output string>",
 "outputs": [{"id":..,"property":..},...],
 "inputs": [{"id":"<prefix>-filters-store","property":"data","value":{...filters...}}],
 "changedPropIds": ["<prefix>-filters-store.data"],
 "state": [{"id":"url","property":"search","value":"?t=&stateID=0&rtab=x&rtype=reports"}]}
```
-> `{"multi":true,"response":{"<store-id>":{"data":[rows...]}, "<title-id>":{...}}}`

- The `output` string must exactly match a registered callback. All 825 are in `GET /_dash-dependencies` (`samples/dash_dependencies.json`).
- Filter dicts below were captured from the live UI's default "Apply" (browser fetch intercept). To add another report: open it, intercept `_dash-update-component`, click FILTERS → APPLY, and copy the largest response's request.
- No cookies, CSRF or tokens needed. UA `Mozilla/5.0` is fine. Latency is 0.4–12 s. No rate-limit headers were seen. I made ~25 calls with no throttling, but keep it polite (≥1 s between calls).
- Report catalogue (all pages, ids, titles): `GET api-prd.../authorize/getdynamicjson?tabnames=REPORTS|DASHBOARD` (public).

## Dataset catalogue (all tested OK, one call each)

| # | Dataset (page) | Client fn | Filter dict (defaults) | Grain / coverage | Key fields | Units |
|---|---|---|---|---|---|---|
| 1 | **State-wise APY** (`statewiseapy`) | `apy_statewise` | `{"fromyear":2024,"toyear":2025,"crop":["Wheat"],"metric":["Area","Production","Yield"],"uom":"Lakh"}` | State × season (Kharif/Rabi/Summer/Total) × crop × crop-year. **1997-98 → 2025-26** (latest = 3rd Advance Est.; older = Final). Includes All-India rows. 37 crops plus aggregates | RecordType (State-Actual / State-Season Total / All India-…), State, State Code, Crop Year, Estimation Cycle, Season, Crop, Crop Code, Crop Category, Metric, Value, Unit Of Measure, Latest Estimate | Lakh Ha, Lakh Tonnes, Kg/Ha (cotton lakh bales of 170 kg, jute/mesta bales of 180 kg) |
| 2 | **District APY, complete DA&FW dataset** (`desdistrictwisecompletedatasetreport`) | `apy_district` | `{"checkbox":false,"cropcategory":["Food Grains"],"crop":["Wheat"],"fromyear":"2024","toyear":"2024","uom":"Lakh","metric":[...],"pmddky":false}` | District × season × crop × year, **1998-99 → 2024-25** (2025-26 not yet). About 520 districts | State, District, Crop Year, Estimation Cycle, Season, Crop, Crop Category, Metric, Value, Unit Of Measure | same |
| 3 | All-India APY time series (`allindiaapy`) | `apy_all_india` | `{"metric":[...],"uom":"Lakh","year":"2025-26"}` | All-India × season × crop, **1966-67 → 2025-26**, 37 crops/aggregates. 4.5 MB | State, Crop Year, Estimation Cycle, Season, Crop, Metric, Value | same |
| 4 | Progressive crop area sown, CWWG weekly (`progressivecropareasown`) | `progressive_area_sown` | `{"radio":"Cropwise","crop":9999,"state":"All India","years":2,"date":"2026-10-23","uom":"Lakh"}` | Weekly snapshot, crop (or state) × current vs last years vs normal | Cropname, Statename, Year, Metric (Normal/Target/Area Sown/Diff/%), Value | Lakh Ha |
| 5 | **Mandi arrivals or prices by state, date window** (`imcmarketlevel`) | `mandi_state_arrivals_or_prices` | `{"from_date":"2026-10-15","to_date":"2026-10-22","crop_category":"Oilseeds","crop":"Rapeseed & Mustard","source":"Agmarknet","top_filter":3,"metric":"arrivals","years":3,"uom":"Tonnes"}` (`metric:"prices"`, `uom:"Rs/Qtl"` for prices) | State × same window in current + 2 prior years. Source Agmarknet or e-NAM (via API) | crpname, state, year, metricvalue, metricname, uom | Tonnes / Rs/Qtl |
| 6 | e-NAM vs Agmarknet mandi comparison (`enamagmarknetcomparison`) | `enam_vs_agmarknet` | `{"fromdate":"2026-09-22","todate":"2026-10-22","crop_category":"Oilseeds","crop":"Rapeseed & Mustard","source":["Agmarknet"],"filter":"top_3_mandis"}` | All-India / state / mandi aggregate over window | StateName, Market, source, variable (MandiArrivalQuantity / MandiWholeSalePrice), value | MT, Rs/Qtl |
| 7 | MSP statement, CACP (`mipmspstatement`) | `msp` | `{"from_year":"2025-26","to_year":"2026-27"}` | All-India × crop × marketing year (about 22 MSP crops + copra) | Crop, Season, Year, Value, UOM, Metric, Crop Category | Rs/Qtl |
| 8 | WPI monthly, agri items (`wpireport`) | `wpi_monthly` | `{"to_year":"2026","from_year":"2024"}` | All-India × 41 commodities × month, **Apr-2012 → Sep-2026** | Crop, YearCode, MonthCode (YYYYMM), Month, WPI | index (2011-12 = 100) |
| 9 | FCI procurement (`procurementfci`) | `fci_procurement` | `{"year":"2025-26","marketing_season":"KMS","season":"Kharif","crop_name":"Rice","uom":"LMT"}` (wheat: RMS/Rabi) | State × marketing year (selected + 2 prior + % change rows) | statename, cropname, seasonname, years, valuess, metrics, qtyuom | LMT |
| 10 | NAFED stocks (`nafedstocksreport`) | `nafed_stocks` | `{"radio":"Statewise","statename":99,"crop_name":"","year":"2026-27","uom":"LMT","crop":1}` (no `url` state) | State × scheme (PSS/PSF/All) for one crop | CropNamed, state_named, yeard, seasond, schemed, availableqtyd | LMT |
| 11 | Commodity trade, DGCIS (`mipcommoditytradedata`) | `trade` | `{"trade":"Export","price_qty":["Quantity","Value"],"year1":2025,"year":2026,"crop_category":["Commercial crops"],"uom":"Thousand","crop_subcategory":["Commercial crops"]}` | All-India × commodity × fiscal year (Export/Import) | commodity, fiscalyear, metric (Quantity / Value INR / Value USD), value | ThMT, thousand INR/USD |
| 12 | Domestic crop calendar (REST, public) | `crop_calendar` | `GET cropcalender/domesticcropcalender` (`internationalcropcalender` also public) | State × crop (980 rows) × month | stateID, state, cropID, crops, season, primary/secondary/tertiaryCategory, jan..dec = list of hex colour codes | colour legend (sowing/harvest) is in the UI, not the JSON. Decode before use |
| 13 | Latest production by state, major crops (REST) | `latest_production_by_state` | `GET homepage/loadindiamap` | latest AE only | cropName, stateName, geoID, seasonName, metricValue, percentageVariation | Lakh Tonnes |
| 14 | Latest all-India crop estimates (REST) | `latest_all_india_estimates` | `GET homepage/displaycropsinformation` | latest AE | cropName, finalEstimate, agricultureYear, UOM | Lakh Tonnes |

Also public: `homepage/getestimationsummary` (category totals), `homepage/loadindiamapcrops`, `dropdown/states` (state keys), `load/reports/latest-release-dropdown`.

### Other Dash reports not wrapped (same mechanism, filter dict to capture)
APY: `allindiaapysw`, `allindiaapyyearwise`, `statewiseapy2`, `fiveyearapy`, `normalestimates`, `stateprofile`, `domesticinternationalproduction`, `apymajorstates`, `apycombined`.
Prices and markets: `pricesmonthcomparison`, `papcombined` (production-arrivals-prices graph, figure plus download callback), `ncdex`, `mipinternationlactualpricevariation`, `mipinternationlavgpricevariation`, `cpi-only`, `wpi`, IMC tabs (`imc/imc-*-tab`).
Procurement: `nafedstatewiseprocurementreport` (`statewise_procurement_report-*`), `nccfstocksandprocurement`.
Trade: `customduties`, `mipcountrywisetradeinsights`, `mipricericetradedata`, `miptradeandapytrends`, `miptradequantitytrends`.
Other: `gvaagri`, `cropprofiledash`, `cwwgdashboard`.

## Not fetchable without login
- **Supply-demand balance sheets** (`balancesheet`, `getbalancesheetdropdowns`): JWT (401).
- State-specific price/arrival API (`get/statespecific/*`), `apidata/*`, `dropdown/years`, `common/getlocations`, MIR / press-release PDFs (`load/reports/get-MIR-*`): JWT.
- The whole `data.upag.gov.in` Open API: OAuth2 password grant, needs DA&FW-issued credentials.
- Dash pages that are only figures (graphs) return Plotly figure JSON rather than rows. They are usable but messier.

## Caveats
- Dash callback signatures (output strings, filter keys) are an **internal UI contract** and can change on any redeploy (build date in the bundle: 2026-10-23). Pin `_dash-dependencies` and smoke-test in CI.
- Filter dicts include defaults the server can silently fill (for example `pmddky` was added to the district dict by the server). Unknown keys are ignored. Missing keys may 500.
- Values are wide-to-long: one row per (entity, year, metric). Units differ by metric. Cotton and jute production come in bales.
- Name joins: UPAG uses DA&FW state names (for example "Andaman And Nicobar Islands"), and crop names such as "Rapeseed & Mustard", "Tur", "Moong", "Urad", "Gram". Agmarknet commodity names differ (for example "Arhar (Tur/Red Gram)(Whole)", "Bengal Gram(Gram)(Whole)", "Mustard"). A crosswalk table is required. Agmarknet districts also need a LGD-style mapping.
- APY is by **crop year (July–June)** and season. Agmarknet is daily. Aggregate arrivals to crop year (or season months) before computing shares. Production is Lakh Tonnes and Agmarknet arrivals are tonnes (×1e5).
- The district dataset is large: Food Grains × All crops × 1 year is about 32 MB. Request per crop.
- APY 2025-26 is 3rd Advance Estimates. `Estimation Cycle` and `Latest Estimate` flag revisions, so store the vintage.
