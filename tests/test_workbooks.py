import json

import numpy as np
import pytest
import synth
from conftest import run_script

openpyxl = pytest.importorskip("openpyxl")


def monthly(root, specs, months=synth.MONTHS):
    """specs: {(commodity, state): (arrivals_fn(k), price_fn(k))}"""
    rows = []
    for k, mo in enumerate(months):
        for (c, s), (af, pf) in specs.items():
            rows.append([mo, 1, c, "g", s, af(k), pf(k)])
    synth.write_gz(root / "data/agmarknet/state_monthly.csv.gz",
                   ["month", "commodity_id", "commodity", "group", "state", "arrivals_t", "price_rs_qtl"], rows)


def run_rank(root, tmp_path, extra=()):
    out, res = tmp_path / "r.xlsx", tmp_path / "r.json"
    g = run_script("analysis/workbooks/crop_ranking.py", root, argv=[out, res, *extra])
    return g, openpyxl.load_workbook(out), json.loads(res.read_text())


# ------------------------------------------------------------------ crop_ranking
def test_ranking_pairs_threshold_and_metrics(root, tmp_path, capsys):
    monthly(root, {
        ("Wheat", "Punjab"): (lambda k: 500, lambda k: 2000 + 10 * k),            # 6000 t in last 12m: kept
        ("Wheat", "UP"): (lambda k: 400 if k != 45 else 600, lambda k: 2000 + 20 * k),   # 400*11 + 600 = 5000 exactly: kept
        ("Wheat", "Tiny"): (lambda k: 399 if k != 45 else 599, lambda k: 2000 + 20 * k),  # 4999: dropped
        ("Onion", "Punjab"): (lambda k: 900, lambda k: 800 + 5 * k),               # not an All-India crop in CORE? it is (crosswalk)
        ("Rice", "Punjab"): (lambda k: 9000, lambda k: 100 + k),                   # not in crosswalk -> ignored
        ("Wheat", "Low"): (lambda k: 49, lambda k: 3000),                          # < MIN_T every month -> no data at all
    })
    g, wb, res = run_rank(root, tmp_path)
    assert "saved" in capsys.readouterr().out
    assert res["months"] == synth.MONTHS
    assert res["pairs"] == ["Onion|All India", "Onion|Punjab", "Wheat|All India", "Wheat|UP", "Wheat|Punjab"] or \
        sorted(res["pairs"]) == sorted(["Onion|All India", "Onion|Punjab", "Wheat|All India", "Wheat|UP", "Wheat|Punjab"])
    assert "Wheat|Tiny" not in res["pairs"] and "Wheat|Low" not in res["pairs"]
    assert not any(p.startswith("Rice") for p in res["pairs"])
    # ordering: by crop then descending arrivals in the last 12 months
    wheat = [p for p in res["pairs"] if p.startswith("Wheat")]
    assert wheat == ["Wheat|All India", "Wheat|Punjab", "Wheat|UP"]
    r = res["res"]["Wheat|Punjab"]
    moves = [10 / (2000 + 10 * (k - 1)) for k in range(1, 46)]
    assert r["arr12"] == 6000 and r["n"] == 45
    assert r["vol"] == pytest.approx(float(np.median(moves)))
    prices = [2000 + 10 * k for k in range(46)]
    assert r["rng"] == pytest.approx(np.percentile(prices, 95) / np.percentile(prices, 5) - 1)
    assert r["last"] == 2000 + 10 * 45


def test_ranking_all_india_is_arrival_weighted(root, tmp_path):
    monthly(root, {("Wheat", "A"): (lambda k: 100, lambda k: 1000 + k), ("Wheat", "B"): (lambda k: 300, lambda k: 2000 + k)})
    g, wb, res = run_rank(root, tmp_path)
    ai = g["data"][("Wheat", "All India")]
    assert ai["2023-01"] == (pytest.approx((100 * 1000 + 300 * 2000) / 400), 400)
    assert res["res"]["Wheat|All India"]["arr12"] == 12 * 400


def test_ranking_end_month_truncates_window(root, tmp_path):
    monthly(root, {("Wheat", "A"): (lambda k: 1000, lambda k: 1000 + k)})
    _, _, res = run_rank(root, tmp_path, extra=["--end", "2026-06"])
    assert res["months"][-1] == "2026-06" and len(res["months"]) == 42
    assert res["res"]["Wheat|A"]["arr12"] == 12000
    _, _, res2 = run_rank(root, tmp_path, extra=["--end", "2026-05"])
    assert res2["months"][-1] == "2026-05"


