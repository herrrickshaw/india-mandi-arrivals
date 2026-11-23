import math

import numpy as np
import pandas as pd
import pytest
from conftest import run_script


@pytest.fixture
def bi(root):
    return run_script("analysis/build_insights.py", root, name="bi")


def wheat_price(state, k):
    return 2000.0 + (100.0 if state == "UP" else 0.0) + 10.0 * k


# ------------------------------------------------------------------ load_monthly
def test_load_monthly_adds_all_india_rows_weighted_by_reliable_arrivals(bi):
    m = bi["load_monthly"]()
    ai = m[(m["state"] == "All India") & (m["commodity"] == "Wheat")].set_index("month")
    assert len(ai) == 46
    for k in (0, 45):
        mo = f"{2023 + k // 12}-{k % 12 + 1:02d}"
        # Punjab 100 t and UP 150 t are reliable; Andaman (10 t < MIN_T=50) is not
        expect = (100 * wheat_price("Punjab", k) + 150 * wheat_price("UP", k)) / 250
        assert ai.loc[mo, "price_rs_qtl"] == pytest.approx(expect)
        assert ai.loc[mo, "arrivals_t"] == 250
    assert set(m.loc[m["state"] == "All India", "upag_state"]) == {"All India"}


def test_load_monthly_min_tonnes_is_inclusive_at_50(bi, monkeypatch):
    assert bi["MIN_T"] == 50
    m = bi["load_monthly"]()
    sub = m[(m["commodity"] == "Onion") & (m["month"] == "2023-01") & (m["state"] != "All India")]
    assert sorted(sub["arrivals_t"]) == [10, 300, 350]


def test_load_monthly_maps_state_names_and_coerces_blanks(bi):
    m = bi["load_monthly"]()
    up = m[m["state"] == "UP"]
    assert set(up["upag_state"]) == {"Uttar Pradesh"}
    assert set(m.loc[m["state"] == "Punjab", "upag_state"]) == {"Punjab"}
    assert set(m.loc[m["state"] == "Andaman and Nicobar", "upag_state"]) == {"Andaman And Nicobar Islands"}
    blank = m[(m["commodity"] == "Wheat") & (m["state"] == "Punjab") & (m["month"] == "2026-10") & m["arrivals_t"].isna()]
    assert len(blank) == 1 and blank["price_rs_qtl"].isna().all()
    assert (m["date"] == pd.to_datetime(m["month"] + "-01")).all()


def test_apy_state_pivots_total_state_rows_only(bi):
    a = bi["apy_state"]()
    assert len(a) == 12                                    # 2 states x 2 crops x 3 years
    r = a[(a["State"] == "Punjab") & (a["Crop"] == "Wheat") & (a["Crop Year"] == "2023-24")].iloc[0]
    assert r["Production"] == 0.5 and r["Area"] == 0.1 and r["Yield"] == 5000


# ------------------------------------------------------------------ arrivals_share
def test_arrivals_share_converts_with_factor_and_crop_year_boundaries(bi, root):
    m, a = bi["load_monthly"](), bi["apy_state"]()
    j = bi["arrivals_share"](m, a)
    assert len(j) == 12 and list(j.columns) == ["state", "crop", "crop_year", "arrivals_t", "production_t",
                                                "arrivals_share_of_production", "months_reported"]
    assert sorted(set(j["crop_year"])) == ["2023-24", "2024-25", "2025-26"]
    w = j[(j["state"] == "Punjab") & (j["crop"] == "Wheat") & (j["crop_year"] == "2023-24")].iloc[0]
    assert w["months_reported"] == 12                      # Jul 2023 .. Jun 2024 inclusive
    assert w["arrivals_t"] == 100 * 12                     # factor 1
    assert w["production_t"] == pytest.approx(0.5 * 1e5)   # lakh tonnes -> tonnes
    assert w["arrivals_share_of_production"] == pytest.approx(1200 / 50000)
    r = j[(j["state"] == "Uttar Pradesh") & (j["crop"] == "Rice") & (j["crop_year"] == "2025-26")].iloc[0]
    assert r["arrivals_t"] == pytest.approx(250 * 0.67 * 12)
    assert r["arrivals_share_of_production"] == pytest.approx(250 * 0.67 * 12 / 25000)
    assert not (j["state"].str.contains("Andaman")).any()
    assert (root / "reports/arrivals_share_of_production.csv").exists()
    assert len(pd.read_csv(root / "reports/arrivals_share_of_production.csv")) == 12


