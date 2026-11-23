import json
import re
import runpy
import sys

import pytest

from indiagri import upag


class FakeResp:
    def __init__(self, b):
        self.b = b

    def read(self):
        return self.b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def cap(monkeypatch):
    """Capture dash_callback calls and return canned rows."""
    calls = []

    def fake(output, store, filters, with_url_state=True):
        calls.append({"output": output, "store": store, "filters": filters, "url_state": with_url_state})
        rid = re.match(r"\.\.([^.]+)\.data", output).group(1)
        return b"RAW", {rid: {"data": [{"row": rid}]}}

    monkeypatch.setattr(upag, "dash_callback", fake)
    return calls


def test_dash_callback_body_for_multi_output(monkeypatch):
    seen = {}

    def post(url, body, timeout=180):
        seen.update(url=url, body=body)
        return json.dumps({"response": {"a": 1}}).encode()

    monkeypatch.setattr(upag, "_post", post)
    out = "..aa-store.data...aa-title.children...aa-note.children.."
    raw, resp = upag.dash_callback(out, "aa-filters", {"f": 1})
    assert resp == {"a": 1} and json.loads(raw) == {"response": {"a": 1}}
    b = seen["body"]
    assert seen["url"] == upag.DASH
    assert b["output"] == out
    assert b["outputs"] == [{"id": "aa-store", "property": "data"}, {"id": "aa-title", "property": "children"},
                            {"id": "aa-note", "property": "children"}]
    assert b["inputs"] == [{"id": "aa-filters", "property": "data", "value": {"f": 1}}]
    assert b["changedPropIds"] == ["aa-filters.data"]
    assert b["state"] == [{"id": "url", "property": "search", "value": upag.URL_SEARCH}]


def test_dash_callback_single_output_is_a_dict_and_state_optional(monkeypatch):
    seen = {}
    monkeypatch.setattr(upag, "_post", lambda u, b, timeout=180: seen.setdefault("b", b) and b"{\"response\": {}}")
    upag.dash_callback("..s.data..", "fs", {}, with_url_state=False)
    b = seen["b"]
    assert b["outputs"] == {"id": "s", "property": "data"}
    assert "state" not in b


def test_post_and_get_build_requests(monkeypatch):
    reqs = []

    def urlopen(req, timeout=None):
        reqs.append((req, timeout))
        return FakeResp(b"ok")

    monkeypatch.setattr(upag.urllib.request, "urlopen", urlopen)
    assert upag._post("http://x/", {"a": 1}) == b"ok"
    r, t = reqs[0]
    assert t == 180 and json.loads(r.data) == {"a": 1}
    assert r.get_header("Content-type") == "application/json" and r.get_header("User-agent") == "Mozilla/5.0"
    assert upag._get("p/q") == b"ok"
    r, t = reqs[1]
    assert r.full_url == upag.API + "p/q" and t == 60 and r.data is None


def test_rows_picks_store_data():
    assert upag._rows({"s": {"data": [1]}}, "s") == [1]


def test_apy_statewise_filters_and_defaults(cap):
    raw, rows = upag.apy_statewise()
    assert raw == b"RAW" and rows == [{"row": "swapy-store"}]
    c = cap[0]
    assert c["store"] == "swapy-filters-store"
    assert c["filters"] == {"fromyear": 2024, "toyear": 2025, "crop": ["Wheat"], "metric": ["Area", "Production", "Yield"], "uom": "Lakh"}
    upag.apy_statewise(crops=("All",), from_year=1997, to_year=2001, uom="Thousand", metrics=("Area",))
    assert cap[1]["filters"] == {"fromyear": 1997, "toyear": 2001, "crop": ["All"], "metric": ["Area"], "uom": "Thousand"}


def test_apy_district_year_is_a_string_and_flags(cap):
    upag.apy_district(2019, ["Oilseeds"], ["Groundnut"])
    f = cap[0]["filters"]
    assert f["fromyear"] == "2019" and f["toyear"] == "2019"
    assert f["cropcategory"] == ["Oilseeds"] and f["crop"] == ["Groundnut"]
    assert f["checkbox"] is False and f["pmddky"] is False and f["uom"] == "Lakh"
    assert cap[0]["store"] == "ddcd-report-filters-store"


def test_apy_all_india_and_progressive_area(cap):
    assert upag.apy_all_india()[1] == [{"row": "aiapy-idstore"}]
    assert cap[0]["filters"] == {"metric": ["Area", "Production", "Yield"], "uom": "Lakh", "year": "2025-26"}
    upag.progressive_area_sown()
    assert cap[1]["filters"] == {"radio": "Cropwise", "crop": 9999, "state": "All India", "years": 2,
                                 "date": "2026-10-23", "uom": "Lakh"}


