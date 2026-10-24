"""State-wise maize, rice and broken-rice price analysis workbook from Agmarknet monthly data.

Usage: python analysis/workbooks/statewise_rice_maize.py <out.xlsx>
Reads data/agmarknet/state_monthly.csv.gz (Maize, Rice, Broken Rice).
Every metric is a formula over the monthly price sheets, driven by the carry inputs on Inputs.
"""
import csv, gzip, pathlib, sys, collections
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.formatting.rule import ColorScaleRule, CellIsRule
from openpyxl.chart import LineChart, Reference
from openpyxl.utils import get_column_letter as L

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = sys.argv[1]
F = "Arial"
BLUE = Font(name=F, color="0000FF"); BLACK = Font(name=F); GREEN = Font(name=F, color="008000")
BOLD = Font(name=F, bold=True); H1 = Font(name=F, bold=True, size=13)
HDR = Font(name=F, bold=True, color="FFFFFF"); HFILL = PatternFill("solid", fgColor="1F4E78")
YEL = PatternFill("solid", fgColor="FFFF00")
RS = '#,##0;(#,##0);-'; PCT = '0.0%;(0.0%);-'

# ---- load data -> series[commodity][state][month] = (price, arrivals)
series = collections.defaultdict(lambda: collections.defaultdict(dict))
for r in csv.DictReader(gzip.open(ROOT / "data/agmarknet/state_monthly.csv.gz", "rt", encoding="utf-8")):
    if r["commodity"] in ("Maize", "Rice", "Broken Rice") and r["price_rs_qtl"]:
        series[r["commodity"]][r["state"]][r["month"]] = (float(r["price_rs_qtl"]), float(r["arrivals_t"] or 0))
months = sorted({m for c in series.values() for s in c.values() for m in s})

# All-India rows for rice and broken rice (maize already has one): arrival-weighted mean of state prices
for com in ("Maize", "Rice", "Broken Rice"):
    ai = {}
    for m in months:
        pts = [(v[m][0], v[m][1]) for st, v in series[com].items() if m in v and v[m][1] > 0]
        w = sum(a for _, a in pts)
        if w: ai[m] = (sum(p * a for p, a in pts) / w, w)
    series[com]["All India"] = ai

# Keep states with >= 60 months of prices and real volume in the last 12 months
last12 = months[-12:]
def keep(com, st):
    v = series[com][st]
    return st == "All India" or (len(v) >= 60 and sum(v.get(m, (0, 0))[1] for m in last12) >= 5000)
states = {com: ["All India"] + sorted([s for s in series[com] if s != "All India" and keep(com, s)],
          key=lambda s: -sum(series[com][s].get(m, (0, 0))[1] for m in last12)) for com in series}

wb = Workbook()
def hdr(ws, r, vals, c0=1):
    for i, v in enumerate(vals):
        c = ws.cell(r, c0 + i, v); c.font = HDR; c.fill = HFILL
        c.alignment = Alignment(wrap_text=True, vertical="center")

# ---- Inputs
ws = wb.active; ws.title = "Inputs"
ws["A1"] = "State-wise maize, rice and broken-rice prices: Agmarknet, Jan 2019 to Oct 2026"; ws["A1"].font = H1
ws["A2"] = "Blue = input. Every other sheet recalculates from these and the monthly price sheets."
hdr(ws, 3, ["Parameter", "Value", "Unit", "Note"])
inp = [("rent", 10, "Rs/qtl/month", "Hired warehouse rent plus fumigation"),
       ("interest", 0.105, "% p.a.", "Working-capital rate on stock"),
       ("shrink", 0.001, "% per month", "Storage loss"),
       ("hold", 6, "months", "Holding period for the carry backtest"),
       ("dip", 0.85, "x 12m mean", "A month is a dip when price <= this x trailing 12-month mean"),
       ("season_to", "2025-12", "month", "Seasonality uses full calendar years up to this month")]
NM = {}
for i, (n, v, u, note) in enumerate(inp):
    r = 4 + i
    ws.cell(r, 1, n).font = BLACK; c = ws.cell(r, 2, v); c.font = BLUE
    c.number_format = PCT if u.startswith("%") else ("@" if isinstance(v, str) else '0.00' if isinstance(v, float) else '0')
    ws.cell(r, 3, u).font = BLACK; ws.cell(r, 4, note).font = BLACK
    NM[n] = f"Inputs!$B${r}"
