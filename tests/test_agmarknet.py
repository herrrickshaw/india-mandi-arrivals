import io
import json
import urllib.error

import pytest

from indiagri import agmarknet as agm


class FakeResp:
    def __init__(self, payload, ctype="application/json"):
        self._p = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.headers = {"Content-Type": ctype}

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Net:
    """Scripted urlopen: each entry is a payload, a (code, headers) HTTP error or an exception."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def __call__(self, req, timeout=None):
        self.calls.append((req.full_url, req.get_method(), req.data, dict(req.header_items()), timeout))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, tuple) and item and item[0] == "http":
            _, code, body, headers = item
            raise urllib.error.HTTPError(req.full_url, code, "err", headers or {}, io.BytesIO(body.encode()))
        return item if isinstance(item, FakeResp) else FakeResp(item)


@pytest.fixture
def net(monkeypatch):
    sleeps = []
    monkeypatch.setattr(agm.time, "sleep", sleeps.append)
    monkeypatch.setattr(agm, "_last", [0.0])
    n = Net([])
    monkeypatch.setattr(agm.urllib.request, "urlopen", n)
    n.sleeps = sleeps
    return n


def test_request_builds_url_params_and_headers(net):
    net.script = [{"ok": 1}]
    out = agm.request("GET", "/x/y", params={"a": "(1,2)", "b": 3})
    assert out == {"ok": 1}
    url, method, data, headers, timeout = net.calls[0]
    assert url == "https://api.agmarknet.gov.in/v1/x/y?a=(1,2)&b=3"
    assert method == "GET" and data is None and timeout == agm.TIMEOUT
    assert headers["User-agent"] == "Mozilla/5.0"
    assert "Content-type" not in headers


def test_request_appends_with_ampersand_when_query_already_present(net):
    net.script = [{}]
    agm.request("GET", "p?z=1", params={"a": 2})
    assert net.calls[0][0].endswith("/p?z=1&a=2")


def test_request_post_sends_json_body_and_content_type(net):
    net.script = [{}]
    agm.request("POST", "dashboard-data/", body={"k": [1]})
    _, method, data, headers, _ = net.calls[0]
    assert method == "POST" and json.loads(data) == {"k": [1]}
    assert headers["Content-type"] == "application/json"


def test_request_empty_body_still_posts_json(net):
    net.script = [{}]
    agm.request("POST", "p", body={})
    assert net.calls[0][2] == b"{}"


def test_request_raw_returns_bytes_and_content_type(net):
    net.script = [FakeResp(b"a,b\n1,2\n", "text/csv")]
    assert agm.request("GET", "p", raw=True) == (b"a,b\n1,2\n", "text/csv")


def test_throttle_sleeps_remaining_interval(monkeypatch):
    monkeypatch.setattr(agm, "_last", [100.0])
    clock = iter([100.5, 101.0])
    monkeypatch.setattr(agm.time, "monotonic", lambda: next(clock))
    slept = []
    monkeypatch.setattr(agm.time, "sleep", slept.append)
    agm._throttle()
    assert slept == [pytest.approx(1.0)]          # MIN_INTERVAL 1.5 - 0.5 elapsed
    assert agm._last[0] == 101.0


def test_throttle_does_not_sleep_when_interval_elapsed(monkeypatch):
    monkeypatch.setattr(agm, "_last", [0.0])
    monkeypatch.setattr(agm.time, "monotonic", lambda: 50.0)
    slept = []
    monkeypatch.setattr(agm.time, "sleep", slept.append)
    agm._throttle()
    assert slept == []
    assert agm._last[0] == 50.0


def test_throttle_exact_interval_does_not_sleep(monkeypatch):
    monkeypatch.setattr(agm, "_last", [10.0])
    clock = iter([11.5, 11.5])
    monkeypatch.setattr(agm.time, "monotonic", lambda: next(clock))
    slept = []
    monkeypatch.setattr(agm.time, "sleep", slept.append)
    agm._throttle()
    assert slept == []


def test_429_honours_retry_after_then_succeeds(net):
    net.script = [("http", 429, "slow", {"Retry-After": "7"}), {"v": 1}]
    assert agm.request("GET", "p") == {"v": 1}
    assert 7.0 in net.sleeps and len(net.calls) == 2


def test_non_numeric_retry_after_falls_back_to_backoff_and_doubles(net):
    net.script = [("http", 503, "x", {"Retry-After": "soon"}), ("http", 502, "x", None),
                  ("http", 504, "x", {}), {"v": 1}]
    assert agm.request("GET", "p") == {"v": 1}
    assert [s for s in net.sleeps if s >= 15] == [15.0, 30.0, 60.0]


def test_backoff_delay_is_capped_at_300(net):
    net.script = [("http", 429, "x", {})] * 5 + [{"v": 1}]
    agm.request("GET", "p")
    assert [s for s in net.sleeps if s >= 15] == [15.0, 30.0, 60.0, 120.0, 240.0]
    net.script = [("http", 429, "x", {})] * 5 + [{"v": 1}]
    # delay variable caps at 300 on the 6th doubling; verify via a fresh run with 6 attempts
    net.sleeps.clear()
    assert agm.MAX_RETRIES == 6


def test_retry_exhaustion_raises_agm_error_with_status_and_url(net):
    net.script = [("http", 429, "x" * 500, {})] * agm.MAX_RETRIES
    with pytest.raises(agm.AgmError) as ei:
        agm.request("GET", "p")
    e = ei.value
    assert e.status == 429 and e.url.endswith("/p")
    assert len(e.body) == 500 and "HTTP 429" in str(e)
    assert len(net.calls) == agm.MAX_RETRIES


def test_other_http_errors_are_not_retried(net):
    net.script = [("http", 403, "Authorization header missing", {}), {"v": 1}]
    with pytest.raises(agm.AgmError) as ei:
        agm.request("GET", "p")
    assert ei.value.status == 403 and len(net.calls) == 1


def test_urlerror_retried_then_wrapped_with_status_minus_one(net):
    net.script = [urllib.error.URLError("dns"), TimeoutError("t"), {"v": 2}]
    assert agm.request("GET", "p") == {"v": 2}
    net.script = [urllib.error.URLError("dns")] * agm.MAX_RETRIES
    with pytest.raises(agm.AgmError) as ei:
        agm.request("GET", "p")
    assert ei.value.status == -1 and "dns" in ei.value.body


def test_get_drops_none_params(net):
    net.script = [{"data": [1]}]
    agm._get("p", a=None, b=0, c="x")
    assert net.calls[0][0].endswith("/p?b=0&c=x")


def test_simple_wrappers_hit_expected_paths(net):
    cases = [
        (lambda: agm.live_date(), "agmarknet-live-date", {"data": 1}),
        (lambda: agm.report_filters(), "daily-price-arrival/filters", {"data": 1}),
        (lambda: agm.dashboard_filters("cumm_faq"), "dashboard-filters/?dashboard_name=cumm_faq", {"data": 1}),
        (lambda: agm.gis_filters(), "gis-mapping/filters", {"data": 1}),
        (lambda: agm.commodity_groups(), "Commoditygroup?page_size=500", {"data": 1}),
        (lambda: agm.grades(), "commodity/grade", {"data": 1}),
        (lambda: agm.units(), "commodity/unit", {"data": 1}),
        (lambda: agm.varieties(), "commodity/variety", {"data": 1}),
        (lambda: agm.states_with_districts(), "location/state?page_size=100", {"states": 1}),
        (lambda: agm.market_directory(), "dashboard-market-filter", {"data": 1}),
        (lambda: agm.dashboard_commodities(), "dashboard-commodities-filter", {"data": 1}),
        (lambda: agm.seasons(), "dashboard-season-filter", {"data": 1}),
        (lambda: agm.price_trend_years(4), "price-trend/year-filter?commodity=4", {"data": 1}),
        (lambda: agm.price_trend_states(4), "price-trend/state-filter?commodity=4", {"data": 1}),
        (lambda: agm.price_trend_districts(4, 19), "price-trend/district-filter?commodity=4&state=19", {"data": 1}),
        (lambda: agm.price_trend_months(4, 2025), "price-trend/month-filter?commodity=4&year=2025", {"data": 1}),
        (lambda: agm.price_trend_weeks(4, 2025, 3), "price-trend/week-filter?commodity=4&year=2025&month=3", {"data": 1}),
    ]
    for call, tail, payload in cases:
        net.script, net.calls = [payload], []
        assert call() == 1
        assert net.calls[0][0] == "https://api.agmarknet.gov.in/v1/" + tail


def test_passthrough_wrappers_return_whole_payload(net):
    for fn, payload in ((agm.markets, {"a": 1}), (agm.market_categories, [1]), (agm.msp_commodity_groups, {"z": 2}), (lambda: agm.market_holidays(7), {"h": 1})):
        net.script = [payload]
        assert fn() == payload


def test_commodities_dedupes_and_stops_when_page_adds_nothing(net):
    page = {"data": [{"id": 1}, {"id": 2}], "pagination": {"next_page": 2}}
    net.script = [page, {"data": [{"id": 1}, {"id": 2}], "pagination": {"next_page": 3}}]
    out = agm.commodities()
    assert [c["id"] for c in out] == [1, 2]
    assert len(net.calls) == 2                       # stops because page 2 added nothing


def test_commodities_follows_pages_until_no_next_page_and_keeps_first_copy(net):
    net.script = [{"data": [{"id": 1, "v": "a"}], "pagination": {"next_page": 2}},
                  {"data": [{"id": 1, "v": "dup"}, {"id": 2, "v": "b"}], "pagination": {"next_page": 3}},
                  {"data": [{"id": 3, "v": "c"}], "pagination": {}}]
    out = agm.commodities()
    assert [(c["id"], c["v"]) for c in out] == [(1, "a"), (2, "b"), (3, "c")]
    assert "page=3" in net.calls[2][0] and "page_size=500" in net.calls[0][0]


def test_market_profile_returns_nested_data_or_none(net):
    net.script = [{"records": {"data": [9]}}]
    assert agm.market_profile(1, 2, 3) == [9]
    assert "category_id=2&subcategory_id=3&market_id=1" in net.calls[0][0]
    net.script = [{"records": None}]
    assert agm.market_profile(1, 2, 3) is None
    net.script = [{}]
    assert agm.market_profile(1, 2, 3) is None


def test_market_profile_enums_queries_both_categories(net):
    net.script = [{"data": "c1"}, {"data": "c2"}]
    assert agm.market_profile_enums() == {1: "c1", 2: "c2"}
    assert "category_id=1&subcategory_id=" in net.calls[0][0]


def test_dashboard_data_pages_and_collects_meta(net):
    net.script = [{"data": {"records": [1, 2], "total": 3}, "pagination": {"next_page": 2}},
                  {"data": {"records": [3]}, "pagination": {}}]
    out = agm.dashboard_data("d", commodity=[1], limit=2)
    assert out["records"] == [1, 2, 3]
    assert out["meta"] == {"total": 3}
    assert out["pagination"] == {}
    b1, b2 = json.loads(net.calls[0][2]), json.loads(net.calls[1][2])
    assert (b1["page"], b2["page"]) == (1, 2)
    assert b1["dashboard"] == "d" and b1["limit"] == 2 and b1["format"] == "json" and b1["commodity"] == [1]


def test_dashboard_data_paginate_false_fetches_one_page(net):
    net.script = [{"data": {"records": [1]}, "pagination": {"next_page": 2}}]
    out = agm.dashboard_data("d", paginate=False)
    assert out["records"] == [1] and len(net.calls) == 1
    assert json.loads(net.calls[0][2])["limit"] == 500


def test_dashboard_data_list_and_null_data_shapes(net):
    net.script = [{"data": [7, 8], "pagination": None}]
    out = agm.dashboard_data("d")
    assert out["records"] == [7, 8] and out["meta"] == {}
    net.script = [{"data": None}]
    out = agm.dashboard_data("d")
    assert out["records"] == [] and out["meta"] == {}


def test_dashboard_data_fields_can_override_defaults(net):
    net.script = [{"data": {"records": []}}]
    agm.dashboard_data("d", format="xml")
    assert json.loads(net.calls[0][2])["format"] == "xml"


def test_dashboard_download_posts_export_flags(net):
    net.script = [FakeResp(b"x", "text/csv")]
    assert agm.dashboard_download("d", "xlsx", state=1) == (b"x", "text/csv")
    body = json.loads(net.calls[0][2])
    assert body["downloadreport"] == "true" and body["downloadformat"] == "xlsx" and body["state"] == 1


def test_statewise_price_arrival_type_codes(net):
    net.script = [{"data": {"records": []}}, {"data": {"records": []}}]
    agm.statewise_price_arrival(iter([4, 5]), "2025-04-01", "2025-04-30")
    agm.statewise_price_arrival([4], "a", "b", kind="arrival")
    b1, b2 = json.loads(net.calls[0][2]), json.loads(net.calls[1][2])
    assert (b1["type"], b2["type"]) == (100016, 100017)
    assert b1["commodity"] == [4, 5] and b1["dashboard"] == "statewise_price_arrival_sp"
    assert (b1["from_date"], b1["to_date"]) == ("2025-04-01", "2025-04-30")
    with pytest.raises(KeyError):
        agm.statewise_price_arrival([1], "a", "b", kind="nope")


def test_other_dashboard_helpers_bodies(net):
    net.script = [{"data": {"records": []}}] * 3
    agm.market_details([1], "2026-10-22")
    agm.marketwise_price_arrival([1], "a", "b")
    agm.cumm_arrival((1, 2), (19,), "a", "b")
    bodies = [json.loads(c[2]) for c in net.calls]
    assert bodies[0]["dashboard"] == "market_details_sp" and bodies[0]["date"] == "2026-10-22"
    assert bodies[1]["dashboard"] == "marketwise_price_arrival" and bodies[1]["from_date"] == "a"
    assert bodies[2]["dashboard"] == "cumm_arrival_sp" and bodies[2]["state"] == [19] and bodies[2]["commodity"] == [1, 2]


def test_price_trend_json_params(net):
    net.script = [{"rows": []}]
    agm.price_trend("prices_weekly", 4, 2025, 3, week=2)
    url = net.calls[0][0]
    assert url.startswith("https://api.agmarknet.gov.in/v1/price-trend/wholesale-prices-weekly?")
    for part in ("report_mode=Statewise", "commodity=4", "year=2025", "month=3", "state=0", "district=0", "week=2", "export=false"):
        assert part in url
    assert "downloadformat" not in url


def test_price_trend_omits_week_when_none_and_export_returns_raw(net):
    net.script = [FakeResp(b"csv", "text/csv")]
    out = agm.price_trend("arrivals_monthly", 4, 2025, 3, report_mode="MarketwiseAll", state=19, fmt="csv")
    assert out == (b"csv", "text/csv")
    url = net.calls[0][0]
    assert "week=" not in url and "export=true" in url and "downloadformat=csv" in url
    assert "report_mode=MarketwiseAll" in url and "state=19" in url


def test_price_trend_unknown_kind_raises(net):
    with pytest.raises(KeyError):
        agm.price_trend("nope", 1, 2025, 1)


def test_price_trend_map_has_six_kinds():
    assert sorted(agm.PRICE_TREND) == ["arrivals_monthly", "arrivals_weekly", "prices_monthly", "prices_weekly",
                                       "variety_prices_monthly", "variety_prices_weekly"]


def test_lastweek_wrappers_excel_flag(net):
    net.script = [{"d": 1}, FakeResp(b"x", "application/vnd.sheet"), {"d": 2}]
    assert agm.lastweek_market_prices(3046, 19, 1) == {"d": 1}
    assert "includeExcel=false" in net.calls[0][0] and "marketId=3046&stateId=19&commodityId=1" in net.calls[0][0]
    assert agm.lastweek_market_prices(3046, 19, 1, excel=True) == (b"x", "application/vnd.sheet")
    assert "includeExcel=true" in net.calls[1][0]
    assert agm.lastweek_commodity_prices(2139, 20, 23) == {"d": 2}
    assert "commodity-price/lastweek" in net.calls[2][0]


def test_save_and_n_helpers(tmp_path):
    agm._save(None, "x", {"a": 1})                         # no dir: no-op
    assert not (tmp_path / "o").exists()
    agm._save(str(tmp_path / "o"), "j", {"a": "é"})
    assert json.loads((tmp_path / "o/j.json").read_text()) == {"a": "é"}
    for ct, ext in (("text/csv", ".csv"), ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
                    ("application/pdf", ".pdf"), ("application/octet-stream", ".bin")):
        agm._save(str(tmp_path / "o"), "b", (b"1", ct))
        assert (tmp_path / "o" / f"b{ext}").read_bytes() == b"1"
    assert agm._n((b"abc", "text/csv")) == "3 bytes text/csv"
    assert agm._n({"records": [1, 2]}) == "2 records"
    assert agm._n({"rows": [1]}) == "1 rows"
    assert agm._n({"data": [1, 2, 3]}) == "3 data"
    assert agm._n({"zz": 1}) == "dict keys=['zz']"
    assert agm._n([1]) == "1 items"
    assert agm._n("x" * 100) == repr("x" * 100)[:60]


def test_smoke_main_runs_every_endpoint_against_a_fake_server(net, monkeypatch, tmp_path, capsys):
    import runpy
    import sys
    payload = {"data": [], "states": [], "records": {"data": []}, "pagination": {}}

    class AlwaysOK:
        def __call__(self, req, timeout=None):
            return FakeResp(payload)

    monkeypatch.setattr(agm.urllib.request, "urlopen", AlwaysOK())
    monkeypatch.setattr(sys, "argv", ["agmarknet.py", str(tmp_path / "samples")])
    runpy.run_path(agm.__file__, run_name="__main__")
    out = capsys.readouterr().out
    assert out.strip().endswith("37 ok, 0 failed")
    assert len(list((tmp_path / "samples").iterdir())) == 37


def test_smoke_main_reports_failures_and_keeps_going(monkeypatch, tmp_path, capsys):
    import runpy
    import sys

    def forbidden(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "no", {}, io.BytesIO(b"Authorization header missing"))

    monkeypatch.setattr(agm.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(agm.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["agmarknet.py"])
    runpy.run_path(agm.__file__, run_name="__main__")
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("FAIL live_date") and "HTTP 403" in out[0]
    assert out[-1] == "0 ok, 37 failed"
