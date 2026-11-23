"""Tiny synthetic project tree (crosswalks + data/) used to run the analysis scripts offline."""
import csv
import gzip
import pathlib

START_MONTHS = [(y, m) for y in range(2023, 2027) for m in range(1, 13) if (y, m) <= (2026, 10)]
MONTHS = [f"{y}-{m:02d}" for y, m in START_MONTHS]          # 46 months, 2023-01 .. 2026-10

COMMODITY_XW = [
    # agmarknet_id, commodity, upag_apy_crop, upag_msp_crop, upag_wpi_crop, msp_season, factor, note
    ("1", "Wheat", "Wheat", "Wheat", "Wheat", "Rabi", "1", ""),
    ("2", "Paddy(Common)", "Rice", "Paddy Common", "Paddy", "Kharif", "0.67", "milled"),
    ("23", "Onion", "", "", "", "", "", ""),
]
STATE_XW = [("Punjab", "Punjab"), ("UP", "Uttar Pradesh"), ("Andaman and Nicobar", "Andaman And Nicobar Islands")]


def crop_years(lo, hi):
    return [f"{y}-{(y + 1) % 100:02d}" for y in range(lo, hi + 1)]


def write_gz(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def price(commodity, state, k):
    base = {"Wheat": 2000.0, "Paddy(Common)": 1500.0, "Onion": 800.0}[commodity] + (100.0 if state == "UP" else 0.0)
    return base + 10.0 * k


def arrivals(commodity, state, k):
    if state == "Andaman and Nicobar":
        return 10.0                                   # below MIN_T (50): must be treated as unreliable
    return {"Wheat": 100.0, "Paddy(Common)": 200.0, "Onion": 300.0}[commodity] + (50.0 if state == "UP" else 0.0)


def build_root(root):
    root = pathlib.Path(root)
    write_csv(root / "crosswalks/commodity_crosswalk.csv",
              ["agmarknet_id", "agmarknet_commodity", "upag_apy_crop", "upag_msp_crop", "upag_wpi_crop",
               "msp_season", "arrival_to_production_factor", "note"], COMMODITY_XW)
    write_csv(root / "crosswalks/state_crosswalk.csv", ["agmarknet_state", "upag_state"], STATE_XW)
    rows = []
    for k, mo in enumerate(MONTHS):
        for c in ("Wheat", "Paddy(Common)", "Onion"):
            for s in ("Punjab", "UP", "Andaman and Nicobar"):
                rows.append([mo, {"Wheat": 1, "Paddy(Common)": 2, "Onion": 23}[c], c, "grp", s,
                             arrivals(c, s, k), price(c, s, k)])
    rows.append(["2026-10", "", "Wheat", "grp", "Punjab", "", ""])          # blank numerics -> NaN
    write_gz(root / "data/agmarknet/state_monthly.csv.gz",
             ["month", "commodity_id", "commodity", "group", "state", "arrivals_t", "price_rs_qtl"], rows)
    # UPAG state APY (Total season, State records) + decoys that must be filtered out
    apy = []
    for st in ("Punjab", "Uttar Pradesh"):
        for crop in ("Wheat", "Rice"):
            for cy in crop_years(2023, 2025):
                apy += [[st, crop, cy, "Total", "State", "Production", 0.5 if st == "Punjab" else 0.25],
                        [st, crop, cy, "Total", "State", "Area", 0.1],
                        [st, crop, cy, "Total", "State", "Yield", 5000]]
    apy.append(["Punjab", "Wheat", "2023-24", "Kharif", "State", "Production", 999])        # wrong season
    apy.append(["Punjab", "Wheat", "2023-24", "Total", "All India", "Production", 888])     # wrong record type
    write_gz(root / "data/upag/apy_state.csv.gz", ["State", "Crop", "Crop Year", "Season", "RecordType", "Metric", "Value"], apy)
    # MSP: kharif marketing year Oct-Sep, rabi Apr-Mar
    msp = [["MSP", "Wheat", "2022-23", 2000], ["MSP", "Wheat", "2023-24", 2100], ["MSP", "Wheat", "2024-25", 2200],
           ["MSP", "Wheat", "2025-26", 2300], ["MSP", "Wheat", "2026-27", 2400],
           ["MSP", "Paddy Common", "2022-23", 2500], ["MSP", "Paddy Common", "2023-24", 2600],
           ["MSP", "Paddy Common", "2024-25", 2700], ["MSP", "Paddy Common", "2025-26", 2800], ["MSP", "Paddy Common", "2026-27", 2900],
           ["Cost", "Wheat", "2023-24", 1]]
    write_gz(root / "data/upag/msp.csv.gz", ["Metric", "Crop", "Year", "Value"], msp)
    # All-India APY
    ai = []
    for crop, area0, yld0 in (("Wheat", 300.0, 2000.0), ("Rice", 400.0, 2500.0)):
        for y in range(1966, 2026):
            cy = f"{y}-{(y + 1) % 100:02d}"
            ai += [[crop, cy, "Total", "Yield", yld0 + 10 * (y - 2000)],
                   [crop, cy, "Total", "Area", area0 + (y - 2000)]]
    ai.append(["Wheat", "2025-26", "Kharif", "Yield", 1])
    write_gz(root / "data/upag/apy_all_india.csv.gz", ["Crop", "Crop Year", "Season", "Metric", "Value"], ai)
    # market sample
    ms = []
    for d in ("2026-01-01", "2026-01-07"):
        for mk, mid, dist, st, comm, a in (("m1 apmc", "11", "D1", "Punjab", "Wheat", 100.0),
                                           ("m1 apmc", "11", "D1", "Punjab", "Onion", 20.0),
                                           ("m2", "12", "D2", "Punjab", "Wheat", 50.0),
                                           ("m3", "13", "D3", "UP", "Paddy(Common)", 70.0)):
            ms.append([d, comm, st, dist, mk, mid, a, 1000])
    ms.append(["2026-01-07", "Wheat", "Punjab", "D1", "m1 apmc", "11", "", 1000])          # blank arrival
    write_gz(root / "data/agmarknet/market_daily_sample.csv.gz",
             ["date", "commodity", "state", "district", "market", "mkt_id", "arrival_t", "modal_price_rs_qtl"], ms)
    (root / "reports").mkdir(exist_ok=True)
    return root


# ---------------------------------------------------------------------------------- crop profiles
PROFILE_CROPS = {
    # crop: (area(y), yield(y), production(y)) as functions of the start year y
    "Wheat": (lambda y: 100 + (y - 2000), lambda y: 2000 + 10 * (y - 2000), lambda y: 100 + 5 * (y - 2000)),
    "Cotton": (lambda y: 120, lambda y: 500, lambda y: 300 - 2 * (y - 2000)),
    "Rapeseed & Mustard": (lambda y: 80, lambda y: 1000, lambda y: 80),
}
P1_STATES = {"Punjab": (60, 30), "Haryana": (30, 10), "Bihar": (8, 5), "Goa": (2, 0.5),
             "Jammu And Kashmir": (5, 5), "Ladakh": (5, 5)}           # (production, area) per crop year
P0_STATES = {"Punjab": 50, "Haryana": 20, "Bihar": 20, "Uttar Pradesh": 10}
DISTRICTS = {("Punjab", "Ludhiana"): 10, ("Punjab", "Amritsar"): 6, ("Haryana", "Karnal"): 4, ("Haryana", "Zeroland"): 0}


def build_profiles_root(root):
    root = pathlib.Path(root)
    ai = []
    for crop, (A, Y, P) in PROFILE_CROPS.items():
        for y in range(2000, 2026):
            cy = f"{y}-{(y + 1) % 100:02d}"
            ai += [[crop, cy, "Total", "Area", A(y)], [crop, cy, "Total", "Yield", Y(y)], [crop, cy, "Total", "Production", P(y)]]
    ai.append(["Wheat", "2025-26", "Kharif", "Production", 12345])
    ai += [["Maize", cy, "Total", m, 1] for cy in ("2003-04", "2004-05") for m in ("Area", "Yield", "Production")]   # < 3 years: skipped
    write_gz(root / "data/upag/apy_all_india.csv.gz", ["Crop", "Crop Year", "Season", "Metric", "Value"], ai)
    st = []
    for crop in PROFILE_CROPS:
        for cy in crop_years(2023, 2025):
            for s, (p, a) in P1_STATES.items():
                st += [[s, crop, cy, "Total", "State", "Production", p], [s, crop, cy, "Total", "State", "Area", a]]
        for cy in crop_years(2003, 2005):
            for s, p in P0_STATES.items():
                st += [[s, crop, cy, "Total", "State", "Production", p], [s, crop, cy, "Total", "State", "Area", 25]]
        st.append(["Punjab", crop, "2023-24", "Kharif", "State", "Production", 999])
        st.append(["Punjab", crop, "2023-24", "Total", "All India", "Production", 999])
    write_gz(root / "data/upag/apy_state.csv.gz", ["State", "Crop", "Crop Year", "Season", "RecordType", "Metric", "Value"], st)
    di = []
    for crop in PROFILE_CROPS:
        for cy in crop_years(2022, 2024):
            for (s, d), v in DISTRICTS.items():
                di += [[s, d, cy, "Total", crop, "Production", v]]
        di.append(["Punjab", "Ludhiana", "2021-22", "Total", crop, "Production", 10000])
        di.append(["Punjab", "Ludhiana", "2023-24", "Kharif", crop, "Production", 10000])
        di.append(["Punjab", "Ludhiana", "2023-24", "Total", crop, "Area", 10000])
    write_gz(root / "data/upag/apy_district.csv.gz", ["State", "District", "Crop Year", "Season", "Crop", "Metric", "Value"], di)
    (root / "reports").mkdir(exist_ok=True)
    return root