def test_arrivals_share_drops_partial_crop_years(bi):
    j = bi["arrivals_share"](bi["load_monthly"](), bi["apy_state"]())
    assert "2026-27" not in set(j["crop_year"])            # only Jul-Oct 2026 = 4 months
    assert "2022-23" not in set(j["crop_year"])            # only Jan-Jun 2023 = 6 months
    assert j["months_reported"].min() == 12


def test_arrivals_share_requires_ten_months(bi):
    m, a = bi["load_monthly"](), bi["apy_state"]()
    keep = ~((m["commodity"] == "Wheat") & (m["state"] == "Punjab") & (m["month"].isin(["2023-07", "2023-08", "2023-09"])))
    j = bi["arrivals_share"](m[keep], a)                   # 9 months left in 2023-24 -> dropped
    assert j[(j["state"] == "Punjab") & (j["crop"] == "Wheat")]["crop_year"].tolist() == ["2024-25", "2025-26"]
    keep = ~((m["commodity"] == "Wheat") & (m["state"] == "Punjab") & (m["month"].isin(["2023-07", "2023-08"])))
    j = bi["arrivals_share"](m[keep], a)                   # exactly 10 months stays
    row = j[(j["state"] == "Punjab") & (j["crop"] == "Wheat") & (j["crop_year"] == "2023-24")]
    assert row["months_reported"].tolist() == [10]


# ------------------------------------------------------------------ mandi_vs_msp
def test_mandi_vs_msp_marketing_year_switches_in_april_for_rabi_and_october_for_kharif(bi):
    x = bi["mandi_vs_msp"](bi["load_monthly"]())
    assert len(x) == 276
    g = lambda mo, c, s: x[(x["month"] == mo) & (x["commodity"] == c) & (x["state"] == s)].iloc[0]
    assert g("2023-03", "Wheat", "Punjab")["msp_year"] == "2022-23"
    assert g("2023-04", "Wheat", "Punjab")["msp_year"] == "2023-24"
    assert g("2023-09", "Paddy(Common)", "Punjab")["msp_year"] == "2022-23"
    assert g("2023-10", "Paddy(Common)", "Punjab")["msp_year"] == "2023-24"
    assert g("2026-04", "Wheat", "UP")["msp_year"] == "2026-27"
    r = g("2023-04", "Wheat", "Punjab")
    assert r["msp_rs_qtl"] == 2100 and r["price_rs_qtl"] == pytest.approx(2030)
    assert r["price_vs_msp"] == pytest.approx(2030 / 2100 - 1) and bool(r["below_msp"]) is True
    hi = g("2026-10", "Wheat", "UP")                       # 2100 + 450 = 2550 vs 2400
    assert hi["price_vs_msp"] == pytest.approx(2550 / 2400 - 1) and bool(hi["below_msp"]) is False
    assert list(x.columns) == ["month", "commodity", "state", "arrivals_t", "price_rs_qtl", "msp_year", "msp_rs_qtl",
                               "price_vs_msp", "below_msp"]


def test_mandi_vs_msp_excludes_unreliable_states_and_crops_without_msp_crosswalk(bi):
    x = bi["mandi_vs_msp"](bi["load_monthly"]())
    assert "Onion" not in set(x["commodity"])
    assert "Andaman and Nicobar" not in set(x["state"])
    assert "All India" in set(x["state"])
    assert x["price_rs_qtl"].notna().all()


def test_mandi_vs_msp_exact_msp_is_not_below(bi):
    m = bi["load_monthly"]()
    m.loc[(m["commodity"] == "Wheat") & (m["state"] == "Punjab") & (m["month"] == "2023-04"), "price_rs_qtl"] = 2100.0
    x = bi["mandi_vs_msp"](m)
    r = x[(x["month"] == "2023-04") & (x["commodity"] == "Wheat") & (x["state"] == "Punjab")].iloc[0]
    assert r["price_vs_msp"] == 0 and bool(r["below_msp"]) is False


# ------------------------------------------------------------------ vol_season
def test_vol_season_metrics_for_linear_price_series(bi):
    v = bi["vol_season"](bi["load_monthly"]())
    assert len(v) == 9                                      # 3 crops x (Punjab, UP, All India); Andaman unreliable
    r = v[(v["commodity"] == "Wheat") & (v["state"] == "Punjab")].iloc[0]
    base = 2000.0
    moves = [10 / (base + 10 * (k - 1)) for k in range(1, 46)]
    assert r["months_counted"] == 45
    assert r["typical_monthly_move"] == pytest.approx(np.median(moves))
    assert r["cheapest_month"] == 1 and r["dearest_month"] == 12
    mean_by_month = {mo: np.mean([base + 10 * (mo - 1 + 12 * i) for i in range(3)]) for mo in range(1, 13)}
    overall = np.mean([base + 10 * k for k in range(36)])
    assert r["seasonal_spread"] == pytest.approx(mean_by_month[12] / mean_by_month[1] - 1)
    assert overall > 0
    assert r["arrivals_last12m_t"] == 1200                  # 2025-11 .. 2026-10 (the blank 2026-10 row is excluded)
    assert r["median_price_last12m"] == pytest.approx(np.median([base + 10 * k for k in range(34, 46)]))
    assert r["peak_arrival_month"] == 1 and r["peak_month_share"] == pytest.approx(1 / 12)


