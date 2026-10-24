"""Mandi leaders workbook from sampled Agmarknet market-level arrivals.

Usage: python analysis/workbooks/mandi_leaders.py <out.xlsx> <results.json>
Reads data/agmarknet/market_daily_sample.csv.gz (every 6th day, 23 field crops).
Market_Crop holds sampled tonnes per mandi and crop (data). Estimated annual tonnes, ranks and every
leader table are formulas over it, so changing the sampling factor on Notes rescales everything.
"""
import csv, gzip, pathlib, sys, json, collections
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter as L

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT, RES = sys.argv[1:3]
SRC = ROOT / "data/agmarknet/market_daily_sample.csv.gz"
F = "Arial"; BLUE = Font(name=F, color="0000FF"); BLACK = Font(name=F); BOLD = Font(name=F, bold=True)
H1 = Font(name=F, bold=True, size=13); HDR = Font(name=F, bold=True, color="FFFFFF"); HFILL = PatternFill("solid", fgColor="1F4E78")
RS = '#,##0;(#,##0);-'; PCT = '0.0%;(0.0%);-'
SHORT = {"Paddy(Common)": "Paddy", "Bajra(Pearl Millet/Cumbu)": "Bajra", "Jowar(Sorghum)": "Jowar", "Ragi(Finger Millet)": "Ragi",
         "Bengal Gram(Gram)(Whole)": "Chana", "Red gram/Arhar/Tur(whole)": "Tur", "Green Gram(Moong)(Whole)": "Moong",
         "Black Gram(Urd Beans)(Whole)": "Urad", "Lentil(Masur)(Whole)": "Masur", "Soyabean": "Soybean", "Dry Chillies": "Dry chilli",
         "Cummin Seed(Jeera)": "Jeera"}
NICE = {"Chattisgarh": "Chhattisgarh", "NCT of Delhi": "Delhi", "Keralam": "Kerala", "Pondicherry": "Puducherry"}

days = set(); agg = collections.defaultdict(float); meta = {}
for r in csv.DictReader(gzip.open(SRC, "rt", encoding="utf-8")):
    days.add(r["date"])
    try: a = float(r["arrival_t"] or 0)
    except ValueError: continue
    if a <= 0: continue
    key = (r["mkt_id"], SHORT.get(r["commodity"], r["commodity"]))
    agg[key] += a
    meta[r["mkt_id"]] = (r["market"].strip().title().replace("Apmc", "APMC"), r["district"], NICE.get(r["state"], r["state"]))
ND = len(days); STEP = 6
rows = sorted([(meta[m][2], meta[m][1], meta[m][0], m, c, t) for (m, c), t in agg.items() if t >= 1], key=lambda x: (x[0], x[4], -x[5]))
# Python cross-check / chart data
mk_tot = collections.defaultdict(float); mk_crops = collections.defaultdict(list)
for st, di, mk, mid, c, t in rows:
    mk_tot[mid] += t; mk_crops[mid].append((c, t))
json.dump({"ndays": ND, "step": STEP, "rows": rows, "meta": meta,
           "mk_tot": mk_tot, "mk_crops": {k: sorted(v, key=lambda x: -x[1]) for k, v in mk_crops.items()}}, open(RES, "w"))

wb = Workbook()
def hdr(ws, r, vals, c0=1):
    for i, v in enumerate(vals):
        c = ws.cell(r, c0 + i, v); c.font = HDR; c.fill = HFILL; c.alignment = Alignment(wrap_text=True, vertical="center")

