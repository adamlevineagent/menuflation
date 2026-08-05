"""dashboard.py — self-contained HTML dashboard from the price DB.

Emits data/reports/dashboard.html: dark theme, Chart.js (CDN) line charts for
dated price series, per-place stats, budget meter. Open in any browser.

Usage: python dashboard.py
"""
import json
import os
import sqlite3
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from menuflation import index  # noqa: E402
from menuflation.extract.qwen_vision import check_key  # noqa: E402

OUT = os.path.join("data", "reports", "dashboard.html")


def _row(r):
    return {k: r[k] for k in r.keys()}


def load(conn):
    places = [_row(r) for r in conn.execute(
        "SELECT id, name, city, state, address, lat, lng, tier, price_level "
        "FROM places")]
    lines = [_row(r) for r in conn.execute(
        "SELECT ci.name item, pl.name place, pl.city, pl.state, "
        "pl.tier tier, m.observed_on obs, m.price price, m.date_source src, "
        "m.notes, m.size "
        "FROM menu_lines m "
        "JOIN canonical_items ci ON ci.id=m.canonical_id "
        "JOIN places pl ON pl.id=m.place_id "
        "ORDER BY ci.name, pl.name, m.observed_on")]
    return places, lines


DATED_SOURCES = ("exif", "dom", "wayback", "pdf", "web")


def series_for_charts(lines):
    """[(item, place, city, state, src, [(date, price)...])] for dated items."""
    buckets = {}
    for l in lines:
        if l["src"] not in DATED_SOURCES:
            continue
        key = (l["item"], l["place"], l["city"], l["state"], l["src"])
        buckets.setdefault(key, []).append((l["obs"], l["price"]))
    out = []
    for key, pts in sorted(buckets.items()):
        pts.sort()
        # dedupe same-date medians
        agg = {}
        for d, p in pts:
            agg.setdefault(d, []).append(p)
        series = [(d, round(statistics.median(v), 2)) for d, v in sorted(agg.items())]
        out.append({"item": key[0], "place": key[1], "city": key[2],
                    "state": key[3], "src": key[4], "points": series})
    return out


