"""Join Agmarknet and UPAG extracts into insight tables under reports/.

    python analysis/build_insights.py

Outputs (CSV + reports/INSIGHTS.md):
  arrivals_share_of_production.csv  mandi arrivals / UPAG production, state x crop x crop year (Jul-Jun)
  mandi_vs_msp.csv                   monthly state mandi price vs MSP for the matching marketing year
  volatility_seasonality.csv         typical monthly price move, cheapest/dearest month, peak arrival months
  yield_trends.csv                   all-India and state yield growth by crop
  area_by_crop.csv                   all-India area by crop, latest year vs 10 years earlier
  top_mandis.csv                     estimated annual arrivals by mandi (sampled days x step)
"""
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
D, OUT = ROOT / "data", ROOT / "reports"
OUT.mkdir(exist_ok=True)
MIN_T = 50          # state-months with fewer tonnes are dropped as unreliable
VOL_FROM = "2023-01"

cw = pd.read_csv(ROOT / "crosswalks/commodity_crosswalk.csv")
st = dict(pd.read_csv(ROOT / "crosswalks/state_crosswalk.csv").values)


def load_monthly():
    m = pd.read_csv(D / "agmarknet/state_monthly.csv.gz")
    m["arrivals_t"] = pd.to_numeric(m["arrivals_t"], errors="coerce")
    m["price_rs_qtl"] = pd.to_numeric(m["price_rs_qtl"], errors="coerce")
    m["upag_state"] = m["state"].map(st).fillna(m["state"])
    m["date"] = pd.to_datetime(m["month"] + "-01")
    # All-India rows: arrival-weighted mean of reliable state prices, summed arrivals
    ok = m[(m["arrivals_t"] >= MIN_T) & m["price_rs_qtl"].notna()].copy()
    ok["pa"] = ok["price_rs_qtl"] * ok["arrivals_t"]
    ai = ok.groupby(["month", "date", "commodity"], as_index=False).agg(pa=("pa", "sum"), arrivals_t=("arrivals_t", "sum"))
    ai["price_rs_qtl"] = ai["pa"] / ai["arrivals_t"]
    ai = ai.drop(columns="pa").assign(state="All India", upag_state="All India")
    return pd.concat([m, ai], ignore_index=True)


def apy_state():
    a = pd.read_csv(D / "upag/apy_state.csv.gz", low_memory=False)
    a = a[(a["Season"] == "Total") & (a["RecordType"].str.startswith("State"))]
    a["Value"] = pd.to_numeric(a["Value"], errors="coerce")
    return a.pivot_table(index=["State", "Crop", "Crop Year"], columns="Metric", values="Value", aggfunc="first").reset_index()


def arrivals_share(m, a):
    x = m.merge(cw[cw["arrival_to_production_factor"].notna()][["agmarknet_commodity", "upag_apy_crop", "arrival_to_production_factor"]],
                left_on="commodity", right_on="agmarknet_commodity")
    x = x[(x["arrivals_t"] >= MIN_T) & (x["state"] != "All India")]
    x["crop_year"] = np.where(x["date"].dt.month >= 7, x["date"].dt.year, x["date"].dt.year - 1)
    x["crop_year"] = x["crop_year"].astype(str) + "-" + ((x["crop_year"] + 1) % 100).astype(str).str.zfill(2)
    x["arr_eq_t"] = x["arrivals_t"] * x["arrival_to_production_factor"]
    g = x.groupby(["upag_state", "upag_apy_crop", "crop_year"], as_index=False).agg(arrivals_t=("arr_eq_t", "sum"), months=("month", "nunique"))
    g = g[g["months"] >= 10]                                    # full crop years only
    j = g.merge(a, left_on=["upag_state", "upag_apy_crop", "crop_year"], right_on=["State", "Crop", "Crop Year"])
    j["production_t"] = j["Production"] * 1e5                   # Lakh Tonnes -> tonnes
    j["arrivals_share_of_production"] = j["arrivals_t"] / j["production_t"]
    j = j[j["production_t"] > 0][["upag_state", "upag_apy_crop", "crop_year", "arrivals_t", "production_t", "arrivals_share_of_production", "months"]]
    j.columns = ["state", "crop", "crop_year", "arrivals_t", "production_t", "arrivals_share_of_production", "months_reported"]
    j.to_csv(OUT / "arrivals_share_of_production.csv", index=False)
    return j


