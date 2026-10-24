"""Collect public UPAG (upag.gov.in) data into data/upag/.

    python3 collectors/upag_collect.py all
    python3 collectors/upag_collect.py apy-state | apy-india | apy-district | msp | wpi | fci | trade | calendar | latest

UPAG's reports are Plotly Dash pages; indiagri.upag calls their data callbacks directly (no login).
Responses are cached under .cache/ so reruns only fetch what is missing. Be polite: one call at a time.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from indiagri import upag                      # noqa: E402
from indiagri.io import cached, write_rows     # noqa: E402


def call(name, fn, *a, **k):
    def run():
        for i in range(4):
            try:
                time.sleep(1.0)
                return fn(*a, **k)[1]
            except Exception as e:                     # transient 5xx / timeouts
                if i == 3:
                    print(f"  {name}: failed ({str(e)[:100]})"); return []
                time.sleep(10 * (i + 1))
    return cached("upag_" + name, run) or []


def apy_state(_=None):
    rows = []
    for y0 in range(1997, 2026, 5):                    # 5-year chunks keep each response a few MB
        y1 = min(y0 + 4, 2025)
        r = call(f"apy_state_{y0}_{y1}", upag.apy_statewise, crops=["All"], from_year=y0, to_year=y1)
        print(f"apy_state {y0}-{y1}: {len(r)}"); rows += r
    print("apy_state:", write_rows("upag/apy_state.csv.gz", rows))


def apy_india(_=None):
    print("apy_all_india:", write_rows("upag/apy_all_india.csv.gz", call("apy_all_india", upag.apy_all_india)))


def apy_district(_=None):
    rows = []
    for y in range(2015, 2025):                        # 2015-16 .. 2024-25 (latest district year)
        for cat in ("Food Grains", "Oilseeds", "Commercial Crops"):
            r = call(f"apy_district_{y}_{cat}", upag.apy_district, year=y, crop_category=[cat], crops=["All"])
            print(f"apy_district {y} {cat}: {len(r)}"); rows += r
    print("apy_district:", write_rows("upag/apy_district.csv.gz", rows))


def msp(_=None):
    print("msp:", write_rows("upag/msp.csv.gz", call("msp_2010_2027", upag.msp, from_year="2010-11", to_year="2026-27")))


def wpi(_=None):
    print("wpi_monthly:", write_rows("upag/wpi_monthly.csv.gz", call("wpi_2012_2026", upag.wpi_monthly, from_year="2012", to_year="2026")))


def fci(_=None):
    rows = []
    for crop, ms, season in (("Rice", "KMS", "Kharif"), ("Wheat", "RMS", "Rabi")):
        for y in range(2016, 2027, 3):                 # each call returns the year plus two prior years
            yr = f"{y}-{str(y + 1)[2:]}"
            r = call(f"fci_{crop}_{yr}", upag.fci_procurement, year=yr, marketing_season=ms, season=season, crop=crop)
            print(f"fci {crop} {yr}: {len(r)}"); rows += r
    # keep year rows only (the report also returns "% Change in ..." summary rows), one row per state-crop-year
    seen, keep = set(), []
    for x in rows:
        k = (x.get("statename"), x.get("cropname"), x.get("years"))
        if str(x.get("years", "")).startswith("%") or k in seen:
            continue
        seen.add(k); keep.append(x)
    print("fci_procurement:", write_rows("upag/fci_procurement.csv.gz", keep))


def trade(_=None):
    rows = []
    for t in ("Export", "Import"):
        for cat in ("Commercial crops", "Food Grains", "Pulses", "Oilseeds", "Horticulture", "Spices"):
            r = call(f"trade_{t}_{cat}", upag.trade, trade_type=t, year_from=2015, year_to=2026, crop_category=[cat])
            print(f"trade {t} {cat}: {len(r)}"); rows += [{"trade": t, "category": cat, **x} for x in r]
    print("trade:", write_rows("upag/trade.csv.gz", rows))


def calendar_(_=None):
    print("crop_calendar:", write_rows("upag/crop_calendar.csv.gz", call("crop_calendar", upag.crop_calendar)))


def latest(_=None):
    print("latest_production_by_state:", write_rows("upag/latest_production_by_state.csv.gz",
                                                    call("latest_state", upag.latest_production_by_state)))
    print("latest_all_india:", write_rows("upag/latest_all_india.csv.gz", call("latest_india", upag.latest_all_india_estimates)))


JOBS = {"apy-state": apy_state, "apy-india": apy_india, "apy-district": apy_district, "msp": msp, "wpi": wpi,
        "fci": fci, "trade": trade, "calendar": calendar_, "latest": latest}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in JOBS.items():
        if which in ("all", name):
            fn()