ws["A12"] = "Source: Agmarknet dashboard API (api.agmarknet.gov.in/v1/dashboard-data, statewise_price_arrival_sp): Maize id 4, Rice id 3, Broken Rice id 244. Prices are Agmarknet's weighted-average Rs/quintal; arrivals in tonnes. All-India = arrival-weighted mean of state prices (this workbook's calculation). Oct-2026 runs to 23 Oct."
ws["A13"] = "Caveats: Agmarknet coverage widened when its new portal went live in Nov-2025, so arrival totals from then on are not comparable with earlier months. States are kept only with 60+ months of prices and 5,000+ t of arrivals in the last 12 months. Rice prices mix many varieties and grades, so state differences partly reflect the mix, not just location."
for a in ("A12", "A13"):
    ws[a].alignment = Alignment(wrap_text=True); ws[a].font = Font(name=F, italic=True)
ws.merge_cells("A12:D12"); ws.merge_cells("A13:D13"); ws.row_dimensions[12].height = 60; ws.row_dimensions[13].height = 60
for col, w in zip("ABCD", (16, 12, 14, 80)): ws.column_dimensions[col].width = w

N = len(months); R0 = 4; RN = R0 + N - 1   # month rows on each price sheet
short = {"Maize": "Maize", "Rice": "Rice", "Broken Rice": "Broken"}
psheet = {}

for com in ("Maize", "Rice", "Broken Rice"):
    sts = states[com]; k = short[com]
    # ---- price sheet
    p = wb.create_sheet(f"{k}_Price"); psheet[com] = p.title
    p["A1"] = f"{com}: monthly weighted-average price by state (Rs/quintal), Agmarknet"; p["A1"].font = H1
    hdr(p, 3, ["Month", "Year", "Mo"] + sts)
    for i, m in enumerate(months):
        r = R0 + i
        p.cell(r, 1, m).font = BLACK
        p.cell(r, 2, f"=VALUE(LEFT(A{r},4))").font = BLACK
        p.cell(r, 3, f"=VALUE(RIGHT(A{r},2))").font = BLACK
        for j, st in enumerate(sts):
            v = series[com][st].get(m)
            if v: c = p.cell(r, 4 + j, round(v[0], 1)); c.font = BLUE; c.number_format = RS
    p.freeze_panes = "D4"; p.column_dimensions["A"].width = 10
    for j in range(len(sts)): p.column_dimensions[L(4 + j)].width = 12
    # ---- arrivals sheet
    a = wb.create_sheet(f"{k}_Arrivals")
    a["A1"] = f"{com}: monthly arrivals by state (tonnes), Agmarknet"; a["A1"].font = H1
    hdr(a, 3, ["Month"] + sts)
    for i, m in enumerate(months):
        r = R0 + i; a.cell(r, 1, m).font = BLACK
        for j, st in enumerate(sts):
            v = series[com][st].get(m)
            if v: c = a.cell(r, 2 + j, round(v[1])); c.font = BLUE; c.number_format = RS
    a.freeze_panes = "B4"
    # ---- carry sheet: net result of buying in month t and selling after `hold` months
    cs = wb.create_sheet(f"{k}_Carry")
    cs["A1"] = f"{com}: net result of buying in a month and selling after the holding period (Rs/quintal), net of rent, interest and shrinkage"; cs["A1"].font = H1
    cs["A2"] = "Dip block (right): shows the month as yyyymm when price <= Inputs!dip x trailing 12-month mean, else blank."
    hdr(cs, 3, ["Month"] + sts)
    off = len(sts) + 3   # dip block starts here
    hdr(cs, 3, ["Dip: " + s for s in sts], off)
    for i, m in enumerate(months):
        r = R0 + i; cs.cell(r, 1, m).font = GREEN
        for j, st in enumerate(sts):
            col = L(4 + j); pr = f"'{p.title}'!{col}{r}"
            fut = f"INDEX('{p.title}'!{col}${R0}:{col}${RN},ROW()-{R0 - 1}+{NM['hold']})"
            cs.cell(r, 2 + j, f"=IF(OR({pr}=\"\",ROW()-{R0 - 1}+{NM['hold']}>{N}),\"\",IF({fut}=\"\",\"\","
                    f"{fut}-{pr}-{NM['hold']}*({NM['rent']}+{pr}*{NM['interest']}/12+{pr}*{NM['shrink']})))").number_format = RS
            if i >= 12:
                cs.cell(r, off + j, f"=IF(OR({pr}=\"\",COUNT('{p.title}'!{col}{r-12}:{col}{r-1})<9),\"\","
                        f"IF({pr}<={NM['dip']}*AVERAGE('{p.title}'!{col}{r-12}:{col}{r-1}),'{p.title}'!$B{r}*100+'{p.title}'!$C{r},\"\"))")
    cs.freeze_panes = "B4"
    cs.conditional_formatting.add(f"B{R0}:{L(1+len(sts))}{RN}", CellIsRule(operator="greaterThan", formula=["0"], font=Font(name=F, color="006100")))
    cs.conditional_formatting.add(f"B{R0}:{L(1+len(sts))}{RN}", CellIsRule(operator="lessThan", formula=["0"], font=Font(name=F, color="9C0006")))

