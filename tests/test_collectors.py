import argparse
import runpy
import sys
import types

import pytest

from collectors import agmarknet_collect as ac
from collectors import upag_collect as uc
from indiagri import agmarknet as agm
from indiagri import io as iio
from indiagri import upag


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(iio, "DATA", tmp_path / "data")
    monkeypatch.setattr(iio, "CACHE", tmp_path / ".cache")
    return tmp_path


def rows_of(rel):
    return iio.read_rows(rel)


# ----------------------------------------------------------------------------- agmarknet_collect
def test_months_is_inclusive_and_rolls_over_year():
    assert list(ac.months("2019-11", "2020-02")) == [(2019, 11), (2019, 12), (2020, 1), (2020, 2)]
    assert list(ac.months("2020-05", "2020-05")) == [(2020, 5)]
    assert list(ac.months("2020-06", "2020-05")) == []


def test_core_crop_list_has_23_ids():
    assert len(ac.CORE) == 23 and 1 in ac.CORE and ac.CORE[23] == "Onion"


def test_masters_writes_every_table_and_unwraps_dict_payloads(monkeypatch, capsys):
    for name in ("commodities", "commodity_groups", "grades", "units", "varieties", "markets", "market_directory",
                 "market_categories", "dashboard_commodities"):
        monkeypatch.setattr(agm, name, lambda n=name: [{"id": 1, "n": n}])
    monkeypatch.setattr(agm, "markets", lambda: {"meta": "x", "data": [{"market_id": 5}, {"market_id": 6}]})
    monkeypatch.setattr(agm, "market_categories", lambda: {"only": "scalar"})
    monkeypatch.setattr(agm, "states_with_districts", lambda: [
        {"state_id": 1, "state_name": "A", "districts": [{"district_id": 10}, {"district_id": 11}]},
        {"id": 2, "name": "B", "districts": None},
    ])
    ac.masters(None)
    assert rows_of("agmarknet/masters/markets.csv.gz") == [{"market_id": "5"}, {"market_id": "6"}]
    assert rows_of("agmarknet/masters/market_categories.csv.gz") == [{"only": "scalar"}]
    assert rows_of("agmarknet/masters/grades.csv.gz") == [{"id": "1", "n": "grades"}]
    states = rows_of("agmarknet/masters/states.csv.gz")
    assert [(s["state_name"], s["name"]) for s in states] == [("A", ""), ("", "B")]   # union of keys, first-seen order
    assert "districts" not in states[0]
    dist = rows_of("agmarknet/masters/districts.csv.gz")
    assert dist == [{"state_id": "1", "state_name": "A", "district_id": "10"},
                    {"state_id": "1", "state_name": "A", "district_id": "11"}]
    out = capsys.readouterr().out
    assert "masters/markets.csv.gz: 2 rows" in out and "masters/districts: 2" in out


def test_masters_falls_back_to_dict_wrapped_in_list_when_no_list_values(monkeypatch):
    for name in ("commodities", "commodity_groups", "grades", "units", "varieties", "markets", "market_directory",
                 "market_categories", "dashboard_commodities"):
        monkeypatch.setattr(agm, name, lambda: [])
    monkeypatch.setattr(agm, "states_with_districts", lambda: [])
    ac.masters(None)
    assert rows_of("agmarknet/masters/states.csv.gz") == [] and rows_of("agmarknet/masters/districts.csv.gz") == []


def test_commodity_ids_filters_pseudo_ids_and_non_digits(monkeypatch):
    monkeypatch.setattr(agm, "dashboard_commodities", lambda: [
        {"cmdt_id": 0}, {"cmdt_id": 5}, {"id": "7"}, {"cmdt_id": 9000}, {"cmdt_id": 8999}, {"cmdt_id": "x"},
        {"cmdt_id": 5}, {"cmdt_id": None, "id": 3}, {}, {"cmdt_id": 1.5}])
    assert ac.commodity_ids() == [3, 5, 7, 8999]


def args(**kw):
    return argparse.Namespace(**kw)


