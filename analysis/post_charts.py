"""SVG charts for the post "India's Farm Map in Seven Charts" (masaladeutsch, 24 Oct 2026).

    python analysis/post_charts.py <states.geojson> <outdir>

Needs reports/ from build_insights.py and clusters.py. State boundaries: DataMeet
(https://github.com/datameet/maps, website/docs/data/geojson/states.geojson), not bundled here.
"""
import json, math, sys, pathlib, html
import numpy as np, pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
GEO, OUT = sys.argv[1], pathlib.Path(sys.argv[2]); OUT.mkdir(exist_ok=True)
D, RP = REPO / "data", REPO / "reports"
FONT = "font-family=\"-apple-system,'Segoe UI',Helvetica,Arial,sans-serif\""
esc = html.escape
INK, MUTED, GRID = "#212529", "#6c757d", "#e9ecef"

def svg_open(w, h, aria, minw=520):
    return [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px;min-width:{minw}px;display:block" role="img" aria-label="{esc(aria)}" xmlns="http://www.w3.org/2000/svg" {FONT}>',
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>']

# ---------------- data
apy = pd.read_csv(D / "upag/apy_state.csv.gz", low_memory=False)
apy = apy[(apy["Season"] == "Total") & apy["RecordType"].str.startswith("State")]
apy["Value"] = pd.to_numeric(apy["Value"], errors="coerce")
ai = pd.read_csv(D / "upag/apy_all_india.csv.gz"); ai = ai[ai["Season"] == "Total"]
ai["Value"] = pd.to_numeric(ai["Value"], errors="coerce"); ai["y0"] = ai["Crop Year"].str[:4].astype(int)
AGG = {"Cereals", "Total Food Grains", "Total Oil Seeds", "Total Pulses", "Nutri/Coarse Cereals", "Shree Anna /Nutri Cereals", "Jute & Mesta", "Other Pulses", "Small Millets"}
LAST = int(ai["y0"].max()); LASTLAB = f"{LAST}-{(LAST + 1) % 100:02d}"

# ---------------- 1. area by crop
ar = ai[ai["Metric"] == "Area"].pivot_table(index="Crop", columns="y0", values="Value", aggfunc="first")
a = pd.DataFrame({"now": ar[LAST], "then": ar[LAST - 10]}).drop(index=[c for c in AGG if c in ar.index]).dropna().sort_values("now", ascending=False).head(16)
W, lx, bh, top = 720, 150, 26, 30; H = top + len(a) * bh + 40; sc = (W - lx - 150) / a["now"].max()
o = svg_open(W, H, f"Bar chart of all-India crop area in {LASTLAB} for the 16 largest crops, with change from ten years earlier. Rice is largest at {a['now'].iloc[0]:.0f} lakh hectares.")
o.append(f'<text x="{lx}" y="18" font-size="12" fill="{MUTED}">Area {LASTLAB}, lakh hectares (change vs {LAST-10}-{(LAST-9)%100:02d})</text>')
for i, (c, r) in enumerate(a.iterrows()):
    y = top + i * bh; w = r["now"] * sc; ch = r["now"] / r["then"] - 1
    o.append(f'<text x="{lx-8}" y="{y+16}" font-size="12.5" fill="{INK}" text-anchor="end">{esc(c)}</text>')
    o.append(f'<rect x="{lx}" y="{y+4}" width="{w:.1f}" height="{bh-9}" fill="#1c6e8c"/>')
    col = "#2b8a3e" if ch > 0.05 else "#c92a2a" if ch < -0.05 else MUTED
    o.append(f'<text x="{lx+w+6:.1f}" y="{y+16}" font-size="12" fill="{INK}">{r["now"]:,.0f}<tspan fill="{col}" dx="8">{"+" if ch>=0 else "−"}{abs(ch)*100:.0f}%</tspan></text>')
o.append("</svg>"); (OUT / "area.svg").write_text("\n".join(o))

# ---------------- 2. yield small multiples
CROPS = ["Rice", "Wheat", "Maize", "Gram", "Tur", "Soybean", "Rapeseed & Mustard", "Groundnut", "Cotton"]
yl = ai[ai["Metric"] == "Yield"].pivot_table(index="y0", columns="Crop", values="Value", aggfunc="first")
cols, pw, ph, gx, gy = 3, 236, 140, 10, 12; W = cols * pw + (cols - 1) * gx; H = 3 * (ph + gy) + 10
o = svg_open(W, H, "Small multiple line charts of all-India yield in kilograms per hectare from 1966-67 to the latest year for rice, wheat, maize, gram, tur, soybean, rapeseed and mustard, groundnut and cotton. Maize, wheat and rice show the steepest long-run rises; tur and cotton have flattened.", 600)
for k, c in enumerate(CROPS):
    s = yl[c].dropna(); cx, cy = (k % 3) * (pw + gx), (k // 3) * (ph + gy)
    x0, x1, y0, y1 = cx + 40, cx + pw - 8, cy + 26, cy + ph - 20; lo = 0; hi = s.max() * 1.08
    X = lambda yy: x0 + (yy - 1966) / (LAST - 1966) * (x1 - x0); Y = lambda v: y1 - (v - lo) / (hi - lo) * (y1 - y0)
    o.append(f'<rect x="{cx}" y="{cy}" width="{pw}" height="{ph}" fill="#f8f9fa" stroke="#dee2e6"/>')
    o.append(f'<text x="{cx+8}" y="{cy+16}" font-size="12.5" font-weight="700" fill="{INK}">{esc(c.replace("Rapeseed & Mustard", "Mustard"))}</text>')
    o.append(f'<text x="{cx+pw-8}" y="{cy+16}" font-size="11" fill="#495057" text-anchor="end">{LASTLAB}: {s.iloc[-1]:,.0f} kg/ha</text>')
    step = 500 if hi < 2500 else 1000
    for t in range(0, int(hi) + 1, step):
        o.append(f'<line x1="{x0}" y1="{Y(t):.1f}" x2="{x1}" y2="{Y(t):.1f}" stroke="{GRID}"/><text x="{x0-4}" y="{Y(t)+4:.1f}" font-size="10" fill="{MUTED}" text-anchor="end">{t:,}</text>')
    for yy in (1970, 1990, 2010):
        o.append(f'<text x="{X(yy):.0f}" y="{y1+13}" font-size="10" fill="{MUTED}" text-anchor="middle">{yy}</text>')
    pts = " ".join(f"{X(yy):.1f},{Y(v):.1f}" for yy, v in s.items())
    o.append(f'<polyline fill="none" stroke="#2b8a3e" stroke-width="1.8" stroke-linejoin="round" points="{pts}"/>')
o.append("</svg>"); (OUT / "yields.svg").write_text("\n".join(o))

# ---------------- map geometry
G = json.load(open(GEO))
NAME = {"Andaman & Nicobar Island": "Andaman And Nicobar Islands", "Arunanchal Pradesh": "Arunachal Pradesh", "Dadara & Nagar Havelli": "Dadra And Nagar Haveli",
        "Daman & Diu": "Daman And Diu", "Jammu & Kashmir": "Jammu And Kashmir", "NCT of Delhi": "Delhi"}
def rings(geom):
    if geom["type"] == "Polygon": return [geom["coordinates"][0]]
    return [p[0] for p in geom["coordinates"]]
def dp(pts, eps):
    if len(pts) < 3: return pts
    a, b = np.array(pts[0]), np.array(pts[-1]); P = np.array(pts)
    d = np.abs(np.cross(b - a, P - a)) / (np.linalg.norm(b - a) or 1)
    i = int(d.argmax())
    if d[i] > eps: return dp(pts[:i + 1], eps)[:-1] + dp(pts[i:], eps)
    return [pts[0], pts[-1]]
def mappaths(w, h, pad=6, eps=0.9, skip=("Andaman & Nicobar Island", "Lakshadweep")):
    feats = [f for f in G["features"] if f["properties"]["ST_NM"] not in skip]
    allp = [p for f in feats for r in rings(f["geometry"]) for p in r]
    lons, lats = [p[0] for p in allp], [p[1] for p in allp]; k = math.cos(math.radians(22))
    lon0, lon1, lat0, lat1 = min(lons), max(lons), min(lats), max(lats)
    sx = (w - 2 * pad) / ((lon1 - lon0) * k); sy = (h - 2 * pad) / (lat1 - lat0); s = min(sx, sy)
    ox = pad + ((w - 2 * pad) - (lon1 - lon0) * k * s) / 2
    out = {}
    for f in feats:
        ds = []
        for r in rings(f["geometry"]):
            pts = [((lon - lon0) * k * s + ox, (lat1 - lat) * s + pad) for lon, lat in r]
            thin = [pts[0]]                                  # radial thinning: drop points closer than eps px
            for p in pts[1:]:
                if (p[0] - thin[-1][0]) ** 2 + (p[1] - thin[-1][1]) ** 2 >= eps ** 2:
                    thin.append(p)
            pts = thin
            if len(pts) >= 3:
                ds.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        out[NAME.get(f["properties"]["ST_NM"], f["properties"]["ST_NM"])] = "".join(ds)
    return out

def ramp(t):  # white -> deep green
    t = max(0, min(1, t)); a, b = (247, 252, 245), (0, 90, 50)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))