ws = wb.active; ws.title = "Notes"
ws["A1"] = "Mandi leaders: which markets move the most of 23 crops, nationally and state by state (Agmarknet)"; ws["A1"].font = H1
notes = [f"Source: Agmarknet dashboard API, market-level daily report (market_details_sp), reported markets only, for 23 crops. Sampled every {STEP}th day from 1 Nov 2025 to 23 Oct 2026: {ND} days, rotating through the weekdays.",
         "Estimated annual tonnes = tonnes on sampled days x the sampling factor below. Rankings depend only on the sampled tonnes, so the factor scales the totals but does not change any rank.",
         "Volumes add different crops by weight (a tonne of tomato counts the same as a tonne of wheat). Arrivals are what each market reports to Agmarknet; markets that report irregularly are understated.",
         "Agmarknet widened its market coverage from Nov 2025, which is inside this window, so totals are not comparable with older Agmarknet figures."]
for i, t in enumerate(notes):
    c = ws.cell(3 + i, 1, t); c.font = BLACK; c.alignment = Alignment(wrap_text=True)
ws.column_dimensions["A"].width = 130
ws.cell(8, 1, "Sampling factor (days per sampled day):").font = BOLD
c = ws.cell(8, 2, STEP); c.font = BLUE; ws.column_dimensions["B"].width = 10
FAC = "Notes!$B$8"

# ---- Market_Crop data + formulas
mc = wb.create_sheet("Market_Crop")
mc["A1"] = "Tonnes per mandi and crop on sampled days (data), with estimated annual tonnes and ranks (formulas)"; mc["A1"].font = H1
hdr(mc, 3, ["State", "District", "Market", "Market id", "Crop", "Sampled tonnes", "Est. annual tonnes", "Rank in state for crop",
            "Key state|crop|rank", "Rank in India for crop", "Key crop|rank", "State crop total (t, est.)", "Share of state crop"])
n = len(rows); R0 = 4; RN = R0 + n - 1
A = lambda col: f"${col}${R0}:${col}${RN}"
for i, (st, di, mk, mid, c, t) in enumerate(rows):
    r = R0 + i
    for j, v in enumerate((st, di, mk, int(mid) if str(mid).isdigit() else mid, c)): mc.cell(r, 1 + j, v).font = BLACK
    x = mc.cell(r, 6, round(t, 2)); x.font = BLUE; x.number_format = RS
    mc.cell(r, 7, f"=F{r}*{FAC}").number_format = RS
    mc.cell(r, 8, f"=COUNTIFS({A('A')},A{r},{A('E')},E{r},{A('F')},\">\"&F{r})+1")
    mc.cell(r, 9, f"=A{r}&\"|\"&E{r}&\"|\"&H{r}")
    mc.cell(r, 10, f"=COUNTIFS({A('E')},E{r},{A('F')},\">\"&F{r})+1")
    mc.cell(r, 11, f"=E{r}&\"|\"&J{r}")
    mc.cell(r, 12, f"=SUMIFS({A('G')},{A('A')},A{r},{A('E')},E{r})").number_format = RS
    mc.cell(r, 13, f"=IFERROR(G{r}/L{r},\"\")").number_format = PCT
mc.freeze_panes = "A4"
for col, w in zip("ABCDEFGHIJKLM", (16, 16, 26, 9, 11, 11, 12, 9, 26, 9, 16, 12, 9)): mc.column_dimensions[col].width = w

# ---- Markets: one row per mandi, total across crops (formulas), national and state ranks
mids = sorted(mk_tot, key=lambda m: -mk_tot[m])
mt = wb.create_sheet("Markets")
mt["A1"] = "Mandis ranked by estimated annual arrivals across all 23 crops"; mt["A1"].font = H1
hdr(mt, 3, ["Market id", "Market", "District", "State", "Est. annual tonnes, all crops", "Rank in India", "Key rank", "Rank in state", "Key state|rank", "Number of crops traded"])
M0 = 4; MN = M0 + len(mids) - 1
B = lambda col: f"${col}${M0}:${col}${MN}"
for i, mid in enumerate(mids):
    r = M0 + i; mk, di, st = meta[mid]
    mt.cell(r, 1, int(mid) if str(mid).isdigit() else mid); mt.cell(r, 2, mk); mt.cell(r, 3, di); mt.cell(r, 4, st)
    mt.cell(r, 5, f"=SUMIFS('Market_Crop'!{A('G')},'Market_Crop'!{A('D')},A{r})").number_format = RS
    mt.cell(r, 6, f"=COUNTIF({B('E')},\">\"&E{r})+1")
    mt.cell(r, 7, f"=\"r\"&F{r}")
    mt.cell(r, 8, f"=COUNTIFS({B('D')},D{r},{B('E')},\">\"&E{r})+1")
    mt.cell(r, 9, f"=D{r}&\"|\"&H{r}")
    mt.cell(r, 10, f"=COUNTIFS('Market_Crop'!{A('D')},A{r})")
