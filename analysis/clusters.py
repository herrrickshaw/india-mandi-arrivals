"""K-means clustering of states by crop-area mix and of crops by price behaviour (numpy only).

    python analysis/clusters.py

Writes reports/state_crop_clusters.csv, reports/state_cluster_centroids.csv, reports/crop_price_clusters.csv.
States are described by the share of their cropped area (latest three crop years, all seasons) under
each crop group; crops by their typical monthly price move, seasonal spread and how concentrated
their arrivals are in the peak month (from reports/volatility_seasonality.csv, all-India rows).
"""
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
D, OUT = ROOT / "data", ROOT / "reports"

GROUPS = {"Rice": ["Rice"], "Wheat": ["Wheat"], "Maize": ["Maize"], "Millets & sorghum": ["Jowar", "Bajra", "Ragi", "Small Millets", "Barley"],
          "Pulses": ["Gram", "Tur", "Moong", "Urad", "Lentil", "Other Pulses"],
          "Oilseeds": ["Groundnut", "Rapeseed & Mustard", "Soybean", "Sunflower", "Sesamum", "Castorseed", "Linseed", "Nigerseed", "Safflower"],
          "Cotton": ["Cotton"], "Sugarcane": ["Sugarcane"], "Jute & fibres": ["Jute", "Mesta", "Sannhemp"]}


def kmeans(X, k, seeds=50, iters=200):
    """Lloyd's k-means with k-means++ starts; returns (labels, centres, inertia) of the best of `seeds` runs."""
    best = None
    for s in range(seeds):
        rng = np.random.default_rng(s)
        c = [X[rng.integers(len(X))]]
        for _ in range(1, k):
            d2 = np.min(((X[:, None, :] - np.array(c)[None]) ** 2).sum(-1), axis=1)
            c.append(X[rng.choice(len(X), p=d2 / d2.sum())])
        c = np.array(c)
        for _ in range(iters):
            lab = ((X[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
            new = np.array([X[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(k)])
            if np.allclose(new, c):
                break
            c = new
        inertia = ((X - c[lab]) ** 2).sum()
        if best is None or inertia < best[2]:
            best = (lab, c, inertia)
    return best


def silhouette(X, lab):
    d = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1)); s = []
    for i in range(len(X)):
        same = lab == lab[i]
        a = d[i, same & (np.arange(len(X)) != i)].mean() if same.sum() > 1 else 0
        b = min(d[i, lab == j].mean() for j in set(lab) if j != lab[i])
        s.append((b - a) / max(a, b) if max(a, b) > 0 else 0)
    return float(np.mean(s))


def state_mix():
    a = pd.read_csv(D / "upag/apy_state.csv.gz", low_memory=False)
    a = a[(a["Season"] == "Total") & a["RecordType"].str.startswith("State") & (a["Metric"] == "Area")]
    a["Value"] = pd.to_numeric(a["Value"], errors="coerce")
    years = sorted(a["Crop Year"].unique())[-3:]
    a = a[a["Crop Year"].isin(years)]
    a["State"] = a["State"].replace({"Ladakh": "Jammu And Kashmir"})
    inv = {c: g for g, cs in GROUPS.items() for c in cs}
    a["group"] = a["Crop"].map(inv)
    a = a.dropna(subset=["group"])
    t = a.groupby(["State", "group"])["Value"].sum().unstack(fill_value=0) / len(years)
    t = t[(t.sum(axis=1) >= 1.0) & (t.index != "Others")]                       # at least 1 lakh ha of these crops: drops tiny UTs
    return t.div(t.sum(axis=1), axis=0), t.sum(axis=1), years


def main(k=5):
    shares, total, years = state_mix()
    X = shares.values
    scores = {kk: silhouette(X, kmeans(X, kk)[0]) for kk in range(3, 9)}
    lab, cen, _ = kmeans(X, k)
    order = np.argsort(-np.bincount(lab, minlength=k))                # cluster 1 = largest
    remap = {old: new + 1 for new, old in enumerate(order)}
    res = shares.copy(); res.insert(0, "cluster", [remap[l] for l in lab]); res.insert(1, "area_lakh_ha", total)
    res.reset_index().to_csv(OUT / "state_crop_clusters.csv", index=False)
    cdf = pd.DataFrame(cen, columns=shares.columns); cdf.insert(0, "cluster", [remap[i] for i in range(k)])
    cdf.sort_values("cluster").to_csv(OUT / "state_cluster_centroids.csv", index=False)
    print("crop years:", years, "silhouette by k:", {kk: round(v, 3) for kk, v in scores.items()})

    v = pd.read_csv(OUT / "volatility_seasonality.csv")
    v = v[v["state"] == "All India"].dropna(subset=["typical_monthly_move", "seasonal_spread", "peak_month_share"])
    if len(v) >= 6:
        F = v[["typical_monthly_move", "seasonal_spread", "peak_month_share"]].values
        Z = (np.log(F) - np.log(F).mean(0)) / np.log(F).std(0)
        l2, _, _ = kmeans(Z, 4)
        v = v.assign(price_cluster=l2 + 1)
        v.to_csv(OUT / "crop_price_clusters.csv", index=False)
    return res, scores


if __name__ == "__main__":
    main()
