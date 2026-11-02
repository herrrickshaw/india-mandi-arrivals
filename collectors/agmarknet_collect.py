"""Collect Agmarknet data (public, no auth) into data/agmarknet/.

    python3 collectors/agmarknet_collect.py masters
    python3 collectors/agmarknet_collect.py state-monthly [--from 2019-01] [--to 2026-10]
    python3 collectors/agmarknet_collect.py market-sample [--step 6] [--from 2025-11-01] [--to 2026-10-23]
    python3 collectors/agmarknet_collect.py price-trend --commodity 4 --state 19 --years 2025 2026

All calls go through indiagri.agmarknet (throttled, 429 back-off) and are cached under .cache/,
so an interrupted run resumes where it stopped.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from indiagri import agmarknet as agm          # noqa: E402
from indiagri import transform as tf           # noqa: E402
from indiagri.io import cached, write_rows      # noqa: E402

BATCH_SIZE = 100          # commodity ids per statewise_price_arrival call

# 23 field crops used for the market-level sample (ids are Agmarknet commodity ids)
CORE = {1: "Wheat", 2: "Paddy(Common)", 3: "Rice", 4: "Maize", 5: "Jowar(Sorghum)", 6: "Bengal Gram(Gram)(Whole)",
        8: "Black Gram(Urd Beans)(Whole)", 9: "Green Gram(Moong)(Whole)", 10: "Groundnut", 12: "Mustard",
        13: "Soyabean", 15: "Cotton", 23: "Onion", 24: "Potato", 25: "Garlic", 28: "Bajra(Pearl Millet/Cumbu)",
        30: "Ragi(Finger Millet)", 35: "Turmeric", 38: "Cummin Seed(Jeera)", 45: "Red gram/Arhar/Tur(whole)",
        52: "Lentil(Masur)(Whole)", 65: "Tomato", 113: "Dry Chillies"}


def masters(_):
    jobs = {
        "masters/commodities.csv.gz": agm.commodities,
        "masters/commodity_groups.csv.gz": agm.commodity_groups,
        "masters/grades.csv.gz": agm.grades,
        "masters/units.csv.gz": agm.units,
        "masters/varieties.csv.gz": agm.varieties,
        "masters/markets.csv.gz": agm.markets,
        "masters/market_directory.csv.gz": agm.market_directory,
        "masters/market_categories.csv.gz": agm.market_categories,
        "masters/dashboard_commodities.csv.gz": agm.dashboard_commodities,
    }
    for path, fn in jobs.items():
        rows = cached("agm_" + path.replace("/", "_"), fn)
        rows = tf.first_list_value(rows)
        n = write_rows("agmarknet/" + path, rows)
        print(f"{path}: {n} rows")
    states = cached("agm_states", agm.states_with_districts)
    dist = tf.flatten_districts(states)
    print("masters/states:", write_rows("agmarknet/masters/states.csv.gz",
                                        [{k: v for k, v in s.items() if k != "districts"} for s in states]))
    print("masters/districts:", write_rows("agmarknet/masters/districts.csv.gz", dist))


def commodity_ids():
    """Every real commodity on the dashboard list (pseudo ids >= 9000 are skipped)."""
    rows = cached("agm_masters_dashboard_commodities.csv.gz", agm.dashboard_commodities)
    return tf.real_commodity_ids(rows)


def state_monthly(a):
    ids = commodity_ids(); batches = tf.chunked(ids, BATCH_SIZE)
    print(f"{len(ids)} commodities in {len(batches)} batches")
    out = {}
    for y, m in tf.months(a.frm, a.to):
        last = calendar.monthrange(y, m)[1]
        if (y, m) == tuple(map(int, a.to.split("-"))) and a.to_day:
            last = a.to_day
        f, t = f"{y}-{m:02d}-01", f"{y}-{m:02d}-{last:02d}"
        for bi, b in enumerate(batches):
            for kind in ("price", "arrival"):
                recs = cached(f"agm_swpa_{f}_{bi}_{kind}",
                              lambda: agm.statewise_price_arrival(b, f, t, kind)["records"])
                tf.merge_state_monthly(out, y, m, kind, recs)
        print(y, m, len(out), flush=True)
    rows = tf.sorted_state_monthly(out)
    print("state_monthly:", write_rows("agmarknet/state_monthly.csv.gz", rows,
                                       ["month", "commodity_id", "commodity", "group", "state", "arrivals_t", "price_rs_qtl"]))


def market_sample(a):
    d0, d1 = dt.date.fromisoformat(a.frm), dt.date.fromisoformat(a.to)
    rows, d = [], d0
    while d <= d1:
        ds = d.isoformat()
        recs = cached(f"agm_mkt_{ds}", lambda: tf.reported_markets(agm.market_details(list(CORE), ds)["records"]))
        rows += [tf.market_sample_row(ds, x) for x in recs]
        print(ds, len(rows), flush=True)
        d += dt.timedelta(days=a.step)
    print("market_daily_sample:", write_rows("agmarknet/market_daily_sample.csv.gz", rows))


def price_trend(a):
    rows = []
    for year in a.years:
        for month in range(1, 13):
            key = f"agm_pt_{a.kind}_{a.commodity}_{a.state}_{year}_{month}"
            try:
                recs = cached(key, lambda: agm.price_trend(a.kind, a.commodity, year, month,
                                                           report_mode="MarketwiseAll", state=a.state))
            except (agm.AgmError, ValueError) as e:      # months not yet published return an error
                print(year, month, "skipped:", str(e)[:80]); continue
            recs = recs.get("data", recs) if isinstance(recs, dict) else recs
            for r in recs if isinstance(recs, list) else []:
                rows.append({"year": year, "month": month, **r})
    print("price_trend:", write_rows(f"agmarknet/price_trend_{a.kind}_{a.commodity}_{a.state}.csv.gz", rows))


if __name__ == "__main__":
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("masters").set_defaults(fn=masters)
    s = sp.add_parser("state-monthly"); s.add_argument("--from", dest="frm", default="2019-01")
    s.add_argument("--to", default="2026-10"); s.add_argument("--to-day", type=int, default=23); s.set_defaults(fn=state_monthly)
    m = sp.add_parser("market-sample"); m.add_argument("--from", dest="frm", default="2025-11-01")
    m.add_argument("--to", default="2026-10-23"); m.add_argument("--step", type=int, default=6); m.set_defaults(fn=market_sample)
    t = sp.add_parser("price-trend"); t.add_argument("--kind", default="arrivals_monthly")
    t.add_argument("--commodity", type=int, required=True); t.add_argument("--state", type=int, required=True)
    t.add_argument("--years", type=int, nargs="+", required=True); t.set_defaults(fn=price_trend)
    a = p.parse_args(); a.fn(a)