def test_state_monthly_merges_price_and_arrival_rows_by_name_since_arrivals_lack_cmdt_id(monkeypatch, capsys):
    monkeypatch.setattr(ac, "commodity_ids", lambda: list(range(1, 251)))        # 250 ids -> 3 batches of 100/100/50
    seen = []

    def fake(ids, f, t, kind):
        seen.append((len(ids), f, t, kind))
        if kind == "price":
            return {"records": [{"cmdt_id": 4, "cmdt_name": " Maize ", "cmdt_grp_name": "Cereals", "state_name": "Bihar ", "as_on": 2100}]}
        return {"records": [{"cmdt_name": "Maize", "cmdt_grp_name": "Cereals", "state_name": "Bihar", "as_on": 55}]}

    monkeypatch.setattr(agm, "statewise_price_arrival", fake)
    ac.state_monthly(args(frm="2025-01", to="2025-02", to_day=0))
    assert [s[0] for s in seen[:6]] == [100, 100, 100, 100, 50, 50]
    assert (seen[0][1], seen[0][2]) == ("2025-01-01", "2025-01-31")
    assert (seen[6][1], seen[6][2]) == ("2025-02-01", "2025-02-28")
    assert [s[3] for s in seen[:2]] == ["price", "arrival"]
    got = rows_of("agmarknet/state_monthly.csv.gz")
    assert len(got) == 2
    assert got[0] == {"month": "2025-01", "commodity_id": "4", "commodity": "Maize", "group": "Cereals", "state": "Bihar",
                      "arrivals_t": "55", "price_rs_qtl": "2100"}
    assert "250 commodities in 3 batches" in capsys.readouterr().out


def test_state_monthly_arrival_only_row_keeps_commodity_id_blank(monkeypatch):
    monkeypatch.setattr(ac, "commodity_ids", lambda: [1])

    def fake(ids, f, t, kind):
        if kind == "price":
            return {"records": []}
        return {"records": [{"cmdt_name": "Onion", "cmdt_grp_name": None, "state_name": "UP", "as_on": 9}]}

    monkeypatch.setattr(agm, "statewise_price_arrival", fake)
    ac.state_monthly(args(frm="2025-03", to="2025-03", to_day=0))
    (row,) = rows_of("agmarknet/state_monthly.csv.gz")
    assert row["commodity_id"] == "" and row["arrivals_t"] == "9" and row["price_rs_qtl"] == ""


def test_state_monthly_to_day_truncates_only_the_final_month(monkeypatch):
    monkeypatch.setattr(ac, "commodity_ids", lambda: [1])
    windows = []

    def fake(ids, f, t, kind):
        windows.append((f, t))
        return {"records": []}

    monkeypatch.setattr(agm, "statewise_price_arrival", fake)
    ac.state_monthly(args(frm="2026-09", to="2026-10", to_day=23))
    assert windows[0] == ("2026-09-01", "2026-09-30")
    assert windows[-1] == ("2026-10-01", "2026-10-23")


def test_state_monthly_full_month_when_to_day_is_zero(monkeypatch):
    monkeypatch.setattr(ac, "commodity_ids", lambda: [1])
    windows = []
    monkeypatch.setattr(agm, "statewise_price_arrival", lambda ids, f, t, kind: windows.append((f, t)) or {"records": []})
    ac.state_monthly(args(frm="2026-10", to="2026-10", to_day=0))
    assert windows[0] == ("2026-10-01", "2026-10-31")


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="cache key agm_swpa_<from>_<batch>_<kind> omits the to-date, so a partial-month run "
                          "(--to-day 23) is served stale on the next run with a later --to-day")
def test_state_monthly_cache_is_keyed_by_the_requested_window(monkeypatch):
    monkeypatch.setattr(ac, "commodity_ids", lambda: [1])
    windows = []
    monkeypatch.setattr(agm, "statewise_price_arrival", lambda ids, f, t, kind: windows.append((f, t)) or {"records": []})
    ac.state_monthly(args(frm="2026-10", to="2026-10", to_day=23))
    windows.clear()
    ac.state_monthly(args(frm="2026-10", to="2026-10", to_day=31))
    assert ("2026-10-01", "2026-10-31") in windows


def test_state_monthly_sorts_rows_by_commodity_state_month(monkeypatch):
    monkeypatch.setattr(ac, "commodity_ids", lambda: [1])

    def fake(ids, f, t, kind):
        names = [("Wheat", "B"), ("Wheat", "A"), ("Apple", "Z")]
        return {"records": [{"cmdt_id": 1, "cmdt_name": n, "state_name": s, "as_on": 1} for n, s in names]}

    monkeypatch.setattr(agm, "statewise_price_arrival", fake)
    ac.state_monthly(args(frm="2025-01", to="2025-02", to_day=0))
    got = [(r["commodity"], r["state"], r["month"]) for r in rows_of("agmarknet/state_monthly.csv.gz")]
    assert got == sorted(got) and len(got) == 6


