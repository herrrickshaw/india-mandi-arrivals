
```markdown
# DATA_SOURCES

Every dataset here is a point-in-time, unofficial extract from Government of India portals, re-published under the
Government Open Data License - India (GODL-India; Gazette notification No. 42 of 10 Feb 2017,
https://data.gov.in/sites/default/files/Gazette_Notification_OGDL.pdf). Obligations: name the source, do not misrepresent
the data, do not imply endorsement. Verify any figure against the source portal before relying on it.
Retrieval dates: collectors run 2026-10-24/25 (see git history).

## 1. Agmarknet - Directorate of Marketing & Inspection, Ministry of Agriculture & Farmers Welfare
- URL: https://agmarknet.gov.in/ (Agmarknet 2.0, live since 11-07-2025)
- Licence: GODL-India (presumed; the portal shows no licence text - confirm with DMI)
- Files: data/agmarknet/state_monthly.csv.gz, market_daily_sample.csv.gz, masters/*.csv.gz
- Fields: month, commodity_id, commodity, group, state, arrivals_t (tonnes), price_rs_qtl (weighted average Rs/quintal);
  market sample: date, commodity, state, district, market, mkt_id, arrival_t, modal_price_rs_qtl; masters: id/name lists and
  the market directory (name, category, institutional address, status).
- Coverage: state_monthly Jan 2019-Nov 2026, November partial to 20 Nov (459 commodities, 32 states, 206,267 rows of which 158,969 non-empty; run crop_ranking.py with --end 2026-10 to exclude the partial month);
  market sample 2025-11-01..2026-10-21 every 6th day (60 dates), 23 field crops, 3,108 markets.
- Refresh: manual; `collectors/agmarknet_collect.py state-monthly`, ~1 h at one request per 1.5 s.
- Caveats: arrivals are what markets report; irregular reporters understated; coverage widened from Nov 2025 so arrivals
  are not comparable across that date; non-weight commodities (coconut, flowers, leaf bunches) carry mis-scaled values;
  23% of state-month rows are empty; placeholder prices (Rs 0.01) exist in the market sample; state names follow the source.
- Collection method: public JSON endpoints used by the portal front end (statewise_price_arrival_sp, market_details_sp,
  master lists), no login; CAPTCHA-gated and authenticated endpoints are not used (docs/agmarknet_api.md).
- Personal data: officials' names/phones dropped by the collector; addresses are institutional; 30 contain institutional
  emails (to be removed).

## 2. UPAG - Dept of Agriculture & Farmers Welfare
- URL: https://upag.gov.in/ ; Licence: GODL-India (presumed). Underlying series belong to DES, CACP, DPIIT/OEA, FCI, DGCI&S.
- Files/fields: apy_state (state x season x crop x year: area Lakh Ha, production Lakh Tonnes, yield Kg/Ha), apy_district,
  apy_all_india, msp (Rs/Qtl, 2013-14..2026-27), wpi_monthly (41 items, 2012-04..2026-09), fci_procurement (rice, wheat,
  2016-17..2025-26), trade (DGCIS, 2015-16..2025-26), crop_calendar, latest_* snapshots.
- Caveats: latest crop year is Third Advance Estimates; cotton in 170 kg bales; trade percent-change rows lack a fiscal year
  and contain values below -100% (unusable); 4 duplicate rows.
- Collection method: UPAG reports are Plotly Dash apps; the collector calls their data callbacks (internal UI contract, may
  change). The official Open API (data.upag.gov.in/api/v1) needs DA&FW credentials and is not used.

## 3. Crosswalks and derived tables (author work, MIT)
crosswalks/*.csv, reports/*.csv, INSIGHTS.md computed by analysis/*.py from the files above.

## 4. data/external/urea_state_2025_26.csv
Department of Fertilizers 2025-26 urea sales by state (LMT) as tabulated on masaladeutsch.blogspot.com (Aug 2026).
Replace with the primary DoF/PIB table.

## 5. Boundaries (not committed)
Used by analysis/post_charts.py: DataMeet https://github.com/datameet/maps - credit DataMeet and the underlying survey vintage.

## Attribution line
"Source: Agmarknet (Directorate of Marketing & Inspection) and UPAG (Dept. of Agriculture & Farmers Welfare), Government of
India, under GODL-India; unofficial extract by <author>, retrieved <date>. Not endorsed by the Government of India."
```
