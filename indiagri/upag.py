"""Minimal stdlib client for public UPAG (upag.gov.in) data.

Two public, unauthenticated backends:
  1. Plotly Dash server  https://dash.upag.gov.in/_dash-update-component  (POST JSON)
     - every report page is a Dash page; its "data store" callback returns tidy JSON rows.
     - we call that callback directly with a filter dict (same shape the UI's filters-store holds).
  2. Portal REST API     https://api-prd.upag.gov.in/v1/upagapi/<path>  (GET)
     - only a handful of homepage / crop-calendar endpoints are public; the rest need a JWT.

The official "Open API" (https://data.upag.gov.in/api/v1/...) needs OAuth2 login -> not used here.

Run:  python3 -I upag_client.py  [outdir]   (one call per dataset, saves raw JSON to samples/)
"""
import json
import os
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
DASH = "https://dash.upag.gov.in/_dash-update-component"
API = "https://api-prd.upag.gov.in/v1/upagapi/"
URL_SEARCH = "?t=&stateID=0&rtab=x&rtype=reports"


def _post(url, body, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get(path, timeout=60):
    req = urllib.request.Request(API + path, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def dash_callback(output, filters_store_id, filters, with_url_state=True):
    """Call one Dash callback whose single input is <filters_store_id>.data.

    `output` must be the exact multi-output string registered on the server
    (see https://dash.upag.gov.in/_dash-dependencies). Returns (raw_bytes, response_dict).
    """
    outs = [{"id": o.split(".")[0], "property": o.split(".")[1]}
            for o in output.strip(".").split("...")]
    body = {
        "output": output,
        "outputs": outs if len(outs) > 1 else outs[0],
        "inputs": [{"id": filters_store_id, "property": "data", "value": filters}],
        "changedPropIds": [filters_store_id + ".data"],
    }
    if with_url_state:
        body["state"] = [{"id": "url", "property": "search", "value": URL_SEARCH}]
    raw = _post(DASH, body)
    return raw, json.loads(raw)["response"]


def _rows(resp, store_id):
    return resp[store_id]["data"]


# ---------------------------------------------------------------- APY (DA&FW)
def apy_statewise(crops=("Wheat",), from_year=2024, to_year=2025, uom="Lakh",
                  metrics=("Area", "Production", "Yield")):
    """State x season x crop x year Area/Production/Yield (report: statewiseapy).
    Years are crop-year start (2024 = 2024-25). uom: 'Lakh' (Lakh Ha / Lakh Tonnes) or 'Thousand'.
    crops=['All'] for all crops (large)."""
    out = ("..swapy-store.data...swapy-suffix-title.children...swapy-notification1.children"
           "...swapy-notification2.children...swapy-notification4.children...swapy-sheetname.children..")
    f = {"fromyear": from_year, "toyear": to_year, "crop": list(crops),
         "metric": list(metrics), "uom": uom}
    raw, resp = dash_callback(out, "swapy-filters-store", f)
    return raw, _rows(resp, "swapy-store")


def apy_district(year=2024, crop_category=("Food Grains",), crops=("All",), uom="Lakh",
                 metrics=("Area", "Production", "Yield")):
    """District x season x crop APY (report: desdistrictwisecompletedatasetreport).
    WARNING: Food Grains / All crops / one year is ~32 MB. Pass specific crops to keep it small."""
    out = ("..ddcd-reports-data-store.data...ddcd-report-suffix-title.children"
           "...ddcd-report-notification3.children...ddcd-report-notification1.children"
           "...ddcd-report-notification2.children..")
    f = {"checkbox": False, "cropcategory": list(crop_category), "crop": list(crops),
         "fromyear": str(year), "toyear": str(year), "uom": uom,
         "metric": list(metrics), "pmddky": False}
    raw, resp = dash_callback(out, "ddcd-report-filters-store", f)
    return raw, _rows(resp, "ddcd-reports-data-store")


def apy_all_india(year="2025-26", uom="Lakh", metrics=("Area", "Production", "Yield")):
    """All-India crop x season APY time series (report: allindiaapy). ~4.5 MB."""
    out = ("..aiapy-idstore.data...aiapy-store_initialfilter.data...aiapy-suffix-title.children"
           "...aiapy-notification1.children...aiapy-notification2.children"
           "...aiapy-notification3.children...aiapy-notification4.children..")
    f = {"metric": list(metrics), "uom": uom, "year": year}
    raw, resp = dash_callback(out, "aiapy-filters-store", f)
    return raw, _rows(resp, "aiapy-idstore")


def progressive_area_sown(date="2026-10-23", state="All India", crop=9999, years=2, uom="Lakh"):
    """CWWG weekly progressive area sown vs normal & last years (report: progressivecropareasown).
    crop=9999 means all crops; radio 'Cropwise'."""
    out = ("..pcas-idstore.data...pcas_initialfilter.data...pcas-suffix-title.children"
           "...pcas-notification1.children..")
    f = {"radio": "Cropwise", "crop": crop, "state": state, "years": years, "date": date, "uom": uom}
    raw, resp = dash_callback(out, "pcas-filters-store", f)
    return raw, _rows(resp, "pcas-idstore")


# ---------------------------------------------------------------- Markets / prices
def mandi_state_arrivals_or_prices(from_date, to_date, crop="Rapeseed & Mustard",
                                   crop_category="Oilseeds", source="Agmarknet",
                                   metric="arrivals", years=3, uom="Tonnes"):
    """State-wise mandi arrivals (or prices) for a date window, same window in N prior years
    (report: imcmarketlevel). source: 'Agmarknet' or 'e-NAM'(UI label); metric: 'arrivals'/'prices'."""
    out = ("..imc_market_level-report-idstore.data...imc_market_level-suffix-title.children"
           "...imc_market_level-source.children...imc_market_level-uom.children..")
    f = {"from_date": from_date, "to_date": to_date, "crop_category": crop_category,
         "crop": crop, "source": source, "top_filter": 3, "metric": metric,
         "years": years, "uom": uom}
    raw, resp = dash_callback(out, "imc_market_level-report-filters-store", f)
    return raw, _rows(resp, "imc_market_level-report-idstore")


def enam_vs_agmarknet(from_date, to_date, crop="Rapeseed & Mustard", crop_category="Oilseeds",
                      sources=("Agmarknet",), mandi_filter="top_3_mandis"):
    """State/mandi arrivals (MT) and wholesale prices (Rs/Qtl) over a window
    (report: enamagmarknetcomparison). mandi_filter: top_3_mandis / major / common / all (see UI)."""
    out = ("..enamvsagmarknet-idstore.data...enamvsagmarknet-title.children"
           "...enamvsagmarknet-uom-info.children...enamvsagmarknet-source-info.children..")
    f = {"fromdate": from_date, "todate": to_date, "crop_category": crop_category,
         "crop": crop, "source": list(sources), "filter": mandi_filter}
    raw, resp = dash_callback(out, "enamvsagmarknet-filters-store", f)
    return raw, _rows(resp, "enamvsagmarknet-idstore")


def msp(from_year="2025-26", to_year="2026-27"):
    """CACP MSP by crop and marketing year, Rs/Qtl (report: mipmspstatement)."""
    out = "..mip-msp-data2-store2.data...mip-msp-data2-title2.children.."
    raw, resp = dash_callback(out, "mip-msp-data2-filters-store",
                              {"from_year": from_year, "to_year": to_year})
    return raw, _rows(resp, "mip-msp-data2-store2")


def wpi_monthly(from_year="2024", to_year="2026"):
    """Monthly WPI by agri commodity (report: wpireport). 2012-2026 is ~0.7 MB."""
    out = "..wpi-report-idstore.data...wpi-report-suffix-title.children.."
    raw, resp = dash_callback(out, "wpi-report-filters-store",
                              {"to_year": to_year, "from_year": from_year})
    return raw, _rows(resp, "wpi-report-idstore")


# ---------------------------------------------------------------- Procurement / stocks / trade
def fci_procurement(year="2025-26", marketing_season="KMS", season="Kharif", crop="Rice", uom="LMT"):
    """FCI state-wise procurement, current vs prior 2 years (report: procurementfci).
    Wheat: marketing_season='RMS', season='Rabi'."""
    out = ("..procfci-idstore.data...procfci_initialfilter.data...procfci-suffix-title.children"
           "...profci-unit-info.children..")
    f = {"year": year, "marketing_season": marketing_season, "season": season,
         "crop_name": crop, "uom": uom}
    raw, resp = dash_callback(out, "procfci-filters-store", f)
    return raw, _rows(resp, "procfci-idstore")


def nafed_stocks(year="2026-27", crop_id=1, state_code=99, uom="LMT"):
    """NAFED stock (PSS/PSF) by state for a crop (report: nafedstocksreport). crop_id 1 = Gram;
    state_code 99 = All India."""
    out = ("..nafed_procurement_report-store.data...nafed_procurement_report-grid-suffix-title.children"
           "...nafed_procurement_report-unit-info.children..")
    f = {"radio": "Statewise", "statename": state_code, "crop_name": "", "year": year,
         "uom": uom, "crop": crop_id}
    raw, resp = dash_callback(out, "nafed_procurement_report-filters-store", f, with_url_state=False)
    return raw, _rows(resp, "nafed_procurement_report-store")


def trade(trade_type="Export", year_from=2025, year_to=2026, crop_category=("Commercial crops",),
          uom="Thousand"):
    """DGCIS export/import quantity (ThMT) & value (INR/USD thousand) by commodity and fiscal year,
    all-India (report: mipcommoditytradedata)."""
    out = ("..trade-reports-data1-store1.data...trade-reports-data1-grid1-title.children"
           "...trade-reports-data1-grid1-unitinfo.children..")
    f = {"trade": trade_type, "price_qty": ["Quantity", "Value"], "year1": year_from,
         "year": year_to, "crop_category": list(crop_category), "uom": uom,
         "crop_subcategory": list(crop_category)}
    raw, resp = dash_callback(out, "trade-reports-data1-filters-store", f)
    return raw, _rows(resp, "trade-reports-data1-store1")


# ---------------------------------------------------------------- Portal REST (public subset)
def crop_calendar(international=False):
    """State x crop x month sowing/harvest calendar (colour-coded month cells)."""
    raw = _get("cropcalender/internationalcropcalender" if international
               else "cropcalender/domesticcropcalender")
    return raw, json.loads(raw)["records"]["records"]


def latest_production_by_state():
    """Latest advance-estimate production by state x major crop (homepage India map)."""
    raw = _get("homepage/loadindiamap")
    return raw, json.loads(raw)["records"]


def latest_all_india_estimates():
    """Latest all-India production per crop (homepage tiles)."""
    raw = _get("homepage/displaycropsinformation")
    return raw, json.loads(raw)["records"]


def report_catalogue(tab="REPORTS"):
    """List of all dashboard/report pages (tab: DASHBOARD or REPORTS)."""
    raw = _get("authorize/getdynamicjson?tabnames=" + tab)
    return raw, json.loads(raw)["records"]


# ---------------------------------------------------------------- self-test
if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
    os.makedirs(outdir, exist_ok=True)
    tests = {
        "apy_statewise_wheat_2024_25": lambda: apy_statewise(["Wheat"], 2024, 2025),
        "apy_district_wheat_2024": lambda: apy_district(2024, ["Food Grains"], ["Wheat"]),
        "apy_all_india_2025_26": lambda: apy_all_india("2025-26"),
        "progressive_area_sown": lambda: progressive_area_sown("2026-10-23"),
        "mandi_state_arrivals_mustard": lambda: mandi_state_arrivals_or_prices("2026-10-15", "2026-10-22"),
        "enam_vs_agmarknet_mustard": lambda: enam_vs_agmarknet("2026-09-22", "2026-10-22"),
        "msp_2025_27": lambda: msp(),
        "wpi_2024_2026": lambda: wpi_monthly("2024", "2026"),
        "fci_procurement_rice_2025_26": lambda: fci_procurement("2025-26"),
        "nafed_stocks_gram": lambda: nafed_stocks(),
        "trade_export_commercial": lambda: trade(),
        "crop_calendar_domestic": lambda: crop_calendar(),
        "latest_production_by_state": latest_production_by_state,
        "latest_all_india_estimates": latest_all_india_estimates,
        "report_catalogue_reports": report_catalogue,
    }
    for name, fn in tests.items():
        t = time.time()
        try:
            raw, rows = fn()
            open(os.path.join(outdir, name + ".json"), "wb").write(raw)
            first = rows[0] if isinstance(rows, list) and rows else rows
            print(f"OK   {name:34s} {len(rows):6d} rows {len(raw)/1e3:9.1f} kB {time.time()-t:5.1f}s  "
                  f"keys={list(first)[:8] if isinstance(first, dict) else type(first).__name__}")
        except Exception as e:  # keep going so one broken report doesn't hide the rest
            print(f"FAIL {name:34s} {type(e).__name__}: {e}")
        time.sleep(1)