def test_market_sample_steps_days_filters_reported_and_maps_columns(monkeypatch, capsys):
    calls = []

    def fake(ids, date):
        calls.append((list(ids), date))
        return {"records": [
            {"status": "Reported Markets", "cmdt_name": "Wheat", "state_name": "S", "district_name": "D", "mkt_name": "M",
             "mkt_id": 7, "arrival_qty": 12.5, "modal_price_wt": 2000},
            {"status": "Non Reported", "cmdt_name": "Rice", "mkt_id": 8}]}

    monkeypatch.setattr(agm, "market_details", fake)
    ac.market_sample(args(frm="2026-01-01", to="2026-01-13", step=6))
    assert [c[1] for c in calls] == ["2026-01-01", "2026-01-07", "2026-01-13"]
    assert calls[0][0] == list(ac.CORE)
    got = rows_of("agmarknet/market_daily_sample.csv.gz")
    assert len(got) == 3
    assert got[0] == {"date": "2026-01-01", "commodity": "Wheat", "state": "S", "district": "D", "market": "M",
                      "mkt_id": "7", "arrival_t": "12.5", "modal_price_rs_qtl": "2000"}
    assert "market_daily_sample: 3" in capsys.readouterr().out


def test_market_sample_end_date_is_inclusive_and_step_one(monkeypatch):
    dates = []
    monkeypatch.setattr(agm, "market_details", lambda ids, d: dates.append(d) or {"records": []})
    ac.market_sample(args(frm="2026-02-27", to="2026-03-01", step=1))
    assert dates == ["2026-02-27", "2026-02-28", "2026-03-01"]


def test_price_trend_collects_months_skips_errors_and_unwraps_data(monkeypatch, capsys):
    def fake(kind, commodity, year, month, report_mode, state):
        assert (kind, commodity, report_mode, state) == ("arrivals_monthly", 4, "MarketwiseAll", 19)
        if (year, month) == (2025, 5):
            raise RuntimeError("not published yet " * 10)
        if month == 1:
            return {"data": [{"market": "a"}]}
        if month == 2:
            return [{"market": "b"}, {"market": "c"}]
        return {"data": "not-a-list"}

    monkeypatch.setattr(agm, "price_trend", fake)
    ac.price_trend(args(kind="arrivals_monthly", commodity=4, state=19, years=[2025]))
    got = rows_of("agmarknet/price_trend_arrivals_monthly_4_19.csv.gz")
    assert [(r["year"], r["month"], r["market"]) for r in got] == [("2025", "1", "a"), ("2025", "2", "b"), ("2025", "2", "c")]
    out = capsys.readouterr().out
    assert "2025 5 skipped: not published yet" in out
    assert len(out.split("skipped: ")[1].split("\n")[0]) == 80


def test_price_trend_results_are_cached_across_runs(monkeypatch):
    n = []
    monkeypatch.setattr(agm, "price_trend", lambda *a, **k: n.append(1) or [])
    a = args(kind="prices_monthly", commodity=1, state=2, years=[2024])
    ac.price_trend(a)
    ac.price_trend(a)
    assert len(n) == 12