def test_vol_season_skips_short_histories_and_gaps_break_changes(bi):
    m = bi["load_monthly"]()
    sub = m[(m["commodity"] == "Wheat") & (m["state"] == "Punjab") & m["arrivals_t"].ge(50)]
    short = sub[sub["month"] <= "2025-01"]                  # 25 months -> 24 changes: kept (>= 24)
    assert len(bi["vol_season"](short)) == 1
    assert bi["vol_season"](short)["months_counted"].iloc[0] == 24
    shorter = sub[sub["month"] <= "2024-12"]                # 24 months -> 23 changes: skipped
    assert bi["vol_season"](shorter).empty
    gap = sub[sub["month"] != "2024-06"]                    # two changes lost at the gap
    assert bi["vol_season"](gap)["months_counted"].iloc[0] == 43


def test_vol_season_ignores_changes_before_vol_from(bi):
    assert bi["VOL_FROM"] == "2023-01"
    m = bi["load_monthly"]()
    sub = m[(m["commodity"] == "Wheat") & (m["state"] == "Punjab") & m["arrivals_t"].ge(50)].copy()
    early = sub.assign(date=sub["date"] - pd.DateOffset(years=1), month=lambda d: (d["date"]).dt.strftime("%Y-%m"))
    v = bi["vol_season"](early)                             # 2022-01 .. 2025-10: first change (2022-02) is before VOL_FROM
    assert v["months_counted"].iloc[0] == 34                # only changes landing on/after 2023-01


# ------------------------------------------------------------------ yields / area
def line(c, y):
    return c + 10 * (y - 2000)


def test_yields_three_year_cagr_formula(bi):
    y = bi["yields"]().set_index("crop")
    w = y.loc["Wheat"]
    assert w["latest_year"] == 2025 and w["latest_yield_kg_ha"] == line(2000, 2025)
    assert w["cagr_2000_latest"] == pytest.approx((line(2000, 2024) / line(2000, 2000)) ** (1 / 24) - 1)
    assert w["cagr_2015_latest"] == pytest.approx((line(2000, 2024) / line(2000, 2015)) ** (1 / 9) - 1)
    assert w["cagr_1970_2000"] == pytest.approx((line(2000, 2000) / line(2000, 1970)) ** (1 / 30) - 1)
    r = y.loc["Rice"]
    assert r["cagr_2015_latest"] == pytest.approx((line(2500, 2024) / line(2500, 2015)) ** (1 / 9) - 1)


def test_yields_missing_window_gives_none_not_crash(bi, root):
    import gzip, csv
    p = root / "data/upag/apy_all_india.csv.gz"
    rows = list(csv.reader(gzip.open(p, "rt")))
    keep = [rows[0]] + [r for r in rows[1:] if int(r[1][:4]) >= 1995]
    with gzip.open(p, "wt", newline="") as fh:
        csv.writer(fh).writerows(keep)
    y = bi["yields"]().set_index("crop")
    assert pd.isna(y.loc["Wheat", "cagr_1970_2000"])
    assert y.loc["Wheat", "cagr_2000_latest"] == pytest.approx((line(2000, 2024) / line(2000, 2000)) ** (1 / 24) - 1)


def test_area_latest_vs_ten_years_before_sorted_desc(bi):
    a = bi["area"]()
    assert list(a["Crop"]) == ["Rice", "Wheat"]
    r = a.iloc[1]
    assert r["area_lakh_ha_latest"] == 300 + 25 and r["area_lakh_ha_10y_before"] == 300 + 15
    assert r["latest_year"] == 2025
    assert r["change_10y"] == pytest.approx(325 / 315 - 1)
    assert list(a.columns) == ["Crop", "area_lakh_ha_latest", "area_lakh_ha_10y_before", "latest_year", "change_10y"]


