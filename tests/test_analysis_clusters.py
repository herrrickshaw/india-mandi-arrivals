import numpy as np
import pandas as pd
import pytest
import synth
from conftest import run_script


@pytest.fixture
def cl(tmp_path):
    return run_script("analysis/clusters.py", tmp_path / "proj", name="cl")


def make_state_apy(root, extra=()):
    rng = np.random.default_rng(0)
    archetypes = [{"Rice": 80, "Wheat": 5, "Cotton": 5}, {"Rice": 5, "Wheat": 80, "Maize": 5}, {"Cotton": 60, "Groundnut": 30, "Gram": 5}]
    rows = []
    for i in range(10):
        st = f"S{i}"
        mix = archetypes[i // 4 if i < 8 else 2]
        for crop, a in mix.items():
            for cy in ("2021-22", "2022-23", "2023-24", "2024-25"):                  # only the last three are used
                v = a * (1 + 0.02 * rng.random()) if cy != "2021-22" else 1e6
                rows.append([st, crop, cy, "Total", "State", "Area", v])
    for cy in ("2022-23", "2023-24", "2024-25"):
        rows += [["Jammu And Kashmir", "Wheat", cy, "Total", "State", "Area", 3.0], ["Ladakh", "Wheat", cy, "Total", "State", "Area", 3.0]]
        rows += [["Others", "Rice", cy, "Total", "State", "Area", 500.0]]
        rows += [["Tinyland", "Rice", cy, "Total", "State", "Area", 0.5]]                 # < 1 lakh ha of these crops
        rows += [["S0", "Sugarcane", cy, "Kharif", "State", "Area", 9999.0],               # decoy season
                 ["S0", "Sugarcane", cy, "Total", "All India", "Area", 9999.0],            # decoy record type
                 ["S0", "Rice", cy, "Total", "State", "Production", 9999.0],               # decoy metric
                 ["S0", "Kiwi", cy, "Total", "State", "Area", 9999.0]]                     # crop in no group
    rows += list(extra)
    synth.write_gz(root / "data/upag/apy_state.csv.gz", ["State", "Crop", "Crop Year", "Season", "RecordType", "Metric", "Value"], rows)


def make_vol(root, n=8, state="All India"):
    rows = []
    for i in range(n):
        rows.append([f"C{i}", state, 0.02 * (i + 1) ** 1.5, 0.1 * (i + 1) ** 2, 0.08 + 0.01 * i])
    rows.append(["Cx", "Punjab", 0.5, 0.5, 0.5])
    rows.append(["Cnan", "All India", None, 0.5, 0.5])
    synth.write_csv(root / "reports/volatility_seasonality.csv",
                    ["commodity", "state", "typical_monthly_move", "seasonal_spread", "peak_month_share"], rows)


# ------------------------------------------------------------------ numeric kernels
def test_kmeans_recovers_obvious_clusters_and_returns_best_inertia(cl):
    X = np.array([[0.0], [1.0], [10.0], [11.0], [20.0], [21.0]])
    lab, c, inertia = cl["kmeans"](X, 3)
    assert len(set(lab)) == 3 and lab[0] == lab[1] and lab[2] == lab[3] and lab[4] == lab[5]
    assert sorted(c.ravel()) == [0.5, 10.5, 20.5]
    assert inertia == pytest.approx(6 * 0.25)


def test_kmeans_is_deterministic(cl):
    X = np.random.default_rng(1).random((30, 2))
    a, b = cl["kmeans"](X, 4), cl["kmeans"](X, 4)
    assert (a[0] == b[0]).all() and np.allclose(a[1], b[1]) and a[2] == b[2]


def test_kmeans_k1_is_the_mean(cl):
    X = np.array([[1.0, 2.0], [3.0, 6.0]])
    lab, c, inertia = cl["kmeans"](X, 1)
    assert (lab == 0).all() and np.allclose(c, [[2.0, 4.0]]) and inertia == pytest.approx(2 + 8)


def test_silhouette_hand_computed(cl):
    X = np.array([[0.0], [1.0], [10.0], [11.0]])
    lab = np.array([0, 0, 1, 1])
    expect = np.mean([(10.5 - 1) / 10.5, (9.5 - 1) / 9.5, (9.5 - 1) / 9.5, (10.5 - 1) / 10.5])
    assert cl["silhouette"](X, lab) == pytest.approx(expect)


def test_silhouette_singleton_cluster_uses_zero_cohesion(cl):
    X = np.array([[0.0], [10.0], [11.0]])
    lab = np.array([0, 1, 1])
    s0 = (10.5 - 0) / 10.5                                      # a = 0 for the singleton -> s = 1
    s1 = (10.0 - 1) / 10.0
    s2 = (11.0 - 1) / 11.0
    assert cl["silhouette"](X, lab) == pytest.approx(np.mean([s0, s1, s2]))


def test_silhouette_coincident_points_score_zero(cl):
    X = np.array([[1.0], [1.0]])
    assert cl["silhouette"](X, np.array([0, 1])) == 0.0


# ------------------------------------------------------------------ state_mix
def test_state_mix_uses_last_three_years_and_filters(tmp_path):
    root = tmp_path / "p"
    make_state_apy(root)
    cl = run_script("analysis/clusters.py", root, name="cl")
    shares, total, years = cl["state_mix"]()
    assert years == ["2022-23", "2023-24", "2024-25"]
    assert "Others" not in shares.index and "Tinyland" not in shares.index
    assert "Ladakh" not in shares.index and "Jammu And Kashmir" in shares.index
    assert shares.loc["Jammu And Kashmir", "Wheat"] == pytest.approx(1.0)
    assert total["Jammu And Kashmir"] == pytest.approx(6.0)             # (3 + 3) lakh ha per year, averaged over 3 years
    assert (shares.sum(axis=1).round(9) == 1.0).all()
    assert "Sugarcane" not in shares.columns and "Kiwi" not in shares.columns
    assert shares.loc["S0", "Rice"] > 0.8 and shares.loc["S0", "Rice"] < 1.0


def test_state_mix_drops_states_just_under_one_lakh_ha(tmp_path):
    root = tmp_path / "p"
    make_state_apy(root, extra=[["Edge", "Rice", cy, "Total", "State", "Area", 1.0] for cy in ("2022-23", "2023-24", "2024-25")]
                   + [["Under", "Rice", cy, "Total", "State", "Area", 0.99] for cy in ("2022-23", "2023-24", "2024-25")])
    cl = run_script("analysis/clusters.py", root, name="cl")
    shares, total, _ = cl["state_mix"]()
    assert "Edge" in shares.index and "Under" not in shares.index


# ------------------------------------------------------------------ main
@pytest.fixture
def ran(tmp_path, capsys):
    root = tmp_path / "p"
    make_state_apy(root)
    make_vol(root)
    g = run_script("analysis/clusters.py", root, name="cl")
    res, scores = g["main"]()
    return root, res, scores, capsys.readouterr().out


def test_main_clusters_sorted_by_size_and_files_written(ran):
    root, res, scores, out = ran
    sizes = res["cluster"].value_counts().sort_index()
    assert list(sizes.index) == [1, 2, 3, 4, 5][:len(sizes)] and list(sizes) == sorted(sizes, reverse=True)
    saved = pd.read_csv(root / "reports/state_crop_clusters.csv")
    assert list(saved.columns[:3]) == ["State", "cluster", "area_lakh_ha"]
    assert len(saved) == len(res) == 11                                 # S0..S9 + Jammu And Kashmir
    cen = pd.read_csv(root / "reports/state_cluster_centroids.csv")
    assert list(cen["cluster"]) == [1, 2, 3, 4, 5]


def test_main_best_silhouette_is_the_true_cluster_count(ran):
    _, _, scores, out = ran
    assert sorted(scores) == [3, 4, 5, 6, 7, 8]
    assert max(scores, key=scores.get) == 4                            # three archetypes + the pure-wheat J&K row
    assert out.startswith("crop years: ['2022-23', '2023-24', '2024-25'] silhouette by k: {3: ")


def test_main_archetype_states_share_a_cluster(tmp_path):
    root = tmp_path / "p"
    make_state_apy(root)
    make_vol(root)
    res, _ = run_script("analysis/clusters.py", root, name="cl")["main"](k=4)
    c = res["cluster"]
    assert c["S0"] == c["S1"] == c["S2"] == c["S3"]
    assert c["S4"] == c["S5"] == c["S6"] == c["S7"]
    assert c["S8"] == c["S9"]
    assert len({c["S0"], c["S4"], c["S8"], c["Jammu And Kashmir"]}) == 4


def test_main_writes_price_clusters_for_all_india_rows_only(ran):
    root, *_ = ran
    pc = pd.read_csv(root / "reports/crop_price_clusters.csv")
    assert len(pc) == 8 and set(pc["state"]) == {"All India"}          # NaN row and Punjab row dropped
    assert set(pc["price_cluster"]) <= {1, 2, 3, 4}


def test_main_skips_price_clusters_with_fewer_than_six_rows(tmp_path):
    root = tmp_path / "p"
    make_state_apy(root)
    make_vol(root, n=5)
    g = run_script("analysis/clusters.py", root, name="cl")
    g["main"]()
    assert not (root / "reports/crop_price_clusters.csv").exists()
    make_vol(root, n=6)
    g = run_script("analysis/clusters.py", root, name="cl")
    g["main"]()
    assert (root / "reports/crop_price_clusters.csv").exists()


def test_main_k_parameter_controls_centroid_rows(tmp_path):
    root = tmp_path / "p"
    make_state_apy(root)
    make_vol(root)
    g = run_script("analysis/clusters.py", root, name="cl")
    res, _ = g["main"](k=3)
    assert set(res["cluster"]) == {1, 2, 3}
    assert len(pd.read_csv(root / "reports/state_cluster_centroids.csv")) == 3


def test_script_entry_point_runs_main(tmp_path):
    root = tmp_path / "p"
    make_state_apy(root)
    make_vol(root)
    run_script("analysis/clusters.py", root, name="__main__")
    assert (root / "reports/state_crop_clusters.csv").exists()