def run_cli(module_file, argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", [module_file, *argv])
    return runpy.run_path(module_file, run_name="__main__")


def test_agmarknet_cli_dispatch_and_defaults(monkeypatch, capsys):
    dispatched = []
    monkeypatch.setattr(ac, "masters", lambda a: None)
    # patch the real functions the CLI will call (the run_path copy re-imports agm / io, not ac)
    monkeypatch.setattr(agm, "commodities", lambda: [])
    for n in ("commodity_groups", "grades", "units", "varieties", "markets", "market_directory", "market_categories",
              "dashboard_commodities", "states_with_districts"):
        monkeypatch.setattr(agm, n, lambda: [])
    run_cli(ac.__file__, ["masters"], monkeypatch)
    assert "masters/commodities.csv.gz: 0 rows" in capsys.readouterr().out
    monkeypatch.setattr(agm, "price_trend", lambda *a, **k: [])
    g = run_cli(ac.__file__, ["price-trend", "--commodity", "4", "--state", "19", "--years", "2024", "2025"], monkeypatch)
    assert "price_trend: 0" in capsys.readouterr().out
    monkeypatch.setattr(agm, "dashboard_commodities", lambda: [])
    monkeypatch.setattr(agm, "statewise_price_arrival", lambda *a, **k: dispatched.append(a) or {"records": []})
    run_cli(ac.__file__, ["state-monthly", "--from", "2026-10", "--to", "2026-10"], monkeypatch)
    assert dispatched == []                                            # no commodities -> no batches
    monkeypatch.setattr(agm, "market_details", lambda ids, d: dispatched.append(d) or {"records": []})
    run_cli(ac.__file__, ["market-sample", "--from", "2026-10-01", "--to", "2026-10-10"], monkeypatch)
    assert dispatched == ["2026-10-01", "2026-10-07"]                  # default --step 6
    with pytest.raises(SystemExit):
        run_cli(ac.__file__, [], monkeypatch)
    with pytest.raises(SystemExit):
        run_cli(ac.__file__, ["price-trend", "--commodity", "4"], monkeypatch)


# ----------------------------------------------------------------------------- upag_collect
@pytest.fixture
def nosleep(monkeypatch):
    s = []
    monkeypatch.setattr(uc.time, "sleep", s.append)
    return s


def test_call_returns_second_element_and_caches(nosleep):
    n = []

    def fn(a, k=0):
        n.append((a, k))
        return b"raw", [{"x": a + k}]

    assert uc.call("nm", fn, 1, k=2) == [{"x": 3}]
    assert uc.call("nm", fn, 99) == [{"x": 3}]                     # served from cache
    assert n == [(1, 2)]


def test_call_retries_with_backoff_and_returns_empty_after_four_failures(nosleep, capsys):
    n = []

    def fn():
        n.append(1)
        raise OSError("e" * 300)

    assert uc.call("bad", fn) == []
    assert len(n) == 4
    assert nosleep == [1.0, 10, 1.0, 20, 1.0, 30, 1.0]
    out = capsys.readouterr().out
    assert out.strip() == "bad: failed (" + "e" * 100 + ")"


def test_call_recovers_after_transient_failure(nosleep):
    seq = iter([OSError("t"), (b"", [1, 2])])

    def fn():
        v = next(seq)
        if isinstance(v, Exception):
            raise v
        return v

    assert uc.call("flaky", fn) == [1, 2]
    assert nosleep == [1.0, 10, 1.0]


def test_call_empty_result_is_not_none(nosleep):
    assert uc.call("empty", lambda: (b"", [])) == []


@pytest.fixture
def fake_upag(monkeypatch, nosleep):
    log = []

    def mk(name, rows):
        def fn(*a, **k):
            log.append((name, a, k))
            return b"r", rows(*a, **k) if callable(rows) else rows
        return fn

    monkeypatch.setattr(upag, "apy_statewise", mk("apy_statewise", lambda **k: [{"y": k["from_year"], "to": k["to_year"]}]))
    monkeypatch.setattr(upag, "apy_all_india", mk("apy_all_india", [{"a": 1}]))
    monkeypatch.setattr(upag, "apy_district", mk("apy_district", lambda **k: [{"y": k["year"], "c": k["crop_category"][0]}]))
    monkeypatch.setattr(upag, "msp", mk("msp", [{"m": 1}]))
    monkeypatch.setattr(upag, "wpi_monthly", mk("wpi", [{"w": 1}]))
    monkeypatch.setattr(upag, "crop_calendar", mk("cal", [{"c": 1}]))
    monkeypatch.setattr(upag, "latest_production_by_state", mk("lps", [{"l": 1}]))
    monkeypatch.setattr(upag, "latest_all_india_estimates", mk("lai", [{"l": 2}]))
    return log


def test_apy_state_uses_five_year_chunks_capped_at_2025(fake_upag, capsys):
    uc.apy_state()
    spans = [(k["from_year"], k["to_year"]) for n, a, k in fake_upag]
    assert spans == [(1997, 2001), (2002, 2006), (2007, 2011), (2012, 2016), (2017, 2021), (2022, 2025)]
    assert all(k["crops"] == ["All"] for n, a, k in fake_upag)
    assert len(rows_of("upag/apy_state.csv.gz")) == 6


def test_apy_india_msp_wpi_calendar_latest_write_files(fake_upag):
    uc.apy_india()
    uc.msp()
    uc.wpi()
    uc.calendar_()
    uc.latest()
    assert rows_of("upag/apy_all_india.csv.gz") == [{"a": "1"}]
    assert rows_of("upag/msp.csv.gz") == [{"m": "1"}]
    assert rows_of("upag/wpi_monthly.csv.gz") == [{"w": "1"}]
    assert rows_of("upag/crop_calendar.csv.gz") == [{"c": "1"}]
    assert rows_of("upag/latest_production_by_state.csv.gz") == [{"l": "1"}]
    assert rows_of("upag/latest_all_india.csv.gz") == [{"l": "2"}]
    by = {n: k for n, a, k in fake_upag}
    assert by["msp"] == {"from_year": "2010-11", "to_year": "2026-27"}
    assert by["wpi"] == {"from_year": "2012", "to_year": "2026"}


def test_apy_district_covers_ten_years_by_three_categories(fake_upag):
    uc.apy_district()
    got = [(k["year"], k["crop_category"][0]) for n, a, k in fake_upag]
    assert len(got) == 30 and got[0] == (2015, "Food Grains") and got[-1] == (2024, "Commercial Crops")
    assert len(rows_of("upag/apy_district.csv.gz")) == 30


def test_fci_dedupes_state_crop_year_and_drops_percent_change_rows(monkeypatch, nosleep):
    def fci(**k):
        y = k["year"]
        return b"", [{"statename": "A", "cropname": k["crop"], "years": y},
                     {"statename": "A", "cropname": k["crop"], "years": y},               # duplicate
                     {"statename": "A", "cropname": k["crop"], "years": "% Change in " + y}]

    monkeypatch.setattr(upag, "fci_procurement", fci)
    uc.fci()
    got = rows_of("upag/fci_procurement.csv.gz")
    assert len(got) == 8                                       # 4 starts (2016,19,22,25) x 2 crops
    assert {r["years"] for r in got} == {"2016-17", "2019-20", "2022-23", "2025-26"}
    assert not [r for r in got if r["years"].startswith("%")]
    assert {(r["cropname"]) for r in got} == {"Rice", "Wheat"}


def test_fci_season_pairs_and_year_labels(monkeypatch, nosleep):
    seen = []
    monkeypatch.setattr(upag, "fci_procurement", lambda **k: seen.append(k) or (b"", []))
    uc.fci()
    assert seen[0] == {"year": "2016-17", "marketing_season": "KMS", "season": "Kharif", "crop": "Rice"}
    assert seen[4]["marketing_season"] == "RMS" and seen[4]["season"] == "Rabi" and seen[4]["crop"] == "Wheat"
    assert seen[-1]["year"] == "2025-26"


def test_trade_tags_rows_with_direction_and_category(monkeypatch, nosleep):
    seen = []

    def trade(**k):
        seen.append(k)
        return b"", [{"v": 1}]

    monkeypatch.setattr(upag, "trade", trade)
    uc.trade()
    got = rows_of("upag/trade.csv.gz")
    assert len(got) == 12 and got[0]["trade"] == "Export" and got[0]["category"] == "Commercial crops"
    assert got[-1]["trade"] == "Import" and got[-1]["category"] == "Spices"
    assert seen[0] == {"trade_type": "Export", "year_from": 2015, "year_to": 2026, "crop_category": ["Commercial crops"]}


def test_upag_cli_runs_selected_job_or_all(fake_upag, monkeypatch, capsys):
    run_cli(uc.__file__, ["msp"], monkeypatch)
    assert [n for n, a, k in fake_upag] == ["msp"]
    fake_upag.clear()
    monkeypatch.setattr(upag, "fci_procurement", lambda **k: (b"", []))
    monkeypatch.setattr(upag, "trade", lambda **k: (b"", []))
    run_cli(uc.__file__, [], monkeypatch)                                       # default: all
    assert {n for n, a, k in fake_upag} >= {"wpi", "apy_all_india", "cal", "lps", "lai"}
    fake_upag.clear()
    run_cli(uc.__file__, ["nonesuch"], monkeypatch)
    assert fake_upag == []