mt.freeze_panes = "A4"
for col, w in zip("ABCDEFGHIJ", (9, 28, 18, 16, 14, 8, 8, 8, 20, 9)): mt.column_dimensions[col].width = w

# ---- Top mandis in India
tp = wb.create_sheet("Top_Mandis", 1)
tp["A1"] = "Top 40 mandis in India by estimated annual arrivals, 23 crops combined"; tp["A1"].font = H1
hdr(tp, 3, ["Rank", "Market", "District", "State", "Est. annual tonnes", "Crops traded"])
for k in range(1, 41):
    r = 3 + k; m = f"MATCH(\"r{k}\",Markets!$G${M0}:$G${MN},0)"
    tp.cell(r, 1, k)
    for j, col in enumerate("BCD"): tp.cell(r, 2 + j, f"=IFERROR(INDEX(Markets!${col}${M0}:${col}${MN},{m}),\"\")")
    tp.cell(r, 5, f"=IFERROR(INDEX(Markets!$E${M0}:$E${MN},{m}),\"\")").number_format = RS
    tp.cell(r, 6, f"=IFERROR(INDEX(Markets!$J${M0}:$J${MN},{m}),\"\")")
for col, w in zip("ABCDEF", (6, 30, 18, 16, 14, 9)): tp.column_dimensions[col].width = w

# ---- Crop leaders in India (top 5 mandis per crop)
crops = sorted({c for *_, c, t in rows}, key=lambda c: -sum(t for *_, cc, t in rows if cc == c))
cl = wb.create_sheet("Crop_Leaders", 2)
cl["A1"] = "Leading mandis for each crop in India (top 5 by estimated annual arrivals)"; cl["A1"].font = H1
hdr(cl, 3, ["Crop", "Crop total in India (t, est.)", "Rank", "Market", "District", "State", "Est. annual tonnes", "Share of India's arrivals"])
r = 4
for c in crops:
    for k in range(1, 6):
        m = f"MATCH(\"{c}|{k}\",'Market_Crop'!{A('K')},0)"
        cl.cell(r, 1, c).font = BOLD if k == 1 else BLACK
        cl.cell(r, 2, f"=SUMIFS('Market_Crop'!{A('G')},'Market_Crop'!{A('E')},A{r})").number_format = RS
        cl.cell(r, 3, k)
        for j, col in enumerate("CBA"): cl.cell(r, 4 + j, f"=IFERROR(INDEX('Market_Crop'!{A(col)},{m}),\"\")")
        cl.cell(r, 7, f"=IFERROR(INDEX('Market_Crop'!{A('G')},{m}),\"\")").number_format = RS
        cl.cell(r, 8, f"=IFERROR(G{r}/B{r},\"\")").number_format = PCT
        r += 1
for col, w in zip("ABCDEFGH", (11, 14, 6, 28, 16, 16, 13, 11)): cl.column_dimensions[col].width = w
cl.freeze_panes = "A4"