def test_market_reports_filters(cap):
    upag.mandi_state_arrivals_or_prices("2026-10-15", "2026-10-22")
    assert cap[0]["filters"] == {"from_date": "2026-10-15", "to_date": "2026-10-22", "crop_category": "Oilseeds",
                                 "crop": "Rapeseed & Mustard", "source": "Agmarknet", "top_filter": 3,
                                 "metric": "arrivals", "years": 3, "uom": "Tonnes"}
    upag.enam_vs_agmarknet("a", "b", sources=("Agmarknet", "e-NAM"))
    assert cap[1]["filters"]["source"] == ["Agmarknet", "e-NAM"]
    assert cap[1]["filters"]["filter"] == "top_3_mandis" and cap[1]["filters"]["fromdate"] == "a"


def test_msp_and_wpi_filters(cap):
    upag.msp()
    assert cap[0]["filters"] == {"from_year": "2025-26", "to_year": "2026-27"}
    upag.wpi_monthly("2012", "2026")
    assert cap[1]["filters"] == {"to_year": "2026", "from_year": "2012"}
    assert cap[1]["store"] == "wpi-report-filters-store"


def test_fci_nafed_trade_filters(cap):
    upag.fci_procurement()
    assert cap[0]["filters"] == {"year": "2025-26", "marketing_season": "KMS", "season": "Kharif", "crop_name": "Rice", "uom": "LMT"}
    upag.nafed_stocks()
    assert cap[1]["filters"] == {"radio": "Statewise", "statename": 99, "crop_name": "", "year": "2026-27", "uom": "LMT", "crop": 1}
    assert cap[1]["url_state"] is False                      # NAFED callback registers no url state
    upag.trade("Import", 2015, 2026, ["Pulses"])
    assert cap[2]["filters"] == {"trade": "Import", "price_qty": ["Quantity", "Value"], "year1": 2015, "year": 2026,
                                 "crop_category": ["Pulses"], "uom": "Thousand", "crop_subcategory": ["Pulses"]}


def test_portal_rest_endpoints(monkeypatch):
    paths = []
    payloads = {
        "cropcalender/domesticcropcalender": {"records": {"records": [1]}},
        "cropcalender/internationalcropcalender": {"records": {"records": [2]}},
        "homepage/loadindiamap": {"records": [3]},
        "homepage/displaycropsinformation": {"records": [4]},
        "authorize/getdynamicjson?tabnames=REPORTS": {"records": [5]},
        "authorize/getdynamicjson?tabnames=DASHBOARD": {"records": [6]},
    }

    def get(path, timeout=60):
        paths.append(path)
        return json.dumps(payloads[path]).encode()

    monkeypatch.setattr(upag, "_get", get)
    assert upag.crop_calendar()[1] == [1]
    assert upag.crop_calendar(international=True)[1] == [2]
    assert upag.latest_production_by_state()[1] == [3]
    assert upag.latest_all_india_estimates()[1] == [4]
    assert upag.report_catalogue()[1] == [5]
    assert upag.report_catalogue("DASHBOARD")[1] == [6]
    assert len(paths) == 6


def test_main_self_test_runs_every_report_and_writes_samples(monkeypatch, tmp_path, capsys):
    src = open(upag.__file__, encoding="utf-8").read()
    stores = set(re.findall(r'_rows\(resp, "([^"]+)"\)', src))
    body = json.dumps({"response": {s: {"data": [{"a": 1}]} for s in stores},
                       "records": {"records": [{"a": 1}]}}).encode()
    monkeypatch.setattr(upag.urllib.request, "urlopen", lambda req, timeout=None: FakeResp(body))
    monkeypatch.setattr(upag.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["upag.py", str(tmp_path / "samples")])
    runpy.run_path(upag.__file__, run_name="__main__")
    out = capsys.readouterr().out.splitlines()
    assert sum(1 for l in out if l.startswith("OK ")) == 15
    assert not [l for l in out if l.startswith("FAIL")]
    assert len(list((tmp_path / "samples").glob("*.json"))) == 15


def test_main_self_test_reports_failures_and_keeps_going(monkeypatch, tmp_path, capsys):
    def boom(req, timeout=None):
        raise OSError("down")

    monkeypatch.setattr(upag.urllib.request, "urlopen", boom)
    monkeypatch.setattr(upag.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["upag.py", str(tmp_path / "s")])
    runpy.run_path(upag.__file__, run_name="__main__")
    out = capsys.readouterr().out.splitlines()
    assert len([l for l in out if l.startswith("FAIL")]) == 15
    assert "OSError: down" in out[0]