def mandi_vs_msp(m):
    msp = pd.read_csv(D / "upag/msp.csv.gz")
    msp = msp[msp["Metric"] == "MSP"][["Crop", "Year", "Value"]].rename(columns={"Value": "msp_rs_qtl"})
    x = m.merge(cw[cw["upag_msp_crop"].notna()][["agmarknet_commodity", "upag_msp_crop", "msp_season"]],
                left_on="commodity", right_on="agmarknet_commodity")
    x = x[(x["arrivals_t"] >= MIN_T) & x["price_rs_qtl"].notna()]
    start = np.where(x["msp_season"] == "Kharif", 10, 4)       # kharif marketing year Oct-Sep, rabi Apr-Mar
    y = np.where(x["date"].dt.month >= start, x["date"].dt.year, x["date"].dt.year - 1)
    x["msp_year"] = pd.Series(y, index=x.index).astype(str) + "-" + pd.Series((y + 1) % 100, index=x.index).astype(str).str.zfill(2)
    x = x.merge(msp, left_on=["upag_msp_crop", "msp_year"], right_on=["Crop", "Year"])
    x["msp_rs_qtl"] = pd.to_numeric(x["msp_rs_qtl"], errors="coerce")
    x["price_vs_msp"] = x["price_rs_qtl"] / x["msp_rs_qtl"] - 1
    x["below_msp"] = x["price_vs_msp"] < 0
    x = x[["month", "commodity", "state", "arrivals_t", "price_rs_qtl", "msp_year", "msp_rs_qtl", "price_vs_msp", "below_msp"]]
    x.to_csv(OUT / "mandi_vs_msp.csv", index=False)
    return x


def vol_season(m):
    x = m[(m["arrivals_t"] >= MIN_T) & m["price_rs_qtl"].notna()].sort_values(["commodity", "state", "date"])
    rows = []
    for (c, s), g in x.groupby(["commodity", "state"]):
        g = g.set_index("date")
        p = g["price_rs_qtl"]
        prev = p.shift(1); gap = (g.index.to_series().diff().dt.days <= 31)
        r = (p / prev - 1)[gap & (g.index >= pd.Timestamp(VOL_FROM + "-01"))].abs().dropna()
        full = g[g.index.year <= 2025]
        if len(r) < 24 or full.empty:
            continue
        si = full.groupby(full.index.month)["price_rs_qtl"].mean() / full["price_rs_qtl"].mean()
        ar = full.groupby(full.index.month)["arrivals_t"].sum(); ar = ar / ar.sum()
        last12 = g[g.index > g.index.max() - pd.DateOffset(months=12)]
        rows.append({"commodity": c, "state": s, "arrivals_last12m_t": last12["arrivals_t"].sum(),
                     "median_price_last12m": last12["price_rs_qtl"].median(),
                     "typical_monthly_move": r.median(), "months_counted": len(r),
                     "cheapest_month": int(si.idxmin()), "dearest_month": int(si.idxmax()),
                     "seasonal_spread": si.max() / si.min() - 1,
                     "peak_arrival_month": int(ar.idxmax()), "peak_month_share": ar.max()})
    v = pd.DataFrame(rows)
    v.to_csv(OUT / "volatility_seasonality.csv", index=False)
    return v


