"""Crop-by-crop production and yield profiles from UPAG area-production-yield data.

    python analysis/crop_profiles.py

Writes reports/crop_profiles.csv (one row per crop), reports/crop_top_states.csv,
reports/crop_top_districts.csv and reports/crop_state_yield_gaps.csv.

Conventions: periods are three-crop-year averages so one drought or bumper year does not drive a
comparison ("2003-06" = 2003-04..2005-06, "2023-26" = 2023-24..2025-26, the latest being advance
estimates). Growth is split into area and yield with logs: ln(P1/P0) = ln(A1/A0) + ln(Y1/Y0).
"""
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
D, OUT = ROOT / "data", ROOT / "reports"
CROPS = ["Rice", "Wheat", "Maize", "Jowar", "Bajra", "Ragi", "Gram", "Tur", "Moong", "Urad", "Lentil",
         "Groundnut", "Rapeseed & Mustard", "Soybean", "Cotton", "Sugarcane"]
BALES = {"Cotton": 170}            # UPAG labels cotton production "Lakh Tonnes" but the figures are lakh bales of 170 kg


def years(lo, hi):
    return [f"{y}-{(y + 1) % 100:02d}" for y in range(lo, hi + 1)]


P0, P1 = years(2003, 2005), years(2023, 2025)


def load_india():
    a = pd.read_csv(D / "upag/apy_all_india.csv.gz")
    a = a[(a["Season"] == "Total") & a["Crop"].isin(CROPS)]
    a["Value"] = pd.to_numeric(a["Value"], errors="coerce")
    return a.pivot_table(index=["Crop", "Crop Year"], columns="Metric", values="Value", aggfunc="first").reset_index()


def load_state():
    a = pd.read_csv(D / "upag/apy_state.csv.gz", low_memory=False)
    a = a[(a["Season"] == "Total") & a["RecordType"].str.startswith("State") & a["Crop"].isin(CROPS)]
    a["Value"] = pd.to_numeric(a["Value"], errors="coerce")
    a["State"] = a["State"].replace({"Ladakh": "Jammu And Kashmir"})
    return a.pivot_table(index=["Crop", "State", "Crop Year"], columns="Metric", values="Value", aggfunc="sum").reset_index()


def load_district():
    a = pd.read_csv(D / "upag/apy_district.csv.gz", low_memory=False,
                    usecols=["State", "District", "Crop Year", "Season", "Crop", "Metric", "Value"])
    a = a[(a["Season"] == "Total") & a["Crop"].isin(CROPS) & (a["Metric"] == "Production")]
    a["Value"] = pd.to_numeric(a["Value"], errors="coerce")
    return a


