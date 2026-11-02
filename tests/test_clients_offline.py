"""Client behaviour with the network stubbed out: nothing here opens a socket."""
import io
import json
import urllib.error

import pytest

from indiagri import agmarknet as agm
from indiagri import upag


class FakeResp(io.BytesIO):
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(agm.time, "sleep", lambda s: None)
    monkeypatch.setattr(agm, "MIN_INTERVAL", 0)


def test_request_retries_429_then_succeeds(monkeypatch):
    calls = []

    def fake(req, timeout):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "slow", {"Retry-After": "2"}, io.BytesIO(b"busy"))
        return FakeResp(b'{"ok": true}')

    monkeypatch.setattr(agm.urllib.request, "urlopen", fake)
    assert agm.request("GET", "x", params={"a": 1}) == {"ok": True}
    assert len(calls) == 2 and calls[0].endswith("/v1/x?a=1")


def test_request_raises_agmerror_on_403(monkeypatch):
    def fake(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "no", {}, io.BytesIO(b"Authorization header missing"))

    monkeypatch.setattr(agm.urllib.request, "urlopen", fake)
    with pytest.raises(agm.AgmError) as ei:
        agm.request("GET", "secret")
    assert ei.value.status == 403


def test_dashboard_data_pages_via_body_and_collects_records(monkeypatch):
    seen = []

    def fake_request(method, path, params=None, body=None, raw=False):
        seen.append(dict(body))
        page = body["page"]
        return {"data": {"records": [{"p": page}], "total": 2}, "pagination": {"next_page": page < 2}}

    monkeypatch.setattr(agm, "request", fake_request)
    out = agm.dashboard_data("market_details_sp", commodity=[1], date="2026-01-01")
    assert [r["p"] for r in out["records"]] == [1, 2]
    assert [b["page"] for b in seen] == [1, 2] and seen[0]["dashboard"] == "market_details_sp"
    assert out["meta"] == {"total": 2}


def test_commodities_stops_when_server_repeats_the_same_page(monkeypatch):
    page = {"data": [{"id": 1}, {"id": 2}], "pagination": {"next_page": True}}
    monkeypatch.setattr(agm, "_get", lambda path, **p: page)
    assert [c["id"] for c in agm.commodities()] == [1, 2]


def test_dash_callback_builds_multi_output_body(monkeypatch):
    sent = {}

    def fake_post(url, body, timeout=180):
        sent.update(body)
        return json.dumps({"response": {"s-store": {"data": [{"a": 1}]}}}).encode()

    monkeypatch.setattr(upag, "_post", fake_post)
    raw, resp = upag.dash_callback("..s-store.data...s-title.children..", "s-filters-store", {"f": 1})
    assert [o["id"] for o in sent["outputs"]] == ["s-store", "s-title"]
    assert sent["inputs"] == [{"id": "s-filters-store", "property": "data", "value": {"f": 1}}]
    assert sent["state"][0]["id"] == "url"
    assert upag._rows(resp, "s-store") == [{"a": 1}]


def test_dash_callback_single_output_is_not_a_list(monkeypatch):
    sent = {}
    monkeypatch.setattr(upag, "_post", lambda u, b, timeout=180: sent.update(b) or b'{"response": {}}')
    upag.dash_callback("..a-store.data..", "a-f", {}, with_url_state=False)
    assert sent["outputs"] == {"id": "a-store", "property": "data"} and "state" not in sent
