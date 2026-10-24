"""SVG charts for the crop-by-crop production and yield profiles (needs reports/ from crop_profiles.py).

    python analysis/crop_charts.py <outdir>

Writes decomposition.svg, yield_gap.svg, concentration.svg, volatility.svg and card_<crop>.svg per crop.
"""
import html
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
D, RP, OUT = ROOT / "data", ROOT / "reports", pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
esc = html.escape
FONT = "font-family=\"-apple-system,'Segoe UI',Helvetica,Arial,sans-serif\""
INK, MUTED, GRID, BLUE, GREEN, DARK, ORANGE = "#212529", "#6c757d", "#e9ecef", "#1c6e8c", "#2b8a3e", "#343a40", "#e8590c"
NAME = {"Rapeseed & Mustard": "Mustard"}
SHORT = {"Uttar Pradesh": "UP", "Madhya Pradesh": "MP", "Andhra Pradesh": "AP", "West Bengal": "WB", "Tamil Nadu": "TN", "Maharashtra": "Maharashtra",
         "Jammu And Kashmir": "J&K", "Himachal Pradesh": "HP"}
prof = pd.read_csv(RP / "crop_profiles.csv"); tops = pd.read_csv(RP / "crop_top_states.csv"); gaps = pd.read_csv(RP / "crop_state_yield_gaps.csv")
nm = lambda c: NAME.get(c, c)
pct = lambda v: f"{v * 100:+.1f}%"