# ---- Seasonality: price index by calendar month (1.00 = that state's average month)
s = wb.create_sheet("Seasonality", 1)
s["A1"] = "Seasonal price index by state: average price in each calendar month / average of all months (full years to Inputs!season_to)"; s["A1"].font = H1
s["A2"] = "Below 1.00 = cheaper than usual (buy window); above 1.00 = dearer (sell window). Green = cheapest months, red = dearest."
hdr(s, 3, ["Commodity", "State"] + ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] + ["Cheapest month", "Dearest month", "Peak/trough spread"])
r = 4; srow = {}
for com in ("Maize", "Rice", "Broken Rice"):
    t = psheet[com]
    for j, st in enumerate(states[com]):
        col = L(4 + j); rng = f"'{t}'!{col}${R0}:{col}${RN}"
        yr = f"'{t}'!$B${R0}:$B${RN}"; mo = f"'{t}'!$C${R0}:$C${RN}"
        cap = f"VALUE(LEFT({NM['season_to']},4))"
        s.cell(r, 1, com).font = BLACK; s.cell(r, 2, st).font = BOLD if st == "All India" else BLACK
        for mm in range(1, 13):
            s.cell(r, 2 + mm, f"=IFERROR(AVERAGEIFS({rng},{mo},{mm},{yr},\"<=\"&{cap})/AVERAGEIFS({rng},{yr},\"<=\"&{cap}),\"\")").number_format = '0.00'
        s.cell(r, 15, f"=IFERROR(INDEX($C$3:$N$3,MATCH(MIN(C{r}:N{r}),C{r}:N{r},0)),\"\")")
        s.cell(r, 16, f"=IFERROR(INDEX($C$3:$N$3,MATCH(MAX(C{r}:N{r}),C{r}:N{r},0)),\"\")")
        s.cell(r, 17, f"=IFERROR(MAX(C{r}:N{r})/MIN(C{r}:N{r})-1,\"\")").number_format = PCT
        srow[(com, st)] = r; r += 1
s.conditional_formatting.add(f"C4:N{r-1}", ColorScaleRule(start_type="num", start_value=0.94, start_color="63BE7B", mid_type="num", mid_value=1, mid_color="FFFFFF", end_type="num", end_value=1.06, end_color="F8696B"))
s.column_dimensions["A"].width = 13; s.column_dimensions["B"].width = 20
for c in range(3, 15): s.column_dimensions[L(c)].width = 7
for c in (15, 16, 17): s.column_dimensions[L(c)].width = 13
s.freeze_panes = "C4"

# ---- Summary
sm = wb.create_sheet("Summary", 1)
sm["A1"] = "State-wise summary: where and when maize and rice are cheapest, and whether carrying stock has paid"; sm["A1"].font = H1
sm["A2"] = "Latest = Oct-2026 (to 23 Oct) or the last month with data. Carry = buy in a month, sell after Inputs!hold months, net of rent, interest and shrinkage; counted over months since Jan-2023. Dips counted since Jan-2020."
hdr(sm, 3, ["Commodity", "State", "Arrivals, last 12m (t)", "Latest price (Rs/qtl)", "12-month mean (Rs/qtl)", "Latest vs 12m mean",
            "Latest vs All-India (Rs/qtl)", "Cheapest month", "Dearest month", "Seasonal spread", "Dip months since 2020",
            "Last dip month", "Carry: months positive", "Carry: months tested", "Carry: share positive", "Carry: average (Rs/qtl)"])