def main():
    ind, st, di = load_india(), load_state(), load_district()
    if "Cotton" in BALES:     # sanity check of the bales reading: yield = bales x 170 kg / area
        c = ind[(ind["Crop"] == "Cotton")].dropna().tail(3)
        implied = (c["Production"] * BALES["Cotton"] / c["Area"]).round(0).tolist()
        print("cotton implied lint yield (kg/ha):", implied, "published:", c["Yield"].round(0).tolist())
    prof, tops, gaps, dtops = [], [], [], []
    for crop in CROPS:
        s = ind[ind["Crop"] == crop].set_index("Crop Year").sort_index()
        p0, p1 = s.loc[s.index.isin(P0)], s.loc[s.index.isin(P1)]
        if len(p0) < 3 or len(p1) < 3:
            continue
        A0, A1, Y0, Y1, Q0, Q1 = p0["Area"].mean(), p1["Area"].mean(), p0["Yield"].mean(), p1["Yield"].mean(), p0["Production"].mean(), p1["Production"].mean()
        lnP, lnA, lnY = np.log(Q1 / Q0), np.log(A1 / A0), np.log(Y1 / Y0)
        q = s["Production"].dropna()
        since = q[q.index >= "2000-01"]
        yoy = (since / since.shift(1) - 1).dropna()
        peak_year = q.idxmax()
        # states, latest three years
        sl = st[(st["Crop"] == crop) & st["Crop Year"].isin(P1)].groupby("State")[["Production", "Area"]].mean()
        so = st[(st["Crop"] == crop) & st["Crop Year"].isin(P0)].groupby("State")[["Production", "Area"]].mean()
        sl["share"] = sl["Production"] / sl["Production"].sum()
        sl["yield"] = sl["Production"] / sl["Area"] * (BALES.get(crop, 1000) if crop in BALES else 1000) * (1 if crop not in BALES else 1)
        if crop in BALES:
            sl["yield"] = sl["Production"] * BALES[crop] / sl["Area"]
        else:
            sl["yield"] = sl["Production"] / sl["Area"] * 1000          # lakh t / lakh ha -> kg/ha
        so["share"] = so["Production"] / so["Production"].sum()
        top = sl.sort_values("Production", ascending=False)
        for rank, (state, r) in enumerate(top.head(5).iterrows(), 1):
            tops.append({"crop": crop, "rank": rank, "state": state, "production": r["Production"], "share": r["share"],
                         "yield_kg_ha": r["yield"], "share_2003_06": so["share"].get(state, np.nan)})
        big = sl[sl["share"] >= 0.03]                                      # states with >= 3% of output
        nat_y = Y1
        best, worst = big["yield"].idxmax(), big["yield"].idxmin()
        gaps.append({"crop": crop, "national_yield": nat_y, "best_state": best, "best_yield": big.loc[best, "yield"],
                     "worst_state": worst, "worst_yield": big.loc[worst, "yield"], "states_compared": len(big)})
        # districts, latest three district years
        dd = di[(di["Crop"] == crop) & di["Crop Year"].isin(years(2022, 2024))].groupby(["State", "District"])["Value"].mean().sort_values(ascending=False)
        dshare = dd / dd.sum()
        for rank, ((state, dist), v) in enumerate(dd.head(5).items(), 1):
            dtops.append({"crop": crop, "rank": rank, "district": dist, "state": state, "production": v, "share": dshare[(state, dist)]})
        prof.append({
            "crop": crop, "unit": "lakh bales (170 kg)" if crop in BALES else "lakh tonnes",
            "production_2023_26": Q1, "production_2003_06": Q0, "area_lakh_ha_2023_26": A1, "area_lakh_ha_2003_06": A0,
            "yield_2023_26": Y1, "yield_2003_06": Y0,
            "production_growth_pa": np.exp(lnP / 20) - 1, "area_growth_pa": np.exp(lnA / 20) - 1, "yield_growth_pa": np.exp(lnY / 20) - 1,
            "yield_share_of_growth": lnY / lnP if lnP > 0 else np.nan,
            "typical_yoy_swing": yoy.abs().median(), "worst_yoy_fall": yoy.min(), "worst_fall_year": yoy.idxmin(),
            "record_year": peak_year, "record_production": q.max(), "latest_year": q.index.max(), "latest_production": q.iloc[-1],
            "top_state": top.index[0], "top_state_share": top["share"].iloc[0], "top3_share": top["share"].head(3).sum(),
            "top3_share_2003_06": so["share"].sort_values(ascending=False).head(3).sum(),
            "top10_district_share": dshare.head(10).sum(), "districts_producing": int((dd > 0).sum()),
        })
    pd.DataFrame(prof).to_csv(OUT / "crop_profiles.csv", index=False)
    pd.DataFrame(tops).to_csv(OUT / "crop_top_states.csv", index=False)
    pd.DataFrame(gaps).to_csv(OUT / "crop_state_yield_gaps.csv", index=False)
    pd.DataFrame(dtops).to_csv(OUT / "crop_top_districts.csv", index=False)
    print("wrote crop_profiles.csv,", len(prof), "crops")


if __name__ == "__main__":
    main()