def yields():
    a = pd.read_csv(D / "upag/apy_all_india.csv.gz")
    a = a[(a["Season"] == "Total") & (a["Metric"] == "Yield")]
    a["Value"] = pd.to_numeric(a["Value"], errors="coerce"); a["y0"] = a["Crop Year"].str[:4].astype(int)
    out = []
    for c, g in a.groupby("Crop"):
        g = g.dropna(subset=["Value"]).set_index("y0")["Value"].sort_index()
        last = int(g.index.max())

        def avg3(y, centred=True):                   # 3-year means damp one-off drought / bumper years
            ys = [y - 1, y, y + 1] if centred else [y - 2, y - 1, y]
            v = g.reindex(ys).dropna()
            return v.mean() if len(v) == 3 else None

        def cagr(y0, y1):
            a, b = avg3(y0), avg3(y1, centred=(y1 != last))
            mid1 = y1 - 1 if y1 == last else y1
            if a and b:
                return (b / a) ** (1 / (mid1 - y0)) - 1
        out.append({"crop": c, "latest_year": last, "latest_yield_kg_ha": g[last],
                    "cagr_2000_latest": cagr(2000, last), "cagr_2015_latest": cagr(2015, last), "cagr_1970_2000": cagr(1970, 2000)})
    y = pd.DataFrame(out); y.to_csv(OUT / "yield_trends.csv", index=False)
    return y


def area():
    a = pd.read_csv(D / "upag/apy_all_india.csv.gz")
    a = a[(a["Season"] == "Total") & (a["Metric"] == "Area")]
    a["Value"] = pd.to_numeric(a["Value"], errors="coerce"); a["y0"] = a["Crop Year"].str[:4].astype(int)
    last = a["y0"].max()
    p = a.pivot_table(index="Crop", columns="y0", values="Value", aggfunc="first")
    r = pd.DataFrame({"area_lakh_ha_latest": p[last], "area_lakh_ha_10y_before": p.get(last - 10), "latest_year": last})
    r["change_10y"] = r["area_lakh_ha_latest"] / r["area_lakh_ha_10y_before"] - 1
    r = r.sort_values("area_lakh_ha_latest", ascending=False).reset_index()
    r.to_csv(OUT / "area_by_crop.csv", index=False)
    return r


def top_mandis(step=6):
    s = pd.read_csv(D / "agmarknet/market_daily_sample.csv.gz")
    s["arrival_t"] = pd.to_numeric(s["arrival_t"], errors="coerce")
    g = s.groupby(["state", "district", "market"], as_index=False).agg(sampled_t=("arrival_t", "sum"), crops=("commodity", "nunique"))
    g["est_annual_t"] = g["sampled_t"] * step
    top = s.groupby(["state", "district", "market", "commodity"], as_index=False)["arrival_t"].sum()
    lead = top.sort_values("arrival_t", ascending=False).groupby(["state", "district", "market"]).head(1)
    g = g.merge(lead.rename(columns={"commodity": "main_crop", "arrival_t": "main_crop_sampled_t"}), on=["state", "district", "market"])
    g["main_crop_share"] = g["main_crop_sampled_t"] / g["sampled_t"]
    g = g.sort_values("est_annual_t", ascending=False)
    g.to_csv(OUT / "top_mandis.csv", index=False)
    return g


def pct(x):
    return f"{x * 100:.1f}%"