r = 4
i23 = months.index("2023-01"); i20 = months.index("2020-01")
for com in ("Maize", "Rice", "Broken Rice"):
    t = psheet[com]; k = short[com]
    for j, st in enumerate(states[com]):
        col = L(4 + j); acol = L(2 + j); ccol = L(2 + j); dcol = L(len(states[com]) + 3 + j)
        rng = f"'{t}'!{col}${R0}:{col}${RN}"
        sm.cell(r, 1, com).font = BLACK; sm.cell(r, 2, st).font = BOLD if st == "All India" else BLACK
        sm.cell(r, 3, f"=SUM('{k}_Arrivals'!{acol}{RN-11}:{acol}{RN})").number_format = RS
        sm.cell(r, 4, f"=INDEX({rng},MATCH(9.99E+307,{rng}))").number_format = RS
        sm.cell(r, 5, f"=AVERAGE('{t}'!{col}{RN-11}:{col}{RN})").number_format = RS
        sm.cell(r, 6, f"=IFERROR(D{r}/E{r}-1,\"\")").number_format = PCT
        sm.cell(r, 7, f"=IFERROR(D{r}-D${r - j},\"\")").number_format = RS
        sr = srow[(com, st)]
        sm.cell(r, 8, f"=Seasonality!O{sr}"); sm.cell(r, 9, f"=Seasonality!P{sr}")
        sm.cell(r, 10, f"=Seasonality!Q{sr}").number_format = PCT
        drng = f"'{k}_Carry'!{dcol}{R0 + i20}:{dcol}{RN}"
        sm.cell(r, 11, f"=COUNT({drng})")
        sm.cell(r, 12, f"=IF(COUNT({drng})=0,\"none\",INT(MAX({drng})/100)&\"-\"&TEXT(MOD(MAX({drng}),100),\"00\"))")
        crng = f"'{k}_Carry'!{ccol}{R0 + i23}:{ccol}{RN}"
        sm.cell(r, 13, f"=COUNTIF({crng},\">0\")"); sm.cell(r, 14, f"=COUNT({crng})")
        sm.cell(r, 15, f"=IFERROR(M{r}/N{r},\"\")").number_format = PCT
        sm.cell(r, 16, f"=IFERROR(AVERAGE({crng}),\"\")").number_format = RS
        for cc in range(3, 17):
            if sm.cell(r, cc).font != BOLD: sm.cell(r, cc).font = GREEN if cc in (8, 9, 10) else BLACK
        r += 1
    r += 1
sm.conditional_formatting.add(f"G4:G{r}", ColorScaleRule(start_type="min", start_color="63BE7B", mid_type="num", mid_value=0, mid_color="FFFFFF", end_type="max", end_color="F8696B"))
sm.conditional_formatting.add(f"O4:O{r}", ColorScaleRule(start_type="num", start_value=0, start_color="F8696B", mid_type="num", mid_value=0.5, mid_color="FFFFFF", end_type="num", end_value=1, end_color="63BE7B"))
for c, w in zip(range(1, 17), (12, 20, 13, 12, 12, 11, 13, 10, 10, 10, 11, 11, 10, 10, 10, 11)):
    sm.column_dimensions[L(c)].width = w
sm.row_dimensions[3].height = 44; sm.freeze_panes = "C4"

# ---- Charts: All-India plus top 4 states by arrivals, per commodity
ch = wb.create_sheet("Charts", 3)
ch["A1"] = "Monthly prices, Jan 2019 to Oct 2026: All-India and the four highest-arrival states (Rs/quintal)"; ch["A1"].font = H1
anchor = 3
for com in ("Maize", "Rice", "Broken Rice"):
    t = wb[psheet[com]]; n = min(5, len(states[com]))
    lc = LineChart(); lc.title = f"{com} price by state (Rs/qtl)"; lc.height = 9; lc.width = 26
    lc.y_axis.title = "Rs/quintal"; lc.x_axis.number_format = "@"; lc.x_axis.tickLblSkip = 12
    data = Reference(t, min_col=4, max_col=3 + n, min_row=3, max_row=RN)
    lc.add_data(data, titles_from_data=True)
    lc.set_categories(Reference(t, min_col=1, min_row=R0, max_row=RN))
    for sser in lc.series: sser.smooth = False; sser.graphicalProperties.line.width = 19000
    ch.add_chart(lc, f"A{anchor}"); anchor += 19

for wsx in wb.worksheets:
    for row in wsx.iter_rows():
        for cell in row:
            if cell.value is not None and (cell.font is None or cell.font.name != F):
                cell.font = Font(name=F, bold=cell.font.bold, color=cell.font.color, italic=cell.font.italic, size=cell.font.size)
wb.save(OUT)
print("saved", OUT, {c: len(v) for c, v in states.items()})