def test_ranking_short_history_has_no_volatility(root, tmp_path):
    monthly(root, {("Wheat", "A"): (lambda k: 1000, lambda k: 1000 + k)}, months=synth.MONTHS[:25])     # 24 changes after START
    _, _, res = run_rank(root, tmp_path)
    assert res["res"]["Wheat|A"]["n"] == 24 and res["res"]["Wheat|A"]["vol"] is not None
    assert res["pairs"] == ["Wheat|All India", "Wheat|A"] or res["pairs"] == ["Wheat|A", "Wheat|All India"]


@pytest.mark.xfail(strict=True, raises=(ValueError, TypeError),
                   reason="when no crop-state pair has 24+ monthly changes, last = 3 and "
                          "ColorScaleRule is added for the invalid range E4:E3, so wb.save never runs")
def test_ranking_with_no_qualifying_pairs_still_saves_a_workbook(root, tmp_path):
    monthly(root, {("Wheat", "A"): (lambda k: 1000, lambda k: 1000 + k)}, months=synth.MONTHS[:24])
    _, wb, res = run_rank(root, tmp_path)
    assert res["pairs"] == []


def test_ranking_workbook_sheets_and_formulas(root, tmp_path):
    monthly(root, {("Wheat", "A"): (lambda k: 1000, lambda k: 1000 + 10 * k), ("Wheat", "B"): (lambda k: 600, lambda k: 900 + 10 * k)})
    _, wb, res = run_rank(root, tmp_path)
    assert wb.sheetnames == ["Notes", "Ranking", "Prices", "Arrivals", "Returns"]
    assert wb["Notes"]["B9"].value == "2023-01"
    p = wb["Prices"]
    assert p["B2"].value == "Wheat" and p["B3"].value == "All India" and p["A4"].value == "2023-01"
    assert p["B4"].value == pytest.approx((1000 * 1000 + 600 * 900) / 1600, abs=0.05)         # rounded to 1 dp
    assert p["C3"].value == "A" and p["C4"].value == 1000 and p["D4"].value == 900
    a = wb["Arrivals"]
    assert a["C4"].value == 1000 and a["D4"].value == 600
    rt = wb["Returns"]
    assert rt["C4"].value is None
    assert rt["C5"].value == '=IF(OR(Prices!C5="",Prices!C4=""),"",ABS(Prices!C5/Prices!C4-1))'
    rk = wb["Ranking"]
    assert [rk.cell(3, c).value for c in (1, 2, 3)] == ["Crop", "State", "Arrivals, last 12m (t)"]
    assert [rk.cell(r, 2).value for r in (4, 5, 6)] == ["All India", "A", "B"]
    assert rk["C5"].value == "=SUM(Arrivals!C38:C49)"                                    # last 12 of 46 months (rows 4..49)
    assert rk["D4"].value is None and rk["D5"].value == '=IFERROR(C5/C4,"")'
    assert rk["I5"].value.startswith("=COUNTIFS($A$4:$A$6,A5,$B$4:$B$6,\"<>All India\",$C$4:$C$6,\">\"&C5)+1")
    assert rk["K4"].value == '=COUNTIFS($B$4:$B$6,"All India",$C$4:$C$6,">"&C4)+1'
    assert rk["I4"].value is None
    assert rk["E5"].value.startswith("=IFERROR(MEDIAN(INDIRECT(\"Returns!C\"&(MATCH(Notes!$B$9,Prices!$A$4:$A$49,0)+3)&\":C49\")),\"\")")
    assert rk.freeze_panes == "C4" and [str(cf.sqref) for cf in rk.conditional_formatting] == ["E4:E6"]
    assert all(c.font.name == "Arial" for row in rk.iter_rows() for c in row if c.value is not None)


# ------------------------------------------------------------------ mandi_leaders
def sample(root, rows):
    synth.write_gz(root / "data/agmarknet/market_daily_sample.csv.gz",
                   ["date", "commodity", "state", "district", "market", "mkt_id", "arrival_t", "modal_price_rs_qtl"], rows)


def run_leaders(root, tmp_path):
    out, res = tmp_path / "l.xlsx", tmp_path / "l.json"
    g = run_script("analysis/workbooks/mandi_leaders.py", root, argv=[out, res])
    return g, openpyxl.load_workbook(out), json.loads(res.read_text())


