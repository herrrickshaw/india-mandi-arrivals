import json
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import pytest
import synth
from conftest import run_script

AI_CROPS = ["Rice", "Wheat", "Maize", "Gram", "Tur", "Soybean", "Rapeseed & Mustard", "Groundnut", "Cotton", "Total Food Grains", "Cereals"]
STATES = ["Punjab", "Haryana", "Bihar", "Jammu And Kashmir"]
def _cross2d_removed():
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            np.cross(np.array([1.0, 2.0]), np.array([3.0, 4.0]))
        return False
    except ValueError:
        return True


NUMPY2 = _cross2d_removed()   # 2-D np.cross: deprecated in NumPy 2.0, an error in newer releases (probed, not version-guessed)
MAP_CROPS = ["Rice", "Wheat", "Maize", "Total Pulses", "Total Oil Seeds", "Cotton"]


def square(x0, y0, size=4.0):
    return [[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]]


def geojson(path):
    feats = [
        {"properties": {"ST_NM": "Punjab"}, "geometry": {"type": "Polygon", "coordinates": [square(74, 30)]}},
        {"properties": {"ST_NM": "Haryana"}, "geometry": {"type": "MultiPolygon", "coordinates": [[square(76, 28)], [square(78, 28, 1.0)]]}},
        {"properties": {"ST_NM": "Bihar"}, "geometry": {"type": "Polygon", "coordinates": [square(84, 25)]}},
        {"properties": {"ST_NM": "Jammu & Kashmir"}, "geometry": {"type": "Polygon", "coordinates": [square(74, 33)]}},
        {"properties": {"ST_NM": "Andaman & Nicobar Island"}, "geometry": {"type": "Polygon", "coordinates": [square(92, 10)]}},
        {"properties": {"ST_NM": "Lakshadweep"}, "geometry": {"type": "Polygon", "coordinates": [square(72, 10)]}},
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


def area_val(ci, y):
    slope = [0.5, 2.0, -1.0][ci % 3]
    return 200.0 + ci * 10 + slope * (y - 1966)


def build(tmp_path):
    root = synth.build_root(tmp_path / "proj")
    ai = []
    for ci, crop in enumerate(AI_CROPS):
        for y in range(1966, 2026):
            cy = f"{y}-{(y + 1) % 100:02d}"
            ai += [[crop, cy, "Total", "Area", area_val(ci, y)], [crop, cy, "Total", "Yield", 800.0 + ci * 50 + (y - 1966) * 20]]
    synth.write_gz(root / "data/upag/apy_all_india.csv.gz", ["Crop", "Crop Year", "Season", "Metric", "Value"], ai)
    st = []
    for crop in MAP_CROPS + ["Total Food Grains"]:
        for cy in synth.crop_years(2023, 2025):
            for i, s in enumerate(STATES + ["Ladakh"]):
                st += [[s, crop, cy, "Total", "State", "Production", 10.0 * (i + 1) + (3 if s == "Ladakh" else 0)],
                       [s, crop, cy, "Total", "State", "Yield", 2000.0 + 500 * i]]
    synth.write_gz(root / "data/upag/apy_state.csv.gz", ["State", "Crop", "Crop Year", "Season", "RecordType", "Metric", "Value"], st)
    cl = [[s, 1 + i % 2] + [0.1 * (i + 1), 0.9 - 0.1 * (i + 1)] for i, s in enumerate(STATES)]
    synth.write_csv(root / "reports/state_crop_clusters.csv", ["State", "cluster", "Rice", "Wheat"], cl)
    synth.write_csv(root / "reports/state_cluster_centroids.csv", ["cluster", "Rice", "Wheat"], [[1, 0.2, 0.8], [2, 0.7, 0.3]])
    names = ["Wheat", "Onion", "Tomato", "Paddy(Common)", "Maize", "Potato", "Garlic", "Mystery Crop"]
    pc, vs = [], []
    for i, n in enumerate(names):
        pc.append([n, "All India", 1 + i // 2, 0.02 * (i + 1) ** 1.3, 0.1 * (i + 1) ** 1.6, 0.08 + 0.02 * (i % 2)])
        vs.append([n, "All India", 100000 * (i + 1), 1000 + i, 0.02 * (i + 1), 0.1 * (i + 1), 1 + i % 12, 12 - i % 12])
    synth.write_csv(root / "reports/crop_price_clusters.csv",
                    ["commodity", "state", "price_cluster", "typical_monthly_move", "seasonal_spread", "peak_month_share"], pc)
    synth.write_csv(root / "reports/volatility_seasonality.csv",
                    ["commodity", "state", "arrivals_last12m_t", "median_price_last12m", "typical_monthly_move", "seasonal_spread",
                     "cheapest_month", "dearest_month"], vs)
    synth.write_csv(root / "data/external/urea_state_2025_26.csv", ["state", "urea_sales_lmt", "urea_kg_per_ha"],
                    [["Punjab", 25.0, 250.0], ["Haryana", 20.0, 200.0], ["Bihar", 18.0, 150.0], ["Jammu And Kashmir", 2.0, 50.0], ["Nowhere", 1.0, 10.0]])
    return root


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("post")
    root = build(tmp)
    geo = geojson(tmp / "states.geojson")
    out = tmp / "out"
    g = run_script("analysis/post_charts.py", root, argv=[geo, out])
    return root, out, g


def test_all_svgs_are_wellformed_xml(ran):
    _, out, _ = ran
    names = sorted(p.name for p in out.glob("*.svg"))
    assert names == ["area.svg", "cluster_map.svg", "maps.svg", "price_clusters.svg", "season_heat.svg", "urea_yield.svg", "yields.svg"]
    for p in out.glob("*.svg"):
        t = ET.fromstring(p.read_text())
        assert t.tag.endswith("svg")


def test_area_chart_labels_and_change_colouring(ran):
    _, out, g = ran
    svg = (out / "area.svg").read_text()
    assert g["LAST"] == 2025 and g["LASTLAB"] == "2025-26"
    assert "Area 2025-26, lakh hectares (change vs 2015-16)" in svg
    assert "Cereals" not in svg and "Total Food Grains" not in svg            # aggregates are dropped
    up = AI_CROPS.index("Maize")                                                # ci=2 -> slope -1.0 (falling)
    gain = AI_CROPS.index("Wheat")                                              # ci=1 -> slope 2.0 (rising)
    flat = AI_CROPS.index("Rice")                                               # ci=0 -> slope 0.5
    ch = lambda ci: area_val(ci, 2025) / area_val(ci, 2015) - 1
    assert ch(gain) > 0.05 and ch(up) < -0.05 and abs(ch(flat)) < 0.05
    assert f'{area_val(gain, 2025):,.0f}<tspan fill="#2b8a3e" dx="8">+{ch(gain) * 100:.0f}%</tspan>' in svg
    assert f'{area_val(up, 2025):,.0f}<tspan fill="#c92a2a" dx="8">−{abs(ch(up)) * 100:.0f}%</tspan>' in svg
    assert f'{area_val(flat, 2025):,.0f}<tspan fill="#6c757d" dx="8">+{ch(flat) * 100:.0f}%</tspan>' in svg


def test_yield_small_multiples_has_nine_panels(ran):
    _, out, _ = ran
    svg = (out / "yields.svg").read_text()
    assert svg.count("<polyline") == 9 and "Mustard</text>" in svg
    assert "2025-26: " in svg and " kg/ha" in svg


def test_maps_have_one_path_per_state_and_skip_islands(ran):
    _, out, g = ran
    paths = g["paths"]
    assert sorted(paths) == ["Bihar", "Haryana", "Jammu And Kashmir", "Punjab"]       # NAME mapping applied; islands skipped
    svg = (out / "maps.svg").read_text()
    assert svg.count("<path ") == 6 * 4
    assert "Top: " in svg and "Ladakh" not in svg
    assert "share of national production: low" in svg


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Ladakh is renamed to Jammu And Kashmir and the two rows are then averaged with .mean() "
                          "instead of summed, so the merged state's share is understated (crop_profiles.py sums them)")
def test_ladakh_production_is_summed_into_jammu_and_kashmir_share(ran):
    _, out, _ = ran
    svg = (out / "maps.svg").read_text()
    jk = 40 + 53                                           # J&K 40 + Ladakh 53, every year
    tot = 10 + 20 + 30 + jk
    assert f"Jammu And Kashmir {jk / tot * 100:.0f}%" in svg


def test_ramp_clamps_and_interpolates(ran):
    _, _, g = ran
    assert g["ramp"](0) == "#f7fcf5" and g["ramp"](1) == "#005a32"
    assert g["ramp"](-5) == g["ramp"](0) and g["ramp"](7) == g["ramp"](1)
    assert g["ramp"](0.5) == "#%02x%02x%02x" % (round((247 + 0) / 2), round((252 + 90) / 2), round((245 + 50) / 2))


def test_douglas_peucker_short_inputs_are_returned_unchanged(ran):
    _, _, g = ran
    assert g["dp"]([(0, 0), (1, 1)], 0.5) == [(0, 0), (1, 1)]
    assert g["dp"]([], 0.5) == []


@pytest.mark.xfail(NUMPY2, strict=True, raises=ValueError,
                   reason="np.cross on 2-D vectors raises on recent NumPy (deprecated since 2.0); requirements.txt allows numpy>=1.24")
def test_douglas_peucker_keeps_corners_and_drops_collinear_points(ran):
    _, _, g = ran
    line = [(0, 0), (1, 0.01), (2, 0), (3, 0)]
    assert g["dp"](line, 0.5) == [(0, 0), (3, 0)]
    kinked = [(0, 0), (1, 5), (2, 0)]
    assert g["dp"](kinked, 0.5) == [(0, 0), (1, 5), (2, 0)]


def test_rings_handles_polygon_and_multipolygon(ran):
    _, _, g = ran
    poly = {"type": "Polygon", "coordinates": [[[0, 0]], [[9, 9]]]}
    multi = {"type": "MultiPolygon", "coordinates": [[[[1, 1]]], [[[2, 2]]]]}
    assert g["rings"](poly) == [[[0, 0]]]
    assert g["rings"](multi) == [[[1, 1]], [[2, 2]]]


def test_mappaths_thins_close_points_and_closes_rings(ran):
    _, _, g = ran
    p = g["mappaths"](200, 200, eps=0.9)
    for d in p.values():
        assert d.startswith("M") and d.endswith("Z")
    big_eps = g["mappaths"](200, 200, eps=500)
    assert all(v == "" for v in big_eps.values())          # everything thinned below 3 points -> no ring survives


def test_cluster_map_legend_and_colours(ran):
    _, out, _ = ran
    svg = (out / "cluster_map.svg").read_text()
    assert "Cluster 1" in svg and "Cluster 2" in svg
    assert "wheat 80%" in svg and "rice 70%" in svg
    assert 'fill="#1c6e8c"' in svg and 'fill="#74c0fc"' in svg
    assert "Jammu &amp; Kashmir" in svg


def test_price_cluster_legend_names_and_meta_json(ran):
    root, out, g = ran
    svg = (out / "price_clusters.svg").read_text()
    for name in ("very volatile perishables", "volatile vegetables", "steady, traded year-round", "harvest-bunched field crops"):
        assert name in svg
    meta = json.loads((out / "price_cluster_meta.json").read_text())
    assert sorted(meta["pcc"]) == ["1", "2", "3", "4"] and len(meta["stats"]) == 4
    assert sum(s["n"] for s in meta["stats"]) == 8
    # cluster 4 has the largest typical monthly moves -> most volatile -> red
    assert meta["pname"]["4"] == "very volatile perishables" and meta["pcc"]["4"] == "#c92a2a"
    assert meta["pname"]["3"] == "volatile vegetables" and meta["pcc"]["3"] == "#e8590c"
    assert "Mystery Crop" not in svg and "Paddy" in svg and ">Wheat</text>" in svg


def test_season_heat_and_median_prices(ran):
    root, out, _ = ran
    svg = (out / "season_heat.svg").read_text()
    assert "Jan" in svg and "Dec" in svg and "cheaper than the crop's average month" in svg
    med = pd.read_csv(out / "median_prices.csv")
    assert list(med.columns) == ["commodity", "median_price_last12m", "typical_monthly_move", "seasonal_spread",
                                 "cheapest_month", "dearest_month", "arrivals_last12m_t"]
    assert set(med["commodity"]) == {"Wheat", "Onion", "Paddy"}                  # CORE crops only, short names
    assert list(med["arrivals_last12m_t"]) == sorted(med["arrivals_last12m_t"], reverse=True)


def test_colr_is_white_at_one_and_saturates_at_plus_minus_twenty_percent(ran):
    _, _, g = ran
    assert g["colr"](1.0) == ("#ffffff", False)
    assert g["colr"](1.2) == ("#c92a2a", True) and g["colr"](5) == g["colr"](1.2)
    assert g["colr"](0.8) == ("#2b8a3e", True) and g["colr"](0.1) == g["colr"](0.8)
    assert g["colr"](1.11)[1] is True and g["colr"](1.10)[1] is False         # dark-text switch just above t = .55


def test_urea_scatter_correlation_and_csv(ran):
    root, out, _ = ran
    u = pd.read_csv(out / "urea_vs_yield.csv")
    assert list(u["state"]) == ["Punjab", "Haryana", "Bihar", "Jammu And Kashmir", "Nowhere"]
    assert u.loc[u["state"] == "Punjab", "fg_yield"].iloc[0] == 2000.0
    assert u.loc[u["state"] == "Haryana", "grain_t_per_t_urea"].iloc[0] == pytest.approx(20.0 / 20.0)
    assert pd.isna(u.loc[u["state"] == "Nowhere", "fg_yield"].iloc[0])
    svg = (out / "urea_yield.svg").read_text()
    assert "Urea per hectare of cropped land, 2025-26 (kg)" in svg and "Food-grain yield 2025-26 (kg/ha)" in svg
    assert u.loc[u["state"] == "Bihar", "cluster"].iloc[0] == 1 and u.loc[u["state"] == "Punjab", "cluster"].iloc[0] == 1


def test_crowded_labels_fall_back_to_offset_positions_with_leader_lines(tmp_path):
    root = build(tmp_path)
    labels = ["Wheat", "Onion", "Tomato", "Maize", "Potato", "Garlic", "Rice", "Cotton", "Banana", "Mango"]
    pc = [[n, "All India", 1 + i % 4, 0.1, 0.5, 0.1] for i, n in enumerate(labels)]
    synth.write_csv(root / "reports/crop_price_clusters.csv",
                    ["commodity", "state", "price_cluster", "typical_monthly_move", "seasonal_spread", "peak_month_share"], pc)
    names = [f"State{i}" for i in range(10)]
    synth.write_csv(root / "data/external/urea_state_2025_26.csv", ["state", "urea_sales_lmt", "urea_kg_per_ha"],
                    [[n, 5.0, 100.0 + (i % 2) * 0.01] for i, n in enumerate(names)])
    st = [[n, "Total Food Grains", cy, "Total", "State", m, 2500.0] for n in names for cy in synth.crop_years(2023, 2025)
          for m in ("Yield", "Production")]
    old = pd.read_csv(root / "data/upag/apy_state.csv.gz")
    new = pd.concat([old, pd.DataFrame(st, columns=old.columns)])
    new.to_csv(root / "data/upag/apy_state.csv.gz", index=False)
    long_states = ["Andhra Pradesh", "Arunachal Pradesh", "Himachal Pradesh", "Madhya Pradesh", "Uttar Pradesh", "West Bengal and more"]
    synth.write_csv(root / "reports/state_crop_clusters.csv", ["State", "cluster", "Rice", "Wheat"],
                    [[n, 1, 0.5, 0.5] for n in long_states] + [["Punjab", 2, 0.1, 0.9]])
    out = tmp_path / "out2"
    run_script("analysis/post_charts.py", root, argv=[geojson(tmp_path / "g.json"), out])
    for name in ("price_clusters.svg", "urea_yield.svg"):
        svg = (out / name).read_text()
        ET.fromstring(svg)
        assert 'stroke-width="0.8"' in svg                    # leader line drawn for a label moved far from its point
    cm = (out / "cluster_map.svg").read_text()
    member_lines = [l for l in cm.splitlines() if 'font-size="11" fill="#6c757d"' in l and "Pradesh" in l]
    assert len(member_lines) >= 2                              # the member list wraps at ~46 characters
    assert all(len(ET.fromstring(l).text) <= 46 + 20 for l in member_lines)


# ----------------------------------------------------------------------------- geometry / mapping assertions
def _svg_els(path, tag):
    return [e for e in ET.fromstring(path.read_text()).iter() if e.tag.endswith("}" + tag)]


def test_yield_panels_show_yield_values_scaled_to_108_percent_of_the_series_max(ran):
    _, out, _ = ran
    svg = (out / "yields.svg").read_text()
    rice_yield_2025 = 800.0 + 0 * 50 + (2025 - 1966) * 20                      # ci=0 -> Rice, the first panel
    assert f"2025-26: {rice_yield_2025:,.0f} kg/ha" in svg                     # Yield rows, not Area rows
    first = _svg_els(out / "yields.svg", "polyline")[0]
    ys = [float(p.split(",")[1]) for p in first.get("points").split()]
    y0, y1 = 26, 140 - 20                                                      # first panel: cy = 0
    assert min(ys) == pytest.approx(y1 - (y1 - y0) / 1.08, abs=0.06)           # series max sits at 1/1.08 of the plot height
    assert max(ys) == pytest.approx(y1 - (800.0 / (rice_yield_2025 * 1.08)) * (y1 - y0), abs=0.06)


def test_mappaths_projection_is_equirectangular_with_cos_22_longitude_scaling(ran):
    import math
    _, _, g = ran
    w, h, pad = 200, 200, 6
    p = g["mappaths"](w, h, pad=pad, eps=0.0)
    k = math.cos(math.radians(22))
    lon0, lon1, lat0, lat1 = 74.0, 88.0, 25.0, 37.0                            # extent of the non-island test states
    s = min((w - 2 * pad) / ((lon1 - lon0) * k), (h - 2 * pad) / (lat1 - lat0))
    ox = pad + ((w - 2 * pad) - (lon1 - lon0) * k * s) / 2
    first = p["Bihar"].split("L")[0]                                          # Bihar square starts at lon 84, lat 25
    x, y = (float(v) for v in first[1:].split(","))
    assert x == pytest.approx((84 - lon0) * k * s + ox, abs=0.06)
    assert y == pytest.approx((lat1 - 25) * s + pad, abs=0.06)


def test_price_cluster_legend_is_two_columns_300px_apart(ran):
    _, out, _ = ran
    names = ("very volatile perishables", "volatile vegetables", "steady, traded year-round", "harvest-bunched field crops")
    texts = [e for e in _svg_els(out / "price_clusters.svg", "text") if e.text in names]
    xs = sorted({float(e.get("x")) for e in texts})
    ys = sorted({float(e.get("y")) for e in texts})
    assert len(xs) == 2 and xs[1] - xs[0] == 300
    assert len(ys) == 2 and ys[1] - ys[0] == 18


def test_season_heat_cells_sit_in_their_calendar_month_column(ran):
    _, out, g = ran
    a2 = g["a2"]
    cells = [e for e in _svg_els(out / "season_heat.svg", "text") if e.get("font-size") == "10.5"]
    got = {(float(e.get("x")), float(e.get("y"))): e.text for e in cells}
    assert got
    for i, c in enumerate(g["keep"]):
        sub = a2[a2["commodity"] == c]
        idx = sub.groupby("mo")["p"].mean() / sub["p"].mean()
        y = 40 + i * 22 + 14
        for mo, val in idx.items():
            assert got[(96 + (mo - 1) * 46 + 46 / 2 - 1, y)] == f"{val:.2f}"
