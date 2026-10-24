"""Minimal stdlib-only client for the PUBLIC (no login, no captcha) endpoints of
Agmarknet 2.0 (https://agmarknet.gov.in, backend https://api.agmarknet.gov.in/v1/).

Rules baked in:
  * at most one request every MIN_INTERVAL seconds (default 1.5 s), process-wide;
  * HTTP 429 -> exponential backoff (honours Retry-After), then retry;
  * dashboard-data paging via "page" in the JSON body (limit <= 500).
Endpoints that return 403 "Authorization header missing" or 400
"TOKEN_OR_CAPTCHA_REQUIRED" are deliberately NOT wrapped.

Run `python3 -I agmarknet_client.py [samples_dir]` for a one-call-per-endpoint smoke test.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.agmarknet.gov.in/v1/"
UA = "Mozilla/5.0"
MIN_INTERVAL = 1.5
MAX_RETRIES = 6
TIMEOUT = 180

_lock = threading.Lock()
_last = [0.0]


class AgmError(RuntimeError):
    def __init__(self, status, body, url):
        super().__init__(f"HTTP {status} for {url}: {body[:200]!r}")
        self.status, self.body, self.url = status, body, url


def _throttle():
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def request(method, path, params=None, body=None, raw=False):
    """Low-level call. Returns parsed JSON, or (bytes, content_type) if raw=True."""
    url = BASE + path.lstrip("/")
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, safe="(),[]")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    delay = 15.0
    for attempt in range(MAX_RETRIES):
        _throttle()
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                payload, ctype = r.read(), r.headers.get("Content-Type", "")
            break
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            if e.code in (429, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                ra = e.headers.get("Retry-After")
                time.sleep(float(ra) if ra and ra.isdigit() else delay)
                delay = min(delay * 2, 300)
                continue
            raise AgmError(e.code, txt, url) from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(delay)
                delay = min(delay * 2, 300)
                continue
            raise AgmError(-1, str(e), url) from None
    if raw:
        return payload, ctype
    return json.loads(payload)


def _get(path, **params):
    return request("GET", path, params={k: v for k, v in params.items() if v is not None})


# --------------------------------------------------------------------------- masters
def live_date():
    """Date the portal went live: {'live_date': 'DD-MM-YYYY'}."""
    return _get("agmarknet-live-date")["data"]


def report_filters():
    """One-shot master bundle (daily-price-arrival/filters): commodities (605) with
    group ids, 16 groups, 18 grades, 2154 varieties, 37 states, 751 districts,
    4176 markets (id/state/district), report types and allowed date ranges."""
    return _get("daily-price-arrival/filters")["data"]


def dashboard_filters(dashboard_name):
    """Per-dashboard filter master. Valid names: cumm_faq, cumm_arrival, cumm_price,
    cumm_data, market_details, statewise_price_arrival, marketwise_price_arrival,
    season_price_arrival, commodity_msp, prevailing_market_below_msp."""
    return _get("dashboard-filters/", dashboard_name=dashboard_name)["data"]


def gis_filters():
    """GIS-atlas filters: 27 MSP commodities, markets with market_category_id,
    msp_type (above/below), report types, market categories."""
    return _get("gis-mapping/filters")["data"]


def commodities():
    """Full commodity master (605) incl. varieties, grades, units, MSP flag, codes.
    Caveat: the server ignores page_size and returns all 605 on every page while still
    advertising next_page, so de-duplicate by id and stop when a page adds nothing."""
    seen, page = {}, 1
    while True:
        r = _get("commodities", page=page, page_size=500)
        before = len(seen)
        for c in r["data"]:
            seen.setdefault(c["id"], c)
        if not r["pagination"].get("next_page") or len(seen) == before:
            return list(seen.values())
        page += 1


def commodity_groups():
    return _get("Commoditygroup", page_size=500)["data"]


def grades():
    return _get("commodity/grade")["data"]


def units():
    return _get("commodity/unit")["data"]


def varieties():
    return _get("commodity/variety")["data"]


def states_with_districts():
    """36 states/UTs with nested districts (LGD codes) and multilingual names."""
    return _get("location/state", page_size=100)["states"]


def markets():
    """4175 markets: market_id, market_name, district_id/name, state_id/name."""
    return _get("market-district-state")


def market_directory():
    """4906 markets with address, category (PMY/SMY/FCM/PVT/RMY/Other),
    area served, api_allowed_market flag, status."""
    return _get("dashboard-market-filter")["data"]


def market_categories():
    return _get("market-category-filter")


def dashboard_commodities():
    """Commodity list used by the home dashboard (incl. pseudo ids 9999 MSP, etc.)."""
    return _get("dashboard-commodities-filter")["data"]


def seasons():
    return _get("dashboard-season-filter")["data"]


def msp_commodity_groups():
    return _get("guest-msp-commodity")


# --------------------------------------------------------------------------- dashboard-data
def dashboard_data(dashboard, paginate=True, limit=500, **fields):
    """POST dashboard-data/. `fields` go into the JSON body verbatim
    (commodity=[ids], state=[ids] or scalar, date='YYYY-MM-DD', from_date, to_date,
    type, year, group, district, market, market_type, grades, variety, season,
    status, min_qty, max_qty). Returns {'records': [...], 'meta': first_page_data}."""
    body = {"dashboard": dashboard, "limit": limit, "format": "json", **fields}
    page, recs, meta = 1, [], None
    while True:
        body["page"] = page
        r = request("POST", "dashboard-data/", body=body)
        data = r.get("data") or {}
        if meta is None:
            meta = {k: v for k, v in data.items() if k != "records"} if isinstance(data, dict) else {}
        recs += (data.get("records") if isinstance(data, dict) else data) or []
        if not paginate or not (r.get("pagination") or {}).get("next_page"):
            return {"records": recs, "meta": meta, "pagination": r.get("pagination")}
        page += 1


def dashboard_download(dashboard, fmt="csv", **fields):
    """Server-side export of a dashboard (downloadreport=true). Returns (bytes, ctype)."""
    body = {"dashboard": dashboard, "downloadreport": "true", "downloadformat": fmt,
            "format": "json", **fields}
    return request("POST", "dashboard-data/", body=body, raw=True)


def statewise_price_arrival(commodity_ids, from_date, to_date, kind="price"):
    """State x month weighted price (type 100016) or arrivals (100017)."""
    t = {"price": 100016, "arrival": 100017}[kind]
    return dashboard_data("statewise_price_arrival_sp", commodity=list(commodity_ids),
                          type=t, from_date=from_date, to_date=to_date)


def market_details(commodity_ids, date):
    """Market x commodity daily price + arrival for one date (reported and non-reported)."""
    return dashboard_data("market_details_sp", commodity=list(commodity_ids), date=date)


def marketwise_price_arrival(commodity_ids, from_date, to_date):
    return dashboard_data("marketwise_price_arrival", commodity=list(commodity_ids),
                          from_date=from_date, to_date=to_date)


def cumm_arrival(commodity_ids, state_ids, from_date, to_date):
    return dashboard_data("cumm_arrival_sp", commodity=list(commodity_ids),
                          state=list(state_ids), from_date=from_date, to_date=to_date)


# --------------------------------------------------------------------------- price-trend
PRICE_TREND = {
    "prices_monthly": "price-trend/wholesale-prices-monthly",
    "prices_weekly": "price-trend/wholesale-prices-weekly",
    "arrivals_monthly": "price-trend/wholesale-arrivals-monthly",
    "arrivals_weekly": "price-trend/wholesale-arrivals-weekly",
    "variety_prices_monthly": "price-trend/varietywise-prices-monthly",
    "variety_prices_weekly": "price-trend/varietywise-prices-weekly",
}


def price_trend(kind, commodity, year, month, report_mode="Statewise", state=0,
                district=0, week=None, fmt=None):
    """Monthly/weekly analysis tables (current vs previous period vs same period last year).

    report_mode: Statewise | Districtwise (state req.) | Marketwise (state+district)
                 | MarketwiseAll (state; all districts).
    Arrivals kinds accept only Marketwise / MarketwiseAll.
    week: 1-4 (weekly kinds; week 4 = day 22..month end).
    fmt: None -> JSON {'title','data'(column groups),'rows'}; 'csv'|'excel'|'pdf' ->
         (bytes, ctype) server export, no auth needed.
    """
    p = {"report_mode": report_mode, "commodity": commodity, "year": year, "month": month,
         "state": state, "district": district}
    if week is not None:
        p["week"] = week
    if fmt:
        p.update(export="true", downloadformat=fmt)
        return request("GET", PRICE_TREND[kind], params=p, raw=True)
    p["export"] = "false"
    return request("GET", PRICE_TREND[kind], params=p)


def price_trend_years(commodity):
    return _get("price-trend/year-filter", commodity=commodity)["data"]


def price_trend_states(commodity):
    return _get("price-trend/state-filter", commodity=commodity)["data"]


def price_trend_districts(commodity, state):
    return _get("price-trend/district-filter", commodity=commodity, state=state)["data"]


def price_trend_months(commodity, year):
    return _get("price-trend/month-filter", commodity=commodity, year=year)["data"]


def price_trend_weeks(commodity, year, month):
    return _get("price-trend/week-filter", commodity=commodity, year=year, month=month)["data"]


# --------------------------------------------------------------------------- last-week
def lastweek_market_prices(market_id, state_id, commodity_id, excel=False):
    """Daily modal price, last 7 days, one market x one commodity, by variety ('NR' = not reported)."""
    p = {"marketId": market_id, "stateId": state_id, "commodityId": commodity_id,
         "includeExcel": "true" if excel else "false"}
    return request("GET", "prices-and-arrivals/market-price/lastweek", params=p, raw=excel)


def lastweek_commodity_prices(market_id, state_id, commodity_id, excel=False):
    p = {"marketId": market_id, "stateId": state_id, "commodityId": commodity_id,
         "includeExcel": "true" if excel else "false"}
    return request("GET", "prices-and-arrivals/commodity-price/lastweek", params=p, raw=excel)


# --------------------------------------------------------------------------- market profile
PROFILE_SECTIONS = {  # (category_id, subcategory_id): name  -- from the site JS
    (1, 1): "General Information (lat/long, address, contacts, est. year)",
    (1, 2): "Administrative Information",
    (1, 3): "Rail/Road Connectivity",
    (1, 4): "Market Area (sub-yards, notified area, cold storages, processing units)",
    (2, 5): "Market Functionaries",
    (2, 6): "Transactional Methods",
    (2, 7): "Transportation",
    (3, 0): "Important Commodities",
    (4, 0): "Licensed Functionaries",
    (5, 8): "Facilities & Services",
    (5, 9): "Market Charges",
    (5, 10): "Financials",
}


def market_profile(market_id, category_id, subcategory_id):
    r = _get("market-profile-categorywise", category_id=category_id,
             subcategory_id=subcategory_id, market_id=market_id)
    return (r.get("records") or {}).get("data")


def market_holidays(market_id):
    return _get("market-profile-holiday", id=market_id)


def market_profile_enums():
    return {c: _get("market-profile-dropdown", category_id=c, subcategory_id="")["data"]
            for c in (1, 2)}


# --------------------------------------------------------------------------- smoke test
def _save(d, name, obj):
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    if isinstance(obj, tuple):
        b, ct = obj
        ext = ".csv" if "csv" in ct else ".xlsx" if "sheet" in ct else ".pdf" if "pdf" in ct else ".bin"
        open(os.path.join(d, name + ext), "wb").write(b)
    else:
        with open(os.path.join(d, name + ".json"), "w") as fh:
            json.dump(obj, fh, ensure_ascii=False)


def _n(obj):
    if isinstance(obj, tuple):
        return f"{len(obj[0])} bytes {obj[1][:40]}"
    if isinstance(obj, dict):
        for k in ("records", "rows", "data"):
            if isinstance(obj.get(k), list):
                return f"{len(obj[k])} {k}"
        return f"dict keys={list(obj)[:8]}"
    if isinstance(obj, list):
        return f"{len(obj)} items"
    return repr(obj)[:60]


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else None
    tests = [
        ("live_date", lambda: live_date()),
        ("report_filters", report_filters),
        ("dashboard_filters_market_details", lambda: dashboard_filters("market_details")),
        ("gis_filters", gis_filters),
        ("commodities", commodities),
        ("commodity_groups", commodity_groups),
        ("grades", grades),
        ("units", units),
        ("varieties", varieties),
        ("states_with_districts", states_with_districts),
        ("markets", markets),
        ("market_directory", market_directory),
        ("market_categories", market_categories),
        ("seasons", seasons),
        ("msp_commodity_groups", msp_commodity_groups),
        ("statewise_price_arrival", lambda: statewise_price_arrival([1], "2025-04-01", "2025-06-30")),
        ("market_details", lambda: dashboard_data("market_details_sp", paginate=False, limit=20,
                                                   commodity=[1], date="2026-10-22")),
        ("marketwise_price_arrival", lambda: marketwise_price_arrival([1], "2026-10-01", "2026-10-22")),
        ("cumm_arrival", lambda: cumm_arrival([1], [19], "2025-04-01", "2025-04-30")),
        ("dashboard_download_csv", lambda: dashboard_download("statewise_price_arrival_sp", "csv",
                                                              commodity=[1], type=100016,
                                                              from_date="2025-04-01", to_date="2025-06-30")),
        ("pt_prices_monthly_statewise", lambda: price_trend("prices_monthly", 1, 2025, 4)),
        ("pt_prices_weekly_statewise", lambda: price_trend("prices_weekly", 1, 2025, 4, week=2)),
        ("pt_arrivals_monthly_mktall_MP", lambda: price_trend("arrivals_monthly", 1, 2025, 4,
                                                               report_mode="MarketwiseAll", state=19)),
        ("pt_arrivals_weekly_mktall_MP", lambda: price_trend("arrivals_weekly", 1, 2025, 4, week=2,
                                                              report_mode="MarketwiseAll", state=19)),
        ("pt_variety_monthly_district_MP", lambda: price_trend("variety_prices_monthly", 1, 2025, 4,
                                                                report_mode="Districtwise", state=19)),
        ("pt_variety_weekly_statewise", lambda: price_trend("variety_prices_weekly", 1, 2025, 4, week=2)),
        ("pt_prices_monthly_mktall_MP_csv", lambda: price_trend("prices_monthly", 1, 2025, 4,
                                                                 report_mode="MarketwiseAll", state=19, fmt="csv")),
        ("pt_years", lambda: price_trend_years(1)),
        ("pt_states", lambda: price_trend_states(1)),
        ("pt_districts", lambda: price_trend_districts(1, 19)),
        ("pt_months", lambda: price_trend_months(1, 2025)),
        ("pt_weeks", lambda: price_trend_weeks(1, 2025, 4)),
        ("lastweek_market_indore_wheat", lambda: lastweek_market_prices(3046, 19, 1)),
        ("lastweek_commodity_lasalgaon_onion", lambda: lastweek_commodity_prices(2139, 20, 23)),
        ("market_profile_general_indore", lambda: market_profile(3046, 1, 1)),
        ("market_profile_charges_indore", lambda: market_profile(3046, 5, 9)),
        ("market_holidays_indore", lambda: market_holidays(3046)),
    ]
    ok = fail = 0
    for name, fn in tests:
        t0 = time.time()
        try:
            res = fn()
            _save(out, name, res)
            print(f"OK   {name:38s} {_n(res)}  ({time.time() - t0:.1f}s)", flush=True)
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {name:38s} {e}", flush=True)
            fail += 1
    print(f"\n{ok} ok, {fail} failed")