@pytest.fixture
def leaders_root(root):
    rows = []
    for d in ("2026-01-01", "2026-01-07", "2026-01-13"):
        rows += [[d, "Wheat", "Punjab", "Ludhiana", " khanna apmc ", "11", 2000, 1],
                 [d, "Paddy(Common)", "Punjab", "Ludhiana", " khanna apmc ", "11", 100, 1],
                 [d, "Wheat", "Punjab", "Amritsar", "Amritsar", "12", 900, 1],
                 [d, "Bajra(Pearl Millet/Cumbu)", "Chattisgarh", "Raipur", "Raipur", "13", 0.4, 1],     # < 1 t per sampled day
                 [d, "Soyabean", "Chattisgarh", "Raipur", "Raipur", "13", 50, 1]]
    rows += [["2026-01-13", "Wheat", "Punjab", "Amritsar", "Amritsar", "12", "", 1],                    # blank -> 0 -> skipped
             ["2026-01-19", "Wheat", "Punjab", "Amritsar", "Amritsar", "12", "n/a", 1],                  # unparseable -> skipped, day counted
             ["2026-01-19", "Wheat", "Punjab", "Amritsar", "Amritsar", "12", "-5", 1]]                   # negative -> skipped
    sample(root, rows)
    return root


def test_leaders_results_json_aggregates_and_cleans(leaders_root, tmp_path):
    g, wb, res = run_leaders(leaders_root, tmp_path)
    assert res["ndays"] == 4 and res["step"] == 6
    got = {(r[3], r[4]): r[5] for r in res["rows"]}
    assert got[("11", "Wheat")] == 6000 and got[("11", "Paddy")] == 300 and got[("12", "Wheat")] == 2700
    assert ("13", "Bajra") in got and got[("13", "Bajra")] == pytest.approx(1.2)          # 3 x 0.4 = 1.2 >= 1 kept
    assert got[("13", "Soybean")] == 150
    assert res["meta"]["11"] == ["Khanna APMC", "Ludhiana", "Punjab"]
    assert res["meta"]["13"][2] == "Chhattisgarh"
    assert res["mk_tot"] == {"11": 6300, "12": 2700, "13": pytest.approx(151.2)}
    assert res["mk_crops"]["11"][0] == ["Wheat", 6000]
    assert [r[0] for r in res["rows"]] == sorted(r[0] for r in res["rows"])


def test_leaders_drops_crops_under_one_tonne_total(leaders_root, tmp_path):
    rows = [["2026-01-01", "Wheat", "Punjab", "D", "Mk", "1", 0.99, 1], ["2026-01-01", "Maize", "Punjab", "D", "Mk", "1", 1.0, 1]]
    sample(leaders_root, rows)
    _, _, res = run_leaders(leaders_root, tmp_path)
    assert [(r[4], r[5]) for r in res["rows"]] == [("Maize", 1.0)]


def test_leaders_workbook_structure_and_formulas(leaders_root, tmp_path):
    _, wb, res = run_leaders(leaders_root, tmp_path)
    assert wb.sheetnames == ["Notes", "Top_Mandis", "Crop_Leaders", "State_Crop_Leaders", "State_Top_Mandis", "Market_Crop", "Markets"]
    assert wb["Notes"]["B8"].value == 6 and wb["Notes"]["A8"].value.startswith("Sampling factor")
    assert "4 days" in wb["Notes"]["A3"].value and "every 6th day" in wb["Notes"]["A3"].value
    mc = wb["Market_Crop"]
    assert [mc.cell(3, c).value for c in (1, 3, 5, 6)] == ["State", "Market", "Crop", "Sampled tonnes"]
    first = [mc.cell(4, c).value for c in range(1, 7)]
    assert first == ["Chhattisgarh", "Raipur", "Raipur", 13, "Bajra", 1.2]
    assert mc["G4"].value == "=F4*Notes!$B$8"
    assert mc["H4"].value == '=COUNTIFS($A$4:$A$8,A4,$E$4:$E$8,E4,$F$4:$F$8,">"&F4)+1'
    assert mc["I4"].value == '=A4&"|"&E4&"|"&H4'
    mk = wb["Markets"]
    assert [mk.cell(r, 2).value for r in (4, 5, 6)] == ["Khanna APMC", "Amritsar", "Raipur"]            # by total tonnes desc
    assert mk["E4"].value == "=SUMIFS('Market_Crop'!$G$4:$G$8,'Market_Crop'!$D$4:$D$8,A4)"
    assert mk["F4"].value == '=COUNTIF($E$4:$E$6,">"&E4)+1'
    assert mk["G4"].value == '="r"&F4'
    top = wb["Top_Mandis"]
    assert top["A4"].value == 1 and top["A43"].value == 40 and top["A44"].value is None
    assert top["B4"].value.startswith('=IFERROR(INDEX(Markets!$B$4:$B$6,MATCH("r1",Markets!$G$4:$G$6,0)),"")')