# ---------------- 3. production-share maps
years = sorted(apy["Crop Year"].unique())[-3:]
pr = apy[(apy["Metric"] == "Production") & apy["Crop Year"].isin(years)].copy()
pr["State"] = pr["State"].replace({"Ladakh": "Jammu And Kashmir"})
MAPC = [("Rice", "Rice"), ("Wheat", "Wheat"), ("Maize", "Maize"), ("Total Pulses", "Pulses"), ("Total Oil Seeds", "Oilseeds"), ("Cotton", "Cotton")]
pw, ph = 236, 270; paths = mappaths(pw - 10, ph - 66, eps=1.5)
W = 3 * pw + 20; H = 2 * (ph + 12) + 40
o = svg_open(W, H, "Six small maps of India showing each state's share of national production, three-year average, for rice, wheat, maize, pulses, oilseeds and cotton. Wheat is concentrated in Uttar Pradesh, Punjab, Madhya Pradesh and Haryana; maize in Karnataka, Madhya Pradesh, Bihar and Maharashtra; cotton in Gujarat, Maharashtra and Telangana.", 600)
for k, (crop, lab) in enumerate(MAPC):
    sub = pr[pr["Crop"] == crop].groupby("State")["Value"].mean(); share = sub / sub.sum()
    cx, cy = (k % 3) * (pw + 10), (k // 3) * (ph + 12)
    o.append(f'<rect x="{cx}" y="{cy}" width="{pw}" height="{ph}" fill="#f8f9fa" stroke="#dee2e6"/>')
    o.append(f'<text x="{cx+8}" y="{cy+17}" font-size="13" font-weight="700" fill="{INK}">{lab}</text>')
    top3 = share.sort_values(ascending=False).head(3)
    tl = [f"{s.replace(' Pradesh', ' Pr.')} {v*100:.0f}%" for s, v in top3.items()]
    o.append(f'<text x="{cx+8}" y="{cy+ph-30}" font-size="11" fill="#495057">Top: {esc(", ".join(tl[:2]))},</text>')
    o.append(f'<text x="{cx+8}" y="{cy+ph-15}" font-size="11" fill="#495057">{esc(tl[2])}</text>')
    o.append(f'<g transform="translate({cx+5},{cy+24})">')
    mx = share.max()
    for st, d in paths.items():
        v = share.get(st, 0); o.append(f'<path d="{d}" fill="{ramp((v/mx)**0.7 if mx else 0)}" stroke="#adb5bd" stroke-width="0.5"/>')
    o.append("</g>")
ly = H - 22
for i, t in enumerate([0, .25, .5, .75, 1]):
    o.append(f'<rect x="{8+i*26}" y="{ly}" width="24" height="12" fill="{ramp(t)}" stroke="#adb5bd" stroke-width="0.5"/>')
o.append(f'<text x="{8+5*26+8}" y="{ly+11}" font-size="12" fill="#495057">share of national production: low → high (scaled to each crop\'s largest state)</text>')
o.append("</svg>"); (OUT / "maps.svg").write_text("\n".join(o))

# ---------------- 4. cluster map
cl = pd.read_csv(RP / "state_crop_clusters.csv"); cen = pd.read_csv(RP / "state_cluster_centroids.csv")
CC = {1: "#1c6e8c", 2: "#74c0fc", 3: "#e8590c", 4: "#f2c94c", 5: "#7048e8", 6: "#2b8a3e"}
def cname(row):
    top = row.drop("cluster").sort_values(ascending=False)
    return " + ".join(f"{k.lower()} {v*100:.0f}%" for k, v in top.head(3).items())
pw2, ph2 = 420, 470; paths2 = mappaths(pw2, ph2, eps=1.2)
W = 760; H = ph2 + 20
o = svg_open(W, H, "Map of India colouring each state by its k-means cluster of crop-area mix, with a legend describing each cluster's average crop shares.", 600)
lab = dict(zip(cl["State"], cl["cluster"]))
for st, d in paths2.items():
    c = lab.get(st); o.append(f'<path d="{d}" fill="{CC.get(c, "#f1f3f5")}" stroke="#ffffff" stroke-width="0.7"/>')
for i, (_, r) in enumerate(cen.sort_values("cluster").iterrows()):
    y = 24 + i * 84; c = int(r["cluster"]); members = sorted(cl[cl["cluster"] == c]["State"])
    o.append(f'<rect x="440" y="{y}" width="16" height="16" fill="{CC[c]}"/><text x="464" y="{y+13}" font-size="13" font-weight="700" fill="{INK}">Cluster {c}</text>')
    o.append(f'<text x="464" y="{y+31}" font-size="11.5" fill="#495057">{esc(cname(r))}</text>')
    words, line, ly2 = ", ".join(m.replace(" And ", " & ") for m in members).split(" "), "", y + 47
    for wd in words:
        if len(line) + len(wd) > 46:
            o.append(f'<text x="464" y="{ly2}" font-size="11" fill="{MUTED}">{esc(line)}</text>'); ly2 += 14; line = ""
        line += ("" if not line else " ") + wd
    o.append(f'<text x="464" y="{ly2}" font-size="11" fill="{MUTED}">{esc(line)}</text>')
o.append("</svg>"); (OUT / "cluster_map.svg").write_text("\n".join(o))

# ---------------- 5. crop price clusters scatter
pc = pd.read_csv(RP / "crop_price_clusters.csv")
CORE = set(pd.read_csv(REPO / "crosswalks/commodity_crosswalk.csv")["agmarknet_commodity"])
LABEL = {"Wheat", "Paddy(Common)", "Rice", "Maize", "Cotton", "Mustard", "Soyabean", "Onion", "Tomato", "Potato", "Garlic", "Banana", "Mango", "Coriander(Leaves)", "Cauliflower", "Turmeric", "Dry Chillies", "Green Gram(Moong)(Whole)", "Apple", "Coconut"}
SH = {"Paddy(Common)": "Paddy", "Bajra(Pearl Millet/Cumbu)": "Bajra", "Jowar(Sorghum)": "Jowar", "Ragi(Finger Millet)": "Ragi", "Bengal Gram(Gram)(Whole)": "Chana",
      "Red gram/Arhar/Tur(whole)": "Tur", "Green Gram(Moong)(Whole)": "Moong", "Black Gram(Urd Beans)(Whole)": "Urad", "Lentil(Masur)(Whole)": "Masur",
      "Soyabean": "Soybean", "Dry Chillies": "Dry chilli", "Cummin Seed(Jeera)": "Jeera"}
W, H = 720, 556; x0, x1, y0, y1 = 70, 700, 20, 470
lx = lambda v: x0 + (math.log10(max(v, 0.012) * 100) - math.log10(1.2)) / (math.log10(60) - math.log10(1.2)) * (x1 - x0)
ly_ = lambda v: y1 - (math.log10(min(max(v, 0.04), 20) * 100) - math.log10(4)) / (math.log10(2000) - math.log10(4)) * (y1 - y0)
_g = pc.groupby("price_cluster").agg(move=("typical_monthly_move", "median"), peak=("peak_month_share", "median"))
_order = _g.sort_values("move", ascending=False).index.tolist()           # most volatile first
_steady = _g.loc[_order[2:]].sort_values("peak").index.tolist()            # of the two calm clusters: spread-out arrivals first
PCC = {_order[0]: "#c92a2a", _order[1]: "#e8590c", _steady[0]: "#2b8a3e", _steady[1]: "#1c6e8c"}
PNAME = {_order[0]: "very volatile perishables", _order[1]: "volatile vegetables", _steady[0]: "steady, traded year-round", _steady[1]: "harvest-bunched field crops"}
o = svg_open(W, H, "Scatter of 23 crops by typical monthly price move and seasonal price spread, coloured by k-means cluster. Vegetables form a separate high-volatility, high-seasonality cluster.")
for t in (2, 5, 10, 20, 50):
    X = lx(t / 100); o.append(f'<line x1="{X:.0f}" y1="{y0}" x2="{X:.0f}" y2="{y1}" stroke="{GRID}"/><text x="{X:.0f}" y="{y1+16}" font-size="12" fill="{MUTED}" text-anchor="middle">{t}%</text>')
for t in (10, 30, 100, 300, 1000):
    Y = ly_(t / 100); o.append(f'<line x1="{x0}" y1="{Y:.0f}" x2="{x1}" y2="{Y:.0f}" stroke="{GRID}"/><text x="{x0-6}" y="{Y+4:.0f}" font-size="12" fill="{MUTED}" text-anchor="end">{t}%</text>')
o.append(f'<text x="{(x0+x1)/2}" y="{y1+34}" font-size="12.5" fill="#495057" text-anchor="middle">Typical monthly price move (log scale)</text>')
o.append(f'<text x="16" y="{(y0+y1)/2}" font-size="12.5" fill="#495057" text-anchor="middle" transform="rotate(-90 16 {(y0+y1)/2})">Seasonal spread, dearest vs cheapest month (log)</text>')
boxes = []
def free(b): return all(b[2] < c[0] or b[0] > c[2] or b[3] < c[1] or b[1] > c[3] for c in boxes)
for r in pc.itertuples():
    o.append(f'<circle cx="{lx(r.typical_monthly_move):.1f}" cy="{ly_(r.seasonal_spread):.1f}" r="3.2" fill="{PCC[int(r.price_cluster)]}" fill-opacity="0.45"/>')
pts = [(SH.get(r.commodity, r.commodity).replace("(Leaves)", " leaves"), lx(r.typical_monthly_move), ly_(r.seasonal_spread), int(r.price_cluster)) for r in pc.itertuples() if r.commodity in LABEL]
for n, X, Y, c in pts: boxes.append((X - 4, Y - 4, X + 4, Y + 4))
for n, X, Y, c in pts:
    w = len(n) * 6.6; o.append(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="5" fill="{PCC[c]}" stroke="#ffffff" stroke-width="0.8"/>')
    for dx, dy, anc in ((8, 4, "start"), (-8, 4, "end"), (8, -8, "start"), (-8, -8, "end"), (8, 15, "start"), (-8, 15, "end"), (0, -10, "middle"), (0, 18, "middle"), (18, -20, "start"), (-18, -20, "end"), (18, 28, "start"), (-18, 28, "end"), (30, -34, "start"), (-30, -34, "end"), (30, 40, "start"), (-30, 40, "end")):
        tx = X + dx; bx = tx if anc == "start" else tx - w if anc == "end" else tx - w / 2; b = (bx - 1, Y + dy - 11, bx + w + 1, Y + dy + 2)
        if free(b) and b[0] > x0 and b[2] < W - 2 and b[1] > y0 - 4 and b[3] < y1: break
    boxes.append(b)
    if abs(dy) > 16:
        o.append(f'<line x1="{X:.1f}" y1="{Y:.1f}" x2="{tx:.1f}" y2="{Y+dy-4 if dy > 0 else Y+dy+3:.1f}" stroke="{PCC[c]}" stroke-width="0.8"/>')
    o.append(f'<text x="{tx:.1f}" y="{Y+dy:.1f}" font-size="12" fill="{PCC[c]}" text-anchor="{anc}">{esc(n)}</text>')
for i, c in enumerate([_order[0], _order[1], _steady[1], _steady[0]]):
    lgx, lgy = x0 + (i % 2) * 300, H - 30 + (i // 2) * 18
    o.append(f'<circle cx="{lgx+6}" cy="{lgy-4}" r="5" fill="{PCC[c]}"/><text x="{lgx+15}" y="{lgy}" font-size="12" fill="#495057">{PNAME[c]}</text>')
o.append("</svg>"); (OUT / "price_clusters.svg").write_text("\n".join(o))
json.dump({"pcc": {int(k): v for k, v in PCC.items()}, "pname": {int(k): v for k, v in PNAME.items()},
           "stats": pc.groupby("price_cluster").agg(n=("commodity", "size"), move=("typical_monthly_move", "median"), spread=("seasonal_spread", "median"), peak=("peak_month_share", "median")).reset_index().to_dict("records")},
          open(OUT / "price_cluster_meta.json", "w"))

# ---------------- 6/7. seasonality heatmap (all-India seasonal index) + median prices
v = pd.read_csv(RP / "volatility_seasonality.csv"); v = v[v["state"] == "All India"]
m = pd.read_csv(D / "agmarknet/state_monthly.csv.gz"); m["arrivals_t"] = pd.to_numeric(m["arrivals_t"], errors="coerce"); m["price_rs_qtl"] = pd.to_numeric(m["price_rs_qtl"], errors="coerce")
m = m[(m["arrivals_t"] >= 50) & m["price_rs_qtl"].notna()]; m["pa"] = m["price_rs_qtl"] * m["arrivals_t"]
a2 = m.groupby(["commodity", "month"]).agg(pa=("pa", "sum"), t=("arrivals_t", "sum")).reset_index(); a2["p"] = a2["pa"] / a2["t"]
a2["mo"] = a2["month"].str[5:].astype(int); a2["yr"] = a2["month"].str[:4].astype(int); a2 = a2[(a2["yr"] >= 2019) & (a2["yr"] <= 2025)]
keep = [c for c in v.sort_values("seasonal_spread", ascending=False)["commodity"] if c in set(a2["commodity"]) and c in CORE][:23]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
cw, ch, lx0, top = 46, 22, 96, 40; W = lx0 + 12 * cw + 10; H = top + len(keep) * ch + 40
def colr(x):
    x = max(0.8, min(1.2, x))
    if x < 1: t = (1 - x) / .2; a, b = (255, 255, 255), (43, 138, 62)
    else: t = (x - 1) / .2; a, b = (255, 255, 255), (201, 42, 42)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)), t > .55
o = svg_open(W, H, "Heatmap of the all-India seasonal price index by crop and calendar month, 2019 to 2025. Vegetables swing most: tomato and onion are cheapest in spring and dearest in late summer and autumn. Grains and pulses vary within a few percent.", 560)
for j, mname in enumerate(MON): o.append(f'<text x="{lx0+j*cw+cw/2-1}" y="{top-10}" font-size="12" fill="#495057" text-anchor="middle">{mname}</text>')
for i, c in enumerate(keep):
    g = a2[a2["commodity"] == c]; idx = g.groupby("mo")["p"].mean() / g["p"].mean(); y = top + i * ch
    o.append(f'<text x="{lx0-8}" y="{y+15}" font-size="12" fill="{INK}" text-anchor="end">{esc(SH.get(c, c))}</text>')
    for j in range(12):
        val = idx.get(j + 1)
        if val is None: continue
        bg, dark = colr(val); o.append(f'<rect x="{lx0+j*cw}" y="{y}" width="{cw-2}" height="{ch-2}" fill="{bg}"/>')
        o.append(f'<text x="{lx0+j*cw+cw/2-1}" y="{y+14}" font-size="10.5" text-anchor="middle" fill="{"#ffffff" if dark else INK}">{val:.2f}</text>')
lyy = top + len(keep) * ch + 16
o.append(f'<rect x="{lx0}" y="{lyy}" width="14" height="14" fill="#2b8a3e"/><text x="{lx0+20}" y="{lyy+12}" font-size="12" fill="#495057">cheaper than the crop\'s average month</text>')
o.append(f'<rect x="{lx0+270}" y="{lyy}" width="14" height="14" fill="#c92a2a"/><text x="{lx0+290}" y="{lyy+12}" font-size="12" fill="#495057">dearer</text></svg>')
(OUT / "season_heat.svg").write_text("\n".join(o))

med = v[v["commodity"].isin(CORE)][["commodity", "median_price_last12m", "typical_monthly_move", "seasonal_spread", "cheapest_month", "dearest_month", "arrivals_last12m_t"]].copy()
med["commodity"] = med["commodity"].map(lambda c: SH.get(c, c))
med.sort_values("arrivals_last12m_t", ascending=False).to_csv(OUT / "median_prices.csv", index=False)
print("charts:", sorted(p.name for p in OUT.iterdir()), {p.name: p.stat().st_size for p in OUT.glob("*.svg")})

# ---------------- 8. urea intensity vs food-grain yield (earlier post's DoF data + UPAG yields + clusters)
u = pd.read_csv(REPO / "data/external/urea_state_2025_26.csv")
fy = apy[(apy["Crop"] == "Total Food Grains") & (apy["Metric"] == "Yield") & (apy["Crop Year"] == LASTLAB)].groupby("State")["Value"].first()
fp = apy[(apy["Crop"] == "Total Food Grains") & (apy["Metric"] == "Production") & (apy["Crop Year"] == LASTLAB)].groupby("State")["Value"].first()
u["fg_yield"] = u["state"].map(fy); u["grain_t_per_t_urea"] = u["state"].map(fp) / u["urea_sales_lmt"]
u["cluster"] = u["state"].map(dict(zip(cl["State"], cl["cluster"])))
u.to_csv(OUT / "urea_vs_yield.csv", index=False)
W, H = 720, 470; x0, x1, y0, y1 = 70, 700, 20, 410
X = lambda v: x0 + (v - 0) / 420 * (x1 - x0); Y = lambda v: y1 - (v - 1000) / (4800 - 1000) * (y1 - y0)
r = np.corrcoef(u["urea_kg_per_ha"], u["fg_yield"])[0, 1]
o = svg_open(W, H, f"Scatter of 18 states: urea per hectare of cropped land in 2025-26 against food-grain yield in {LASTLAB}, coloured by crop-mix cluster. Punjab, Haryana and Bihar use the most urea and Punjab has the highest yield; correlation {r:.2f}.")
for t in range(0, 421, 100):
    o.append(f'<line x1="{X(t):.0f}" y1="{y0}" x2="{X(t):.0f}" y2="{y1}" stroke="{GRID}"/><text x="{X(t):.0f}" y="{y1+16}" font-size="12" fill="{MUTED}" text-anchor="middle">{t}</text>')
for t in range(1000, 4801, 1000):
    o.append(f'<line x1="{x0}" y1="{Y(t):.0f}" x2="{x1}" y2="{Y(t):.0f}" stroke="{GRID}"/><text x="{x0-6}" y="{Y(t)+4:.0f}" font-size="12" fill="{MUTED}" text-anchor="end">{t:,}</text>')
o.append(f'<text x="{(x0+x1)/2}" y="{y1+36}" font-size="12.5" fill="#495057" text-anchor="middle">Urea per hectare of cropped land, 2025-26 (kg)</text>')
o.append(f'<text x="16" y="{(y0+y1)/2}" font-size="12.5" fill="#495057" text-anchor="middle" transform="rotate(-90 16 {(y0+y1)/2})">Food-grain yield {LASTLAB} (kg/ha)</text>')
boxes = []
pts = [(row.state, X(row.urea_kg_per_ha), Y(row.fg_yield), int(row.cluster) if pd.notna(row.cluster) else 0) for row in u.itertuples()]
for n, px, py, c in pts: boxes.append((px - 4, py - 4, px + 4, py + 4))
for n, px, py, c in pts:
    col = CC.get(c, MUTED); w = len(n) * 6.6
    o.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5.5" fill="{col}" stroke="#ffffff" stroke-width="0.8"/>')
    for dx, dy, anc in ((8, 4, "start"), (-8, 4, "end"), (8, -8, "start"), (-8, -8, "end"), (8, 15, "start"), (-8, 15, "end"), (0, -11, "middle"), (0, 19, "middle"), (18, -20, "start"), (-18, -20, "end"), (18, 28, "start"), (-18, 28, "end")):
        tx = px + dx; bx = tx if anc == "start" else tx - w if anc == "end" else tx - w / 2; b = (bx - 1, py + dy - 11, bx + w + 1, py + dy + 2)
        if free(b) and b[0] > x0 and b[2] < W - 2 and b[1] > y0 - 4 and b[3] < y1: break
    boxes.append(b)
    if abs(dy) > 16: o.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{tx:.1f}" y2="{py+dy-4 if dy > 0 else py+dy+3:.1f}" stroke="{col}" stroke-width="0.8"/>')
    o.append(f'<text x="{tx:.1f}" y="{py+dy:.1f}" font-size="11.5" fill="{INK}" text-anchor="{anc}">{esc(n)}</text>')
lx2 = x0
for c in sorted(set(u["cluster"].dropna().astype(int))):
    o.append(f'<circle cx="{lx2+6}" cy="{H-12}" r="5.5" fill="{CC[int(c)]}"/><text x="{lx2+15}" y="{H-8}" font-size="12" fill="#495057">Cluster {int(c)}</text>'); lx2 += 100
o.append(f'<text x="{W-8}" y="{H-8}" font-size="12" fill="#495057" text-anchor="end">correlation {r:.2f}</text></svg>')
(OUT / "urea_yield.svg").write_text("\n".join(o))
print("urea corr", round(r, 3))