# ------------------------------------------------------------------ top_mandis / pct
def test_top_mandis_totals_main_crop_and_est_annual(bi):
    g = bi["top_mandis"]()
    assert list(g["market"]) == ["m1 apmc", "m3", "m2"]
    top = g.iloc[0]
    assert top["sampled_t"] == 240 and top["crops"] == 2 and top["est_annual_t"] == 240 * 6
    assert top["main_crop"] == "Wheat" and top["main_crop_sampled_t"] == 200
    assert top["main_crop_share"] == pytest.approx(200 / 240)
    assert g.iloc[1]["main_crop"] == "Paddy(Common)" and g.iloc[1]["main_crop_share"] == 1.0


def test_top_mandis_step_scales_estimate(bi):
    g = bi["top_mandis"](step=3)
    assert g.iloc[0]["est_annual_t"] == 240 * 3


def test_pct_formatting(bi):
    assert bi["pct"](0.1234) == "12.3%"
    assert bi["pct"](-0.05) == "-5.0%"
    assert bi["pct"](0) == "0.0%"


# ------------------------------------------------------------------ __main__ report
def test_main_writes_all_reports_and_markdown(root, capsys):
    run_script("analysis/build_insights.py", root, name="__main__")
    out = capsys.readouterr().out
    names = ["INSIGHTS.md", "area_by_crop.csv", "arrivals_share_of_production.csv", "mandi_vs_msp.csv", "top_mandis.csv",
             "volatility_seasonality.csv", "yield_trends.csv"]
    assert out.strip() == f"wrote reports/: {names}"
    md = (root / "reports/INSIGHTS.md").read_text()
    assert md.startswith("# Insights\n")
    assert "## Mandi arrivals as a share of production (crop year 2025-26)" in md
    assert "| Punjab | Wheat | 1,200 | 50,000 | 2.4% |" in md
    assert "| Uttar Pradesh | Rice | 2,010 | 25,000 | 8.0% |" in md
    assert "## Mandi prices against MSP, last 24 months" in md
    assert "## Yield growth (all-India, compound annual)" in md
    assert "## Area by crop (all-India, 2025 vs 10 years earlier)" in md
    assert "| Rice | 425.0 | 415.0 | 2.4% |" in md
    assert "| m1 apmc | D1 | Punjab | 1,440 | Wheat | 83.3% |" in md
    assert md.endswith("\n") and not md.endswith("\n\n")


def test_main_msp_section_covers_last_24_months_only(root):
    g = run_script("analysis/build_insights.py", root, name="__main__")
    md = (root / "reports/INSIGHTS.md").read_text()
    sec = md.split("## Mandi prices against MSP, last 24 months")[1].split("\n## ")[0]
    ms = g["ms"]
    last2 = ms[ms["month"] >= "2024-11"]
    wheat = last2[last2["commodity"] == "Wheat"]
    assert f"| Wheat | {len(wheat)} |" in sec
    below = wheat["below_msp"].mean() * 100
    assert f"{below:.1f}%" in sec


def test_main_yield_table_shows_dash_for_missing_growth_windows(root, tmp_path):
    import csv, gzip
    p = root / "data/upag/apy_all_india.csv.gz"
    rows = list(csv.reader(gzip.open(p, "rt")))
    with gzip.open(p, "wt", newline="") as fh:
        csv.writer(fh).writerows([rows[0]] + [r for r in rows[1:] if int(r[1][:4]) >= 1995])
    run_script("analysis/build_insights.py", root, name="__main__")
    md = (root / "reports/INSIGHTS.md").read_text()
    wheat = [l for l in md.splitlines() if l.startswith("| Wheat | 2,250 |")]
    assert len(wheat) == 1 and wheat[0].split("|")[3].strip() == "–"        # 1970-2000 column


def test_main_volatility_section_lists_only_markets_with_100k_tonnes(root):
    import synth
    rows = []
    for k, mo in enumerate(synth.MONTHS):
        rows.append([mo, 1, "Wheat", "g", "Punjab", 20000.0, 2000 + 10 * k])          # 240,000 t in the last 12 months
        rows.append([mo, 1, "Wheat", "g", "UP", 8000.0, 2000 + 10 * k])               # 96,000 t: below the 100,000 cut
    synth.write_gz(root / "data/agmarknet/state_monthly.csv.gz",
                   ["month", "commodity_id", "commodity", "group", "state", "arrivals_t", "price_rs_qtl"], rows)
    run_script("analysis/build_insights.py", root, name="__main__")
    md = (root / "reports/INSIGHTS.md").read_text()
    sec = md.split("## Most and least volatile large markets")[1].split("\n## ")[0]
    assert "| Wheat | Punjab | 240,000 |" in sec and "| Wheat | All India | 336,000 |" in sec
    assert "| Wheat | UP |" not in sec
    assert "| 1 | 12 |" in sec                                                        # cheapest / dearest calendar months
