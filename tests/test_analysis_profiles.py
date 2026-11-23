import math
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import pytest
import synth
from conftest import run_script


@pytest.fixture
def proot(tmp_path):
    return synth.build_profiles_root(tmp_path / "prof")


@pytest.fixture
def prof(proot, capsys):
    g = run_script("analysis/crop_profiles.py", proot, name="__main__")
    g["_out"] = capsys.readouterr().out
    return g


def rd(root, name):
    return pd.read_csv(root / "reports" / name)


def mean(f, lo, hi):
    return np.mean([f(y) for y in range(lo, hi + 1)])


def test_years_helper_wraps_century(prof):
    assert prof["years"](1999, 2001) == ["1999-00", "2000-01", "2001-02"]
    assert prof["P0"] == ["2003-04", "2004-05", "2005-06"] and prof["P1"] == ["2023-24", "2024-25", "2025-26"]


def test_main_skips_crops_with_short_windows_and_reports_row_count(prof, proot):
    p = rd(proot, "crop_profiles.csv")
    assert list(p["crop"]) == ["Wheat", "Rapeseed & Mustard", "Cotton"]          # CROPS order; Maize/others skipped
    assert "wrote crop_profiles.csv, 3 crops" in prof["_out"]


def test_cotton_bale_sanity_print(prof):
    A, Y, P = synth.PROFILE_CROPS["Cotton"]
    implied = [round(P(y) * 170 / A(y)) for y in (2023, 2024, 2025)]
    assert f"cotton implied lint yield (kg/ha): {[float(i) for i in implied]} published: " in prof["_out"]


def test_growth_decomposition_uses_log_split_over_twenty_years(prof, proot):
    A, Y, P = synth.PROFILE_CROPS["Wheat"]
    r = rd(proot, "crop_profiles.csv").set_index("crop").loc["Wheat"]
    q0, q1 = mean(P, 2003, 2005), mean(P, 2023, 2025)
    a0, a1 = mean(A, 2003, 2005), mean(A, 2023, 2025)
    y0, y1 = mean(Y, 2003, 2005), mean(Y, 2023, 2025)
    assert r["production_2003_06"] == pytest.approx(q0) and r["production_2023_26"] == pytest.approx(q1)
    assert r["production_growth_pa"] == pytest.approx(math.exp(math.log(q1 / q0) / 20) - 1)
    assert r["area_growth_pa"] == pytest.approx(math.exp(math.log(a1 / a0) / 20) - 1)
    assert r["yield_growth_pa"] == pytest.approx(math.exp(math.log(y1 / y0) / 20) - 1)
    assert r["yield_share_of_growth"] == pytest.approx(math.log(y1 / y0) / math.log(q1 / q0))
    assert r["unit"] == "lakh tonnes"


def test_non_positive_growth_has_no_yield_share_and_cotton_unit(prof, proot):
    p = rd(proot, "crop_profiles.csv").set_index("crop")
    assert pd.isna(p.loc["Cotton", "yield_share_of_growth"])           # production fell
    assert pd.isna(p.loc["Rapeseed & Mustard", "yield_share_of_growth"])   # flat: lnP == 0 is not > 0
    assert p.loc["Cotton", "unit"] == "lakh bales (170 kg)"
    assert p.loc["Cotton", "production_growth_pa"] < 0


def test_volatility_and_record_fields(prof, proot):
    A, Y, P = synth.PROFILE_CROPS["Wheat"]
    r = rd(proot, "crop_profiles.csv").set_index("crop").loc["Wheat"]
    yoy = [P(y) / P(y - 1) - 1 for y in range(2001, 2026)]               # first diff is 2000-01 -> 2001-02
    assert r["typical_yoy_swing"] == pytest.approx(np.median(np.abs(yoy)))
    assert r["worst_yoy_fall"] == pytest.approx(min(yoy)) and r["worst_fall_year"] == "2025-26"
    assert r["record_year"] == "2025-26" and r["record_production"] == P(2025)
    assert r["latest_year"] == "2025-26" and r["latest_production"] == P(2025)
    c = rd(proot, "crop_profiles.csv").set_index("crop").loc["Cotton"]
    cp = synth.PROFILE_CROPS["Cotton"][2]
    assert c["record_year"] == "2000-01" and c["record_production"] == cp(2000)
    assert c["worst_fall_year"] == "2025-26"
    assert c["latest_production"] == cp(2025)


def test_state_shares_merge_ladakh_into_jammu_and_kashmir(prof, proot):
    t = rd(proot, "crop_top_states.csv")
    w = t[t["crop"] == "Wheat"].set_index("rank")
    assert list(w["state"]) == ["Punjab", "Haryana", "Jammu And Kashmir", "Bihar", "Goa"]
    tot = 60 + 30 + 8 + 2 + 10
    assert w.loc[1, "share"] == pytest.approx(60 / tot) and w.loc[3, "share"] == pytest.approx(10 / tot)
    assert w.loc[3, "production"] == 10
    assert w.loc[1, "yield_kg_ha"] == pytest.approx(60 / 30 * 1000)
    assert w.loc[3, "yield_kg_ha"] == pytest.approx(10 / 10 * 1000)       # Ladakh + J&K production and area both merged
    assert w.loc[1, "share_2003_06"] == pytest.approx(50 / 100)
    assert pd.isna(w.loc[5, "share_2003_06"])                              # Goa had no 2003-06 production