if __name__ == "__main__":
    m = load_monthly(); a = apy_state()
    sh = arrivals_share(m, a); ms = mandi_vs_msp(m); v = vol_season(m); y = yields(); ar = area(); tm = top_mandis()
    L = ["# Insights", "", "Generated by `analysis/build_insights.py` from the extracts in `data/`. Figures are this repository's calculations.", ""]
    recent = sh[sh["crop_year"] == sh["crop_year"].max()]
    L += [f"## Mandi arrivals as a share of production (crop year {sh['crop_year'].max()})", "",
          "How much of a state's output passes through regulated mandis (Agmarknet arrivals / UPAG production). Above 100% usually means grain arriving from other states or double counting at terminal markets.", "",
          "| State | Crop | Arrivals (t) | Production (t) | Share |", "|---|---|---|---|---|"]
    for _, r in recent.sort_values("production_t", ascending=False).head(25).iterrows():
        L.append(f"| {r.state} | {r.crop} | {r.arrivals_t:,.0f} | {r.production_t:,.0f} | {pct(r.arrivals_share_of_production)} |")
    last2 = ms[ms["month"] >= (pd.Timestamp(ms["month"].max() + "-01") - pd.DateOffset(months=23)).strftime("%Y-%m")]
    b = last2.groupby("commodity").agg(state_months=("below_msp", "size"), below=("below_msp", "mean"), median_gap=("price_vs_msp", "median")).sort_values("below", ascending=False)
    L += ["", "## Mandi prices against MSP, last 24 months", "", "Share of state-months in which the state's mandi price was below that year's MSP.", "",
          "| Commodity | State-months | Below MSP | Median price vs MSP |", "|---|---|---|---|"]
    for c, r in b.iterrows():
        L.append(f"| {c} | {int(r.state_months)} | {pct(r.below)} | {pct(r.median_gap)} |")
    vi = v[v["state"].isin(["All India"]) | True].sort_values("arrivals_last12m_t", ascending=False)
    L += ["", "## Most and least volatile large markets (typical monthly price move since 2023)", "", "| Commodity | State | Arrivals, last 12m (t) | Typical monthly move | Cheapest month | Dearest month |", "|---|---|---|---|---|---|"]
    big = v[v["arrivals_last12m_t"] >= 100000]
    for _, r in pd.concat([big.nlargest(10, "typical_monthly_move"), big.nsmallest(10, "typical_monthly_move")]).iterrows():
        L.append(f"| {r.commodity} | {r.state} | {r.arrivals_last12m_t:,.0f} | {pct(r.typical_monthly_move)} | {r.cheapest_month} | {r.dearest_month} |")
    L += ["", "## Yield growth (all-India, compound annual)", "", "Growth between three-year averages centred on each start year and the latest three years, so a single drought or bumper year does not drive the rate.", "",
          "| Crop | Latest yield (kg/ha) | 1970-2000 | 2000-latest | 2015-latest |", "|---|---|---|---|---|"]
    for _, r in y.dropna(subset=["cagr_2000_latest"]).sort_values("cagr_2015_latest", ascending=False).iterrows():
        f = lambda z: pct(z) if pd.notna(z) else "–"
        L.append(f"| {r.crop} | {r.latest_yield_kg_ha:,.0f} | {f(r.cagr_1970_2000)} | {f(r.cagr_2000_latest)} | {f(r.cagr_2015_latest)} |")
    L += ["", f"## Area by crop (all-India, {int(ar['latest_year'].iloc[0])} vs 10 years earlier)", "", "| Crop | Area (lakh ha) | 10 years earlier | Change |", "|---|---|---|---|"]
    for _, r in ar.head(20).iterrows():
        L.append(f"| {r.Crop} | {r.area_lakh_ha_latest:,.1f} | {r.area_lakh_ha_10y_before:,.1f} | {pct(r.change_10y) if pd.notna(r.change_10y) else '–'} |")
    L += ["", "## Largest mandis (estimated annual arrivals, 23 field crops)", "", "| Market | District | State | Est. tonnes | Main crop | Main crop share |", "|---|---|---|---|---|---|"]
    for _, r in tm.head(25).iterrows():
        L.append(f"| {r.market} | {r.district} | {r.state} | {r.est_annual_t:,.0f} | {r.main_crop} | {pct(r.main_crop_share)} |")
    (OUT / "INSIGHTS.md").write_text("\n".join(L) + "\n")
    print("wrote reports/:", sorted(p.name for p in OUT.iterdir()))