def build(conn):
    places, lines = load(conn)
    series = series_for_charts(lines)
    n_exif = sum(1 for l in lines if l["src"] in DATED_SOURCES)
    # place stats
    pstats = []
    for p in places:
        pl = [l for l in lines if l["place"] == p["name"]]
        if not pl:
            continue
        med = statistics.median(l["price"] for l in pl)
        span = (min(l["obs"] for l in pl), max(l["obs"] for l in pl))
        pstats.append({**p, "items": len(pl), "median": round(med, 2),
                       "from": span[0], "to": span[1]})
    pstats.sort(key=lambda x: x["median"])
    key = check_key()
    budget = {"usage": round(key.get("usage", 0), 4),
              "limit": key.get("limit", 10)} if key.get("ok") else {"usage": 0, "limit": 10}

    payload = {
        "stats": {"places": len(places), "photos": len({l["item"] for l in lines}) and None,
                  "menus": len({(l["place"], l["obs"]) for l in lines}),
                  "lines": len(lines), "dated": n_exif, "undated": len(lines) - n_exif},
        "budget": budget,
        "series": series,
        "lines": lines,
        "places": pstats,
        "aggregate": index.aggregate_index(conn),
        "coverage": index.coverage_matrix(conn),
        "yoy": index.yoy_change(index.price_series(conn)),
        "averages": index.item_averages(conn, min_records=5),
        "families": index.family_averages(conn, min_records=5),
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"dashboard -> {OUT}  ({os.path.getsize(OUT)//1024}KB)")
    return OUT


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>menuflation — price index from menu photos</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#0b0f14;--panel:#111823;--line:#1e2a3a;--tx:#e6edf3;--dim:#8b98a9;
--acc:#58d68d;--amb:#f2c94c;--red:#e74c3c;--mono:ui-monospace,'Cascadia Code',Consolas,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font:14px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif;padding:28px}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:22px;letter-spacing:.4px}
h1 small{color:var(--dim);font-weight:400;font-size:13px;margin-left:10px}
.sub{color:var(--dim);margin:6px 0 22px;font-size:13px}
.grid{display:grid;gap:14px;margin-bottom:22px}
.cards{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card .k{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.8px}
.card .v{font-size:24px;font-weight:650;margin-top:4px;font-family:var(--mono)}
.card .v.acc{color:var(--acc)} .card .v.amb{color:var(--amb)}
.card .v small{font-size:12px;color:var(--dim);font-weight:400}
h2{font-size:15px;margin:26px 0 12px;color:var(--tx);letter-spacing:.3px}
h2 .n{color:var(--dim);font-weight:400}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
.chartgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:14px}
.chartcard{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.chartcard h3{font-size:13px;font-weight:600}
.chartcard .pl{color:var(--dim);font-size:12px;margin-bottom:8px}
.chartcard .yoy{display:inline-block;font-family:var(--mono);font-size:12px;padding:2px 8px;
border-radius:99px;margin-left:8px}
.yoy.up{background:rgba(231,76,60,.12);color:var(--red)}
.yoy.flat{background:rgba(139,152,169,.12);color:var(--dim)}
.yoy.down{background:rgba(88,214,141,.12);color:var(--acc)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:var(--dim);text-align:left;font-weight:500;font-size:11px;text-transform:uppercase;
letter-spacing:.7px;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:7px 10px;border-bottom:1px solid rgba(30,42,58,.5)}
tr:hover td{background:rgba(88,214,141,.04)}
td.px{font-family:var(--mono)} td.dim{color:var(--dim)} td.acc{color:var(--acc)}
.tag{display:inline-block;font-size:10px;padding:1px 7px;border-radius:99px;border:1px solid var(--line);color:var(--dim)}
.tag.exif{color:var(--acc);border-color:rgba(88,214,141,.4)}
.budgetbar{height:6px;background:var(--line);border-radius:99px;overflow:hidden;margin-top:6px}
.budgetbar>div{height:100%;background:var(--acc);border-radius:99px}
.foot{color:var(--dim);font-size:12px;margin-top:26px;text-align:center}
</style>
</head>
<body><div class="wrap">
<h1>menuflation<small>real food-price inflation, from Google Maps menu photos</small></h1>
<div class="sub">Grants Pass OR · Napa CA · Burgerville statewide · qwen3.7-flash extraction · EXIF-dated observations</div>

<div class="grid cards" id="cards"></div>

<div class="panel" id="filters">
  <label>City <select id="fCity"></select></label>
  <label>Tier <select id="fTier"></select></label>
  <label>Source <select id="fSrc"></select></label>
  <button id="fReset">reset</button>
</div>

<h2>Menuflation index <span class="n" id="aggN"></span></h2>
<div class="panel">
  <div id="aggEmpty" class="dim" style="display:none">No dated same-store pairs yet — the index needs 2+ dated observations of the same item at the same store (photos or Wayback).</div>
  <canvas id="aggChart" style="max-height:220px;display:none"></canvas>
  <table id="aggPairs" style="margin-top:14px"></table>
</div>

<h2>Dated price series <span class="n" id="seriesN"></span></h2>
<div class="chartgrid" id="charts"></div>

<h2>Universal averages — the cheeseburger average <span class="n" id="famN"></span></h2>
<div class="chartgrid" id="fams"></div>

<h2>Item averages — the emergent index <span class="n" id="avgN"></span></h2>
<div class="chartgrid" id="avgs"></div>

<h2>Same-store YoY <span class="n" id="yoyN"></span></h2>
<div class="panel"><table id="yoy"></table></div>

<h2>Dated coverage <span class="n" id="covN"></span></h2>
<div class="panel"><table id="cov"></table></div>

<h2>All priced lines <span class="n" id="linesN"></span></h2>
<div class="panel"><table id="lines"></table></div>

<h2>Places <span class="n" id="placesN"></span></h2>
<div class="panel"><table id="places"></table></div>

<div class="foot">menuflation · prices as read from menu photos · observations marked exif are
anchored to the photo's capture date; fallback rows are undated (cross-sectional only)</div>
</div>
<script>
const D = __DATA__;
const $ = (id) => document.getElementById(id);
const fmt = (n) => "$" + n.toFixed(2);

// cards
const cards = [
  ["places", D.stats.places, ""], ["priced lines", D.stats.lines, ""],
  ["exif-dated", D.stats.dated, "acc"], ["undated", D.stats.undated, "amb"],
  ["budget spent", D.budget.usage.toFixed(3), "", " of $" + D.budget.limit],
];
$("cards").innerHTML = cards.map(([k, v, cls, small]) =>
  `<div class="card"><div class="k">${k}</div><div class="v ${cls}">${v}<small>${small||""}</small></div></div>`).join("");

// aggregate menuflation index
const A = D.aggregate;
if (A.overall) {
  cards.unshift(["annualized rate", (A.overall.annualized*100).toFixed(1) + "%",
    A.overall.annualized > 0.001 ? "acc" : "amb", " /yr · " + A.overall.n_pairs + " pairs"]);
  $("cards").innerHTML = cards.map(([k, v, cls, small]) =>
    `<div class="card"><div class="k">${k}</div><div class="v ${cls}">${v}<small>${small||""}</small></div></div>`).join("");
}
$("aggN").textContent = A.overall ? `(median ratio · ${A.overall.from} → ${A.overall.to})` : "";
if (A.months.length) {
  $("aggChart").style.display = "block";
  new Chart($("aggChart"), {
    type: "bar",
    data: { labels: A.months.map(m => m.month),
      datasets: [{ data: A.months.map(m => m.index),
        backgroundColor: A.months.map(m => m.index >= 1 ? "rgba(231,76,60,.6)" : "rgba(88,214,141,.6)"),
        borderRadius: 4 }]},
    options: { plugins: { legend: { display: false },
      tooltip: { callbacks: { label: c => (c.parsed.y*100).toFixed(1) + "% (n=" + A.months[c.dataIndex].n + ")" } } },
      scales: { x: { ticks: { color: "#8b98a9" }, grid: { color: "#1e2a3a" } },
                y: { ticks: { color: "#8b98a9", callback: v => (v*100).toFixed(0) + "%" },
                     grid: { color: "#1e2a3a" } } } }
  });
  const pairs = [];
  A.months.forEach(m => m.items.forEach(it => pairs.push(Object.assign({}, it, { month: m.month }))));
  pairs.sort((a, b) => Math.abs(b.ratio - 1) - Math.abs(a.ratio - 1));
  $("aggPairs").innerHTML = `<tr><th>month</th><th>change</th><th>item</th><th>size</th><th>store</th></tr>` +
    pairs.map(p => `<tr><td class="px">${p.month}</td>
      <td class="px ${p.ratio >= 1 ? 'acc' : 'dim'}">${((p.ratio - 1) * 100).toFixed(1)}%</td>
      <td>${p.item}</td><td class="dim">${p.size || ""}</td><td>${p.place}</td></tr>`).join("");
} else {
  $("aggEmpty").style.display = "block";
}

// --- filters (criterion 5): city / tier / source ---
const F = { city: "all", tier: "all", src: "all" };
const FKEYS = { fCity: "city", fTier: "tier", fSrc: "src" };
function tierOf(place) { const p = D.places.find(x => x.name === place); return (p && p.tier) || "unknown"; }
function matches(l) {
  if (F.city !== "all" && l.city !== F.city) return false;
  if (F.tier !== "all" && (l.tier || tierOf(l.place)) !== F.tier) return false;
  if (F.src !== "all" && l.src !== F.src) return false;
  return true;
}
function fill(sel, vals) { $(sel).innerHTML = `<option value="all">all</option>` + vals.map(v => `<option>${v}</option>`).join(""); }
fill("fCity", [...new Set(D.lines.map(l => l.city).filter(Boolean))].sort());
fill("fTier", [...new Set(D.lines.map(l => l.tier || "unknown"))].sort());
fill("fSrc", [...new Set(D.lines.map(l => l.src))].sort());
let chartInstances = [];
function renderAll() {
  chartInstances.forEach(c => c.destroy());
  chartInstances = [];
  $("charts").innerHTML = "";
  renderCharts(D.series.filter(s => matches({ city: s.city, state: s.state, src: s.src, place: s.place, tier: tierOf(s.place) })));
  renderLines(D.lines.filter(matches));
}
Object.keys(FKEYS).forEach(id => $(id).addEventListener("change", () => { F[FKEYS[id]] = $(id).value; renderAll(); }));
$("fReset").addEventListener("click", () => { Object.keys(FKEYS).forEach(id => { $(id).value = "all"; F[FKEYS[id]] = "all"; }); renderAll(); });

// charts
function renderCharts(charts) {
$("seriesN").textContent = "(" + charts.length + ")";
const pal = ["#58d68d", "#f2c94c", "#5dade2", "#e74c3c", "#bb8fce", "#f0b27a"];
let ci = 0;
for (const s of charts) {
  const first = s.points[0][1], last = s.points[s.points.length-1][1];
  const pct = first ? ((last/first - 1) * 100) : 0;
  const cls = pct > 0.5 ? "up" : (pct < -0.5 ? "down" : "flat");
  const lbl = (pct > 0 ? "+" : "") + pct.toFixed(1) + "%";
  const el = document.createElement("div");
  el.className = "chartcard";
  el.innerHTML = `<h3>${s.item} <span class="yoy ${cls}">${lbl}</span></h3>
    <div class="pl">${s.place} · ${s.city}, ${s.state}</div>
    <canvas></canvas>`;
  $("charts").appendChild(el);
  chartInstances.push(new Chart(el.querySelector("canvas"), {
    type: "line",
    data: { labels: s.points.map(p => p[0]),
            datasets: [{ data: s.points.map(p => p[1]), borderColor: pal[ci++ % pal.length],
                         backgroundColor: "transparent", tension: .25, pointRadius: 4, borderWidth: 2 }]},
    options: { plugins: { legend: { display: false },
              tooltip: { callbacks: { label: c => fmt(c.parsed.y) } } },
              scales: { x: { ticks: { color: "#8b98a9" }, grid: { color: "#1e2a3a" } },
                        y: { ticks: { color: "#8b98a9", callback: v => "$" + v },
                             grid: { color: "#1e2a3a" } } } }
                        }));
                        }
}  // close renderCharts

// universal averages (family level: any cheeseburger counts)
$("famN").textContent = "(" + D.families.length + ")";
for (const a of D.families) {
  const el = document.createElement("div");
  el.className = "chartcard";
  el.innerHTML = `<h3>${a.family} <span class="tag exif">average</span></h3>
    <div class="pl">${a.total} records · ${a.places} places · median price per year, all stores</div>
    <canvas></canvas>`;
  $("fams").appendChild(el);
  new Chart(el.querySelector("canvas"), {
    type: "line",
    data: { labels: a.series.map(s => s.year),
      datasets: [{ data: a.series.map(s => s.median), borderColor: pal[ci++ % pal.length],
        backgroundColor: "transparent", tension: .25, pointRadius: 4, borderWidth: 2 }]},
    options: { plugins: { legend: { display: false },
      tooltip: { callbacks: { label: c => fmt(c.parsed.y) + " (n=" + a.series[c.dataIndex].n + ")" } } },
      scales: { x: { ticks: { color: "#8b98a9" }, grid: { color: "#1e2a3a" } },
                y: { ticks: { color: "#8b98a9", callback: v => "$" + v }, grid: { color: "#1e2a3a" } } } }
  });
}

// item averages (emergent: any item with enough dated records)
$("avgN").textContent = "(" + D.averages.length + ")";
for (const a of D.averages) {
  const el = document.createElement("div");
  el.className = "chartcard";
  el.innerHTML = `<h3>${a.item}</h3>
    <div class="pl">${a.total} records · ${a.places} places · median price per year across stores</div>
    <canvas></canvas>`;
  $("avgs").appendChild(el);
  new Chart(el.querySelector("canvas"), {
    type: "line",
    data: { labels: a.series.map(s => s.year),
      datasets: [{ data: a.series.map(s => s.median), borderColor: pal[ci++ % pal.length],
        backgroundColor: "transparent", tension: .25, pointRadius: 4, borderWidth: 2 }]},
    options: { plugins: { legend: { display: false },
      tooltip: { callbacks: { label: c => fmt(c.parsed.y) + " (n=" + a.series[c.dataIndex].n + ")" } } },
      scales: { x: { ticks: { color: "#8b98a9" }, grid: { color: "#1e2a3a" } },
                y: { ticks: { color: "#8b98a9", callback: v => "$" + v }, grid: { color: "#1e2a3a" } } } }
  });
}

// same-store YoY
$("yoyN").textContent = "(" + D.yoy.length + ")";
$("yoy").innerHTML = `<tr><th>item</th><th>size</th><th>store</th><th>from</th><th>to</th><th>change</th></tr>` +
  D.yoy.map(y => `<tr><td>${y.item}</td><td class="dim">${y.size || ""}</td><td>${y.place}</td>
    <td class="px">${y.from} ${fmt(y.from_price)}</td><td class="px">${y.to} ${fmt(y.to_price)}</td>
    <td class="px ${y.pct > 0.5 ? 'acc' : (y.pct < -0.5 ? 'dim' : '')}">${y.pct > 0 ? '+' : ''}${y.pct}%</td></tr>`).join("");

// dated coverage matrix (places x years)
const C = D.coverage;
$("covN").textContent = "(" + Object.keys(C.matrix).length + " places)";
$("cov").innerHTML = `<tr><th>place</th>${C.years.map(y => `<th>${y}</th>`).join("")}</tr>` +
  Object.entries(C.matrix).map(([name, yrs]) =>
    `<tr><td>${name}</td>${C.years.map(y => `<td class="px">${yrs[y] || "·"}</td>`).join("")}</tr>`).join("");

// lines table
function renderLines(rows) {
$("linesN").textContent = "(" + rows.length + ")";
$("lines").innerHTML = `<tr><th>item</th><th>place</th><th>city</th><th>observed</th><th>price</th><th>src</th><th>notes</th></tr>` +
  rows.map(l => `<tr><td>${l.item}</td><td>${l.place}</td><td class="dim">${l.city}</td>
    <td class="px">${l.obs}</td><td class="px acc">${fmt(l.price)}</td>
    <td><span class="tag ${l.src}">${l.src}</span></td><td class="dim">${l.notes||""} ${l.size||""}</td></tr>`).join("");
}
renderAll();

// places
$("placesN").textContent = "(" + D.places.length + ")";
$("places").innerHTML = `<tr><th>place</th><th>city</th><th>items</th><th>median price</th><th>dated span</th></tr>` +
  D.places.map(p => `<tr><td>${p.name}</td><td class="dim">${p.city}, ${p.state}</td>
    <td>${p.items}</td><td class="px acc">${fmt(p.median)}</td>
    <td class="px dim">${p.from} → ${p.to}</td></tr>`).join("");
</script>
</body></html>
"""


def main():
    from menuflation import db
    conn = db.connect()
    build(conn)


if __name__ == "__main__":
    main()