# ---- State crop leaders: leading mandi for every crop in every state with >= 20,000 t est. of that crop
st_crop = collections.defaultdict(float)
for st, di, mk, mid, c, t in rows: st_crop[(st, c)] += t
pairs = sorted([k for k, t in st_crop.items() if t * STEP >= 20000], key=lambda k: (k[0], -st_crop[k]))
sl = wb.create_sheet("State_Crop_Leaders", 3)
sl["A1"] = "Leading mandi for each crop in each state (state-crop pairs with at least 20,000 t estimated arrivals)"; sl["A1"].font = H1
hdr(sl, 3, ["State", "Crop", "State crop total (t, est.)", "Leading market", "District", "Est. annual tonnes", "Share of state crop", "Second market", "Second, est. tonnes"])
for i, (st, c) in enumerate(pairs):
    r = 4 + i
    m1 = f"MATCH(A{r}&\"|\"&B{r}&\"|1\",'Market_Crop'!{A('I')},0)"; m2 = f"MATCH(A{r}&\"|\"&B{r}&\"|2\",'Market_Crop'!{A('I')},0)"
    sl.cell(r, 1, st); sl.cell(r, 2, c)
    sl.cell(r, 3, f"=SUMIFS('Market_Crop'!{A('G')},'Market_Crop'!{A('A')},A{r},'Market_Crop'!{A('E')},B{r})").number_format = RS
    sl.cell(r, 4, f"=IFERROR(INDEX('Market_Crop'!{A('C')},{m1}),\"\")"); sl.cell(r, 5, f"=IFERROR(INDEX('Market_Crop'!{A('B')},{m1}),\"\")")
    sl.cell(r, 6, f"=IFERROR(INDEX('Market_Crop'!{A('G')},{m1}),\"\")").number_format = RS
    sl.cell(r, 7, f"=IFERROR(F{r}/C{r},\"\")").number_format = PCT
    sl.cell(r, 8, f"=IFERROR(INDEX('Market_Crop'!{A('C')},{m2}),\"\")")
    sl.cell(r, 9, f"=IFERROR(INDEX('Market_Crop'!{A('G')},{m2}),\"\")").number_format = RS
for col, w in zip("ABCDEFGHI", (16, 11, 13, 28, 16, 13, 10, 28, 13)): sl.column_dimensions[col].width = w
sl.freeze_panes = "C4"

# ---- State top mandis (top 5 per state)
states = sorted({st for st, *_ in rows}, key=lambda s: -sum(t for st, *_, t in rows if st == s))
ss = wb.create_sheet("State_Top_Mandis", 4)
ss["A1"] = "Top 5 mandis in each state by estimated annual arrivals, all 23 crops"; ss["A1"].font = H1
hdr(ss, 3, ["State", "Rank", "Market", "District", "Est. annual tonnes", "Crops traded"])
r = 4
for st in states[:20]:
    for k in range(1, 6):
        m = f"MATCH(\"{st}|{k}\",Markets!$I${M0}:$I${MN},0)"
        ss.cell(r, 1, st).font = BOLD if k == 1 else BLACK; ss.cell(r, 2, k)
        for j, col in enumerate("BC"): ss.cell(r, 3 + j, f"=IFERROR(INDEX(Markets!${col}${M0}:${col}${MN},{m}),\"\")")
        ss.cell(r, 5, f"=IFERROR(INDEX(Markets!$E${M0}:$E${MN},{m}),\"\")").number_format = RS
        ss.cell(r, 6, f"=IFERROR(INDEX(Markets!$J${M0}:$J${MN},{m}),\"\")")
        r += 1
for col, w in zip("ABCDEF", (16, 6, 30, 18, 14, 9)): ss.column_dimensions[col].width = w
ss.freeze_panes = "A4"

for wsx in wb.worksheets:
    for rr in wsx.iter_rows():
        for cell in rr:
            if cell.value is not None and cell.font.name != F:
                cell.font = Font(name=F, bold=cell.font.bold, color=cell.font.color, italic=cell.font.italic, size=cell.font.size)
wb.save(OUT); print("saved", OUT, "rows", n, "markets", len(mids), "state-crop pairs", len(pairs), "days", ND)