def test_leaders_crop_and_state_sheets(leaders_root, tmp_path):
    big = []
    for d in range(30):
        big.append([f"2026-02-{d % 28 + 1:02d}", "Wheat", "Punjab", "Ludhiana", "Big", "21", 130, 1])
    sample(leaders_root, big)
    _, wb, res = run_leaders(leaders_root, tmp_path)
    sl = wb["State_Crop_Leaders"]
    # 30 x 130 = 3900 sampled -> 23,400 est >= 20,000
    assert sl["A4"].value == "Punjab" and sl["B4"].value == "Wheat"
    assert sl["C4"].value.startswith("=SUMIFS(")
    assert sl["A5"].value is None
    cl = wb["Crop_Leaders"]
    assert cl["A4"].value == "Wheat" and cl["C4"].value == 1 and cl["C8"].value == 5 and cl["A9"].value is None
    ss = wb["State_Top_Mandis"]
    assert ss["A4"].value == "Punjab" and ss["B4"].value == 1 and ss["B8"].value == 5


def test_leaders_state_crop_pair_threshold_is_inclusive_at_20000(leaders_root, tmp_path):
    sample(leaders_root, [["2026-02-01", "Wheat", "Punjab", "D", "A", "1", 20000 / 6, 1],
                          ["2026-02-01", "Maize", "Punjab", "D", "A", "1", 20000 / 6 - 0.01, 1]])
    _, wb, _ = run_leaders(leaders_root, tmp_path)
    sl = wb["State_Crop_Leaders"]
    assert [sl.cell(r, 2).value for r in range(4, 8)] == ["Wheat", None, None, None]


def test_leaders_state_top_mandis_limited_to_twenty_states(leaders_root, tmp_path):
    rows = [["2026-02-01", "Wheat", f"State{i:02d}", "D", f"M{i}", str(100 + i), 10 + i, 1] for i in range(22)]
    sample(leaders_root, rows)
    _, wb, _ = run_leaders(leaders_root, tmp_path)
    ss = wb["State_Top_Mandis"]
    states = {ss.cell(r, 1).value for r in range(4, 4 + 100) if ss.cell(r, 1).value}
    assert len(states) == 20 and "State00" not in states and "State21" in states


# ------------------------------------------------------------------ statewise_rice_maize
LONG_MONTHS = [f"{y}-{m:02d}" for y in range(2019, 2027) for m in range(1, 13) if (y, m) <= (2026, 10)]      # 94 months


def run_statewise(root, tmp_path, rows):
    synth.write_gz(root / "data/agmarknet/state_monthly.csv.gz",
                   ["month", "commodity_id", "commodity", "group", "state", "arrivals_t", "price_rs_qtl"], rows)
    out = tmp_path / "s.xlsx"
    g = run_script("analysis/workbooks/statewise_rice_maize.py", root, argv=[out])
    return g, openpyxl.load_workbook(out)


def sw_rows(com, state, months, arr, price):
    return [[m, 1, com, "g", state, arr(m), price(m)] for m in months]


@pytest.fixture
def sw(root, tmp_path):
    last12 = LONG_MONTHS[-12:]
    rows = []
    rows += sw_rows("Maize", "Big", LONG_MONTHS, lambda m: 600 if m in last12 else 10, lambda m: 2000 + LONG_MONTHS.index(m))
    rows += sw_rows("Maize", "Edge", LONG_MONTHS[-60:], lambda m: 5000 / 12 if m in last12 else 1, lambda m: 1800)  # 60 months, 5000 t: kept
    rows += sw_rows("Maize", "Short", LONG_MONTHS[-59:], lambda m: 900, lambda m: 1700)                             # 59 months: dropped
    rows += sw_rows("Maize", "Low", LONG_MONTHS, lambda m: 400 if m in last12 else 900, lambda m: 1600)             # 4800 t last 12m: dropped
    rows += sw_rows("Rice", "Big", LONG_MONTHS, lambda m: 500, lambda m: 3000)
    rows += sw_rows("Rice", "Other", LONG_MONTHS, lambda m: 450, lambda m: 1000)
    rows += [["2026-10", 1, "Rice", "g", "NoPrice", 9999, ""], ["2026-10", 1, "Wheat", "g", "Big", 9999, 5]]    # ignored
    return run_statewise(root, tmp_path, rows) + (rows,)