def test_top_states_limited_to_five_and_rank_starts_at_one(prof, proot):
    t = rd(proot, "crop_top_states.csv")
    assert {c: list(g["rank"]) for c, g in t.groupby("crop")} == {c: [1, 2, 3, 4, 5] for c in ("Wheat", "Cotton", "Rapeseed & Mustard")}


def test_cotton_yield_uses_bale_weight(prof, proot):
    t = rd(proot, "crop_top_states.csv")
    c = t[t["crop"] == "Cotton"].set_index("rank")
    assert c.loc[1, "yield_kg_ha"] == pytest.approx(60 * 170 / 30)
    assert c.loc[2, "yield_kg_ha"] == pytest.approx(30 * 170 / 10)


def test_concentration_metrics(prof, proot):
    p = rd(proot, "crop_profiles.csv").set_index("crop").loc["Wheat"]
    tot = 110
    assert p["top_state"] == "Punjab" and p["top_state_share"] == pytest.approx(60 / tot)
    assert p["top3_share"] == pytest.approx((60 + 30 + 10) / tot)
    assert p["top3_share_2003_06"] == pytest.approx((50 + 20 + 20) / 100)


def test_yield_gap_only_compares_states_with_three_percent_share(prof, proot):
    g = rd(proot, "crop_state_yield_gaps.csv").set_index("crop").loc["Wheat"]
    A, Y, P = synth.PROFILE_CROPS["Wheat"]
    assert g["states_compared"] == 4                                       # Goa (1.8%) excluded
    assert g["best_state"] == "Haryana" and g["best_yield"] == pytest.approx(3000)
    assert g["worst_state"] == "Jammu And Kashmir" and g["worst_yield"] == pytest.approx(1000)
    assert g["national_yield"] == pytest.approx(mean(Y, 2023, 2025))


def test_district_tops_use_only_the_2022_2024_production_window(prof, proot):
    d = rd(proot, "crop_top_districts.csv")
    w = d[d["crop"] == "Wheat"].set_index("rank")
    assert list(w["district"]) == ["Ludhiana", "Amritsar", "Karnal", "Zeroland"]
    assert w.loc[1, "production"] == 10 and w.loc[1, "share"] == pytest.approx(10 / 20)
    p = rd(proot, "crop_profiles.csv").set_index("crop").loc["Wheat"]
    assert p["top10_district_share"] == pytest.approx(1.0)
    assert p["districts_producing"] == 3                                   # the zero district is not producing


def test_crop_with_no_data_is_skipped_everywhere(prof, proot):
    for n in ("crop_profiles.csv", "crop_top_states.csv", "crop_state_yield_gaps.csv", "crop_top_districts.csv"):
        assert "Rice" not in set(rd(proot, n)["crop"])


# ----------------------------------------------------------------------------- crop_charts
@pytest.fixture
def charts(prof, proot, tmp_path):
    out = tmp_path / "svgs"
    g = run_script("analysis/crop_charts.py", proot, argv=[out], name="__main__")
    return out, g


def test_chart_files_are_written_and_wellformed(charts):
    out, _ = charts
    names = sorted(p.name for p in out.glob("*.svg"))
    assert names == ["card_cotton.svg", "card_rapeseed_mustard.svg", "card_wheat.svg", "concentration.svg",
                     "decomposition.svg", "volatility.svg", "yield_gap.svg"]
    for p in out.glob("*.svg"):
        root = ET.fromstring(p.read_text())
        assert root.tag.endswith("svg") and root.get("viewBox")


def test_chart_labels_use_short_names_and_formatting(charts):
    out, _ = charts
    dec = (out / "decomposition.svg").read_text()
    assert ">Mustard</text>" in dec and ">Rapeseed &amp; Mustard</text>" not in dec
    assert "Average annual change, 2003-06 to 2023-26" in dec
    vol = (out / "volatility.svg").read_text()
    assert "worst " in vol and "(2025-26)" in vol
    gap = (out / "yield_gap.svg").read_text()
    assert "J&amp;K" in gap and "national yield = 100%" in gap
    assert "Haryana 300%" in gap                                           # best_yield / national yield, rounded
    conc = (out / "concentration.svg").read_text()
    assert "Punjab alone 55%" in conc


def test_chart_colour_rule_for_concentration_threshold(charts):
    out, _ = charts
    conc = (out / "concentration.svg").read_text()
    # Wheat top3 share 2003-06 = 0.90 vs 2023-26 = 0.909: change < 0.02 -> muted grey
    assert 'stroke="#6c757d" stroke-width="2.5"' in conc


def test_sugarcane_style_units_and_card_contents(charts):
    out, _ = charts
    card = (out / "card_wheat.svg").read_text()
    assert "Index, 2003-06 average = 100" in card and "Largest producers, 2023-26: share · yield" in card
    assert "55% · 2,000 kg/ha" in card
    assert card.count("<polyline") == 3
    assert "— production" in card


def test_pct_helper_signs(charts):
    _, g = charts
    assert g["pct"](0.025) == "+2.5%" and g["pct"](-0.025) == "-2.5%"
    assert g["nm"]("Rapeseed & Mustard") == "Mustard" and g["nm"]("Wheat") == "Wheat"