def svg(w, h, aria, minw=520):
    return [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px;min-width:{minw}px;display:block" role="img" aria-label="{esc(aria)}" xmlns="http://www.w3.org/2000/svg" {FONT}>',
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>']


def save(name, o):
    o.append("</svg>"); (OUT / name).write_text("\n".join(o))


# 1. growth decomposition: area vs yield, per year, 2003-06 -> 2023-26
p = prof.sort_values("production_growth_pa")
W, lx, bh, top = 720, 120, 26, 34; H = top + len(p) * bh + 40; zero = lx + 230; sc = 4200    # px per unit growth rate
o = svg(W, H, "Diverging bar chart of 16 crops: annual production growth from 2003-06 to 2023-26 split into growth from area and growth from yield. Maize and moong grew fastest, around 6% a year, split evenly between area and yield. Soybean grew only through area; groundnut and bajra grew only through yield while their area shrank; jowar and ragi output fell.")
o.append(f'<text x="{lx}" y="16" font-size="12" fill="{MUTED}">Average annual change, 2003-06 to 2023-26 (three-year averages)</text>')
for t in (-0.04, -0.02, 0, 0.02, 0.04, 0.06):
    x = zero + t * sc; o.append(f'<line x1="{x:.0f}" y1="{top-4}" x2="{x:.0f}" y2="{H-34}" stroke="{GRID if t else "#adb5bd"}"/><text x="{x:.0f}" y="{H-20}" font-size="11.5" fill="{MUTED}" text-anchor="middle">{t*100:+.0f}%</text>')
for i, r in enumerate(p.itertuples()):
    y = top + i * bh
    o.append(f'<text x="{lx-8}" y="{y+16}" font-size="12.5" fill="{INK}" text-anchor="end">{esc(nm(r.crop))}</text>')
    a, yl = r.area_growth_pa, r.yield_growth_pa
    # stack: area from zero, yield after it, each signed
    for v, col, start in ((a, BLUE, 0.0), (yl, GREEN, a if (a >= 0) == (yl >= 0) else 0.0)):
        x0_, x1_ = zero + start * sc, zero + (start + v) * sc
        o.append(f'<rect x="{min(x0_, x1_):.1f}" y="{y+5}" width="{abs(x1_-x0_):.1f}" height="{bh-10}" fill="{col}" fill-opacity="0.85"/>')
    px = zero + r.production_growth_pa * sc
    o.append(f'<circle cx="{px:.1f}" cy="{y+bh/2:.1f}" r="4.5" fill="{DARK}"/>')
    o.append(f'<text x="{W-6}" y="{y+16}" font-size="12" fill="{INK}" text-anchor="end">{pct(r.production_growth_pa)}</text>')
ly = H - 6
o.append(f'<rect x="{lx}" y="{ly-11}" width="14" height="12" fill="{BLUE}"/><text x="{lx+19}" y="{ly}" font-size="12" fill="#495057">from area</text>')
o.append(f'<rect x="{lx+110}" y="{ly-11}" width="14" height="12" fill="{GREEN}"/><text x="{lx+129}" y="{ly}" font-size="12" fill="#495057">from yield</text>')
o.append(f'<circle cx="{lx+232}" cy="{ly-5}" r="4.5" fill="{DARK}"/><text x="{lx+242}" y="{ly}" font-size="12" fill="#495057">production (value at right)</text>')
save("decomposition.svg", o)

# 2. yield gap: weakest and strongest major state as % of national yield
g = gaps.assign(lo=gaps["worst_yield"] / gaps["national_yield"], hi=gaps["best_yield"] / gaps["national_yield"]).sort_values("hi")
W, lx, bh, top = 720, 110, 30, 30; H = top + len(g) * bh + 36; x0, x1 = lx + 10, W - 150; vmax = 3.0
X = lambda v: x0 + v / vmax * (x1 - x0)
o = svg(W, H, "Dumbbell chart of yields in the weakest and strongest major producing state for each crop, as a percentage of the national yield, 2023-24 to 2025-26. The widest gaps are in jowar, maize, moong and urad; the narrowest in lentil, sugarcane and soybean.")
for t in (0, 0.5, 1, 1.5, 2, 2.5, 3):
    o.append(f'<line x1="{X(t):.0f}" y1="{top-6}" x2="{X(t):.0f}" y2="{H-30}" stroke="{"#adb5bd" if t == 1 else GRID}"/><text x="{X(t):.0f}" y="{H-16}" font-size="11.5" fill="{MUTED}" text-anchor="middle">{t*100:.0f}%</text>')
o.append(f'<text x="{X(1)+4:.0f}" y="{top-12}" font-size="11" fill="{MUTED}">national yield = 100%</text>')
for i, r in enumerate(g.itertuples()):
    y = top + i * bh + 12
    o.append(f'<text x="{lx-8}" y="{y+4}" font-size="12.5" fill="{INK}" text-anchor="end">{esc(nm(r.crop))}</text>')
    o.append(f'<line x1="{X(r.lo):.1f}" y1="{y}" x2="{X(r.hi):.1f}" y2="{y}" stroke="#adb5bd" stroke-width="3"/>')
    o.append(f'<circle cx="{X(r.lo):.1f}" cy="{y}" r="5" fill="{ORANGE}"/><circle cx="{X(r.hi):.1f}" cy="{y}" r="5" fill="{GREEN}"/>')
    o.append(f'<text x="{X(r.lo)-8:.1f}" y="{y+4}" font-size="11" fill="{ORANGE}" text-anchor="end">{esc(SHORT.get(r.worst_state, r.worst_state))}</text>')
    o.append(f'<text x="{X(r.hi)+8:.1f}" y="{y+4}" font-size="11" fill="{GREEN}">{esc(SHORT.get(r.best_state, r.best_state))} {r.hi*100:.0f}%</text>')
save("yield_gap.svg", o)

# 3. concentration: top-3 state share then and now
c = prof.sort_values("top3_share")
W, lx, bh, top = 720, 120, 28, 30; H = top + len(c) * bh + 36; x0, x1 = lx + 10, W - 170
X = lambda v: x0 + (v - 0.3) / 0.7 * (x1 - x0)
o = svg(W, H, "Chart of the share of national production from each crop's top three states, 2003-06 compared with 2023-26. Soybean, ragi, lentil and sugarcane are the most concentrated, above 80%; rice is the least, at 35%. Sugarcane, moong and tur became more concentrated; rice and jowar less.")
for t in (0.3, 0.5, 0.7, 0.9, 1.0):
    o.append(f'<line x1="{X(t):.0f}" y1="{top-6}" x2="{X(t):.0f}" y2="{H-30}" stroke="{GRID}"/><text x="{X(t):.0f}" y="{H-16}" font-size="11.5" fill="{MUTED}" text-anchor="middle">{t*100:.0f}%</text>')
for i, r in enumerate(c.itertuples()):
    y = top + i * bh + 10; a, b = r.top3_share_2003_06, r.top3_share
    col = ORANGE if b > a + 0.02 else BLUE if b < a - 0.02 else MUTED
    o.append(f'<text x="{lx-8}" y="{y+4}" font-size="12.5" fill="{INK}" text-anchor="end">{esc(nm(r.crop))}</text>')
    o.append(f'<line x1="{X(a):.1f}" y1="{y}" x2="{X(b):.1f}" y2="{y}" stroke="{col}" stroke-width="2.5"/>')
    o.append(f'<circle cx="{X(a):.1f}" cy="{y}" r="4" fill="#ffffff" stroke="{col}" stroke-width="2"/><circle cx="{X(b):.1f}" cy="{y}" r="5" fill="{col}"/>')
    o.append(f'<text x="{x1+14}" y="{y+4}" font-size="11.5" fill="#495057">{esc(SHORT.get(r.top_state, r.top_state))} alone {r.top_state_share*100:.0f}%</text>')
ly = H - 2
o.append(f'<circle cx="{lx+4}" cy="{ly-5}" r="4" fill="#ffffff" stroke="{MUTED}" stroke-width="2"/><text x="{lx+13}" y="{ly}" font-size="12" fill="#495057">2003-06</text>')
o.append(f'<circle cx="{lx+84}" cy="{ly-5}" r="5" fill="{MUTED}"/><text x="{lx+94}" y="{ly}" font-size="12" fill="#495057">2023-26: orange = more concentrated, blue = less</text>')
save("concentration.svg", o)

# 4. volatility: typical year-on-year swing and the worst single-year fall since 2000
v = prof.sort_values("typical_yoy_swing")
W, lx, bh, top = 720, 120, 26, 30; H = top + len(v) * bh + 30; sc = (W - lx - 260) / 0.25
o = svg(W, H, "Bar chart of the typical year-on-year change in all-India production since 2000 for 16 crops. Groundnut and moong swing about 21 to 22 percent in a typical year and ragi 16 percent; wheat and rice about 4 percent.")
o.append(f'<text x="{lx}" y="16" font-size="12" fill="{MUTED}">Typical yearly change in national output since 2000, and the worst single-year fall</text>')
for i, r in enumerate(v.itertuples()):
    y = top + i * bh; w = r.typical_yoy_swing * sc
    o.append(f'<text x="{lx-8}" y="{y+16}" font-size="12.5" fill="{INK}" text-anchor="end">{esc(nm(r.crop))}</text>')
    o.append(f'<rect x="{lx}" y="{y+5}" width="{w:.1f}" height="{bh-10}" fill="{BLUE}"/>')
    o.append(f'<text x="{lx+w+6:.1f}" y="{y+16}" font-size="12" fill="{INK}">{r.typical_yoy_swing*100:.0f}%<tspan fill="{ORANGE}" dx="10">worst {r.worst_yoy_fall*100:.0f}% ({esc(r.worst_fall_year)})</tspan></text>')
save("volatility.svg", o)

# 5. one card per crop: index lines (2003-06 = 100) + top-5 states
ind = pd.read_csv(D / "upag/apy_all_india.csv.gz"); ind = ind[ind["Season"] == "Total"]
ind["Value"] = pd.to_numeric(ind["Value"], errors="coerce"); ind["y0"] = ind["Crop Year"].str[:4].astype(int)
for r in prof.itertuples():
    s = ind[ind["Crop"] == r.crop].pivot_table(index="y0", columns="Metric", values="Value", aggfunc="first").sort_index()
    s = s[s.index >= 1980]
    base = s.loc[2003:2005].mean()
    idx = s / base * 100
    W, H = 720, 230; cx0, cx1, cy0, cy1 = 52, 380, 28, 196
    hi = max(160, float(idx.max().max()) * 1.05); lo = min(40, float(idx.min().min()) * 0.95)
    X = lambda yy: cx0 + (yy - 1980) / (s.index.max() - 1980) * (cx1 - cx0); Y = lambda vv: cy1 - (vv - lo) / (hi - lo) * (cy1 - cy0)
    o = svg(W, H, f"{nm(r.crop)}: production, area and yield since 1980 indexed to 2003-06, and the five largest producing states with their share of output and yield.", 560)
    o.append(f'<text x="{cx0}" y="16" font-size="12" fill="{MUTED}">Index, 2003-06 average = 100</text>')
    step = 50 if hi - lo < 250 else 100
    t = (int(lo) // step + 1) * step
    while t < hi:
        o.append(f'<line x1="{cx0}" y1="{Y(t):.1f}" x2="{cx1}" y2="{Y(t):.1f}" stroke="{GRID if t != 100 else "#adb5bd"}"/><text x="{cx0-5}" y="{Y(t)+4:.1f}" font-size="10.5" fill="{MUTED}" text-anchor="end">{t}</text>'); t += step
    for yy in (1980, 1990, 2000, 2010, 2020):
        o.append(f'<text x="{X(yy):.0f}" y="{cy1+15}" font-size="10.5" fill="{MUTED}" text-anchor="middle">{yy}</text>')
    for metric, col, wd, dash in (("Area", BLUE, 1.6, ' stroke-dasharray="5 3"'), ("Yield", GREEN, 1.6, ""), ("Production", DARK, 2.4, "")):
        ser = idx[metric].dropna()
        pts = " ".join(f"{X(yy):.1f},{Y(vv):.1f}" for yy, vv in ser.items())
        o.append(f'<polyline fill="none" stroke="{col}" stroke-width="{wd}"{dash} stroke-linejoin="round" points="{pts}"/>')
    o.append(f'<text x="{cx0}" y="{H-8}" font-size="11.5" fill="{DARK}">— production</text><text x="{cx0+92}" y="{H-8}" font-size="11.5" fill="{GREEN}">— yield</text><text x="{cx0+150}" y="{H-8}" font-size="11.5" fill="{BLUE}">- - area</text>')
    # states
    t5 = tops[tops["crop"] == r.crop].sort_values("rank")
    sx0, sw = 520, 150; o.append(f'<text x="410" y="16" font-size="12" fill="{MUTED}">Largest producers, 2023-26: share · yield</text>')
    mx = t5["share"].max()
    for i, q in enumerate(t5.itertuples()):
        y = 30 + i * 30
        o.append(f'<text x="{sx0-8}" y="{y+15}" font-size="12" fill="{INK}" text-anchor="end">{esc(q.state)}</text>')
        o.append(f'<rect x="{sx0}" y="{y+4}" width="{q.share/mx*sw*0.62:.1f}" height="16" fill="#adb5bd"/>')
        yv = f"{q.yield_kg_ha/1000:,.1f} t/ha" if r.crop == "Sugarcane" else f"{q.yield_kg_ha:,.0f} kg/ha"
        o.append(f'<text x="{sx0+q.share/mx*sw*0.62+5:.1f}" y="{y+16}" font-size="11.5" fill="{INK}">{q.share*100:.0f}% · {yv}</text>')
    save(f"card_{r.crop.replace(' & ', '_').replace(' ', '_').lower()}.svg", o)
print("charts:", sorted(p.name for p in OUT.glob("*.svg")))