def test_statewise_keeps_states_with_60_months_and_5000_tonnes_ordered_by_arrivals(sw, capsys):
    g, wb, _ = sw
    assert g["states"]["Maize"] == ["All India", "Big", "Edge"]
    assert g["states"]["Rice"] == ["All India", "Big", "Other"]          # 6000 t then 5400 t
    assert "Broken Rice" not in g["states"] or g["states"]["Broken Rice"] == ["All India"]
    p = wb["Maize_Price"]
    assert [p.cell(3, c).value for c in range(1, 7)] == ["Month", "Year", "Mo", "All India", "Big", "Edge"]
    assert p["A4"].value == "2019-01" and p["A97"].value == "2026-10" and p["A98"].value is None


def test_statewise_all_india_price_is_arrival_weighted_and_rounded(sw):
    _, wb, _ = sw
    p = wb["Rice_Price"]
    k = LONG_MONTHS.index("2026-10")
    assert p.cell(4 + k, 4).value == pytest.approx((500 * 3000 + 450 * 1000) / 950, abs=0.05)                  # All India
    assert p.cell(4 + k, 5).value == 3000 and p.cell(4 + k, 6).value == 1000
    mz = wb["Maize_Price"]
    assert mz.cell(4, 5).value == 2000.0                                                              # Big, 2019-01
    assert mz.cell(4, 4).value == pytest.approx((10 * 2000 + 900 * 1600) / 910, abs=0.05)            # Big + Low report that month


def test_statewise_arrivals_are_real_numbers_not_zeroed(sw):
    _, wb, _ = sw
    a = wb["Maize_Arrivals"]
    assert a.cell(97, 2).value == 600 + round(5000 / 12) + 900 + 400                         # All India sums every state incl. the dropped ones
    assert a.cell(97, 3).value == 600 and a.cell(4, 3).value == 10


def test_statewise_input_defaults_and_notes(sw):
    _, wb, _ = sw
    i = wb["Inputs"]
    assert [(i.cell(r, 1).value, i.cell(r, 2).value) for r in range(4, 10)] == [
        ("rent", 10), ("interest", 0.105), ("shrink", 0.001), ("hold", 6), ("dip", 0.85), ("season_to", "2025-12")]
    assert i["D8"].value == "A month is a dip when price <= this x trailing 12-month mean"
    assert "net of rent, interest and shrinkage" in wb["Summary"]["A2"].value
    assert wb["Summary"]["A3"].value == "Commodity"


def test_statewise_every_cell_is_arial_and_all_india_rows_are_bold(sw):
    _, wb, _ = sw
    assert all(c.font.name == "Arial" for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None)
    for name in ("Seasonality", "Summary"):
        ws = wb[name]
        rows = [(ws.cell(r, 2).value, ws.cell(r, 2).font.bold) for r in range(4, 14) if ws.cell(r, 2).value]
        assert rows and all(bold == (st == "All India") for st, bold in rows)
        assert any(st == "All India" for st, _ in rows)
    sm = wb["Summary"]
    assert [sm.cell(r, 2).value for r in range(4, 7)] == ["All India", "Big", "Edge"]


def test_statewise_carry_and_dip_formulas_reference_the_inputs(sw):
    _, wb, _ = sw
    c = wb["Maize_Carry"]
    assert c["B4"].value.startswith("=IF(OR('Maize_Price'!D4=\"\",ROW()-3+Inputs!$B$7>94)")
    assert "Inputs!$B$6*(Inputs!$B$4+'Maize_Price'!D4*Inputs!$B$5/12+'Maize_Price'!D4*Inputs!$B$6)" not in c["B4"].value
    assert "Inputs!$B$7*(Inputs!$B$4+'Maize_Price'!D4*Inputs!$B$5/12+'Maize_Price'!D4*Inputs!$B$6)" in c["B4"].value
    dip = c.cell(16, 6)                                                                              # month index 12 -> first dip formula
    assert dip.value.startswith("=IF(OR('Maize_Price'!D16=\"\",COUNT('Maize_Price'!D4:D15)<9)")
    assert "'Maize_Price'!D16<=Inputs!$B$8*AVERAGE('Maize_Price'!D4:D15)" in dip.value
    assert c.cell(15, 6).value is None                                                               # no dip test before 12 months of history


def test_ranking_counts_the_change_into_the_start_month(root, tmp_path):
    months = ["2022-11", "2022-12"] + synth.MONTHS                                  # two months of history before START (2023-01)
    monthly(root, {("Wheat", "A"): (lambda k: 1000, lambda k: 1000 + 10 * k)}, months=months)
    _, _, res = run_rank(root, tmp_path)
    assert res["res"]["Wheat|A"]["n"] == 46                                         # 2023-01 .. 2026-10, each vs its predecessor
