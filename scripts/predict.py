"""Prediction test v3: tier-matched family engine.

The aggregate median rate (0.94%/yr) under-predicts the burger shock because
the median is diluted by flat pairs (drinks, coffee). The perfection test's
right engine: same-TIER cheeseburger-family median ratio (Burgerville =
inexpensive tier), applied to the store's old price. Plus the item's own
historical drift (old pairs only, no capture leakage).
"""
import os, sqlite3, sys, math, argparse
sys.path.insert(0, os.getcwd())
from statistics import median
from collections import defaultdict

from menuflation.index import aggregate_index, price_series, item_family

ap = argparse.ArgumentParser(description="Perfection test (v3 tier-matched family engine)")
ap.add_argument("--place", default="ChIJL3qwyg-hlVQRK3LBcpuq72k",
                help="place_id to test (default: Burgerville Montavilla anchor)")
ap.add_argument("--capture", default=None,
                help="capture observation date (default: auto-detect the store's "
                     "latest dated observation)")
args = ap.parse_args()

ANCHOR = args.place
CAPTURE = args.capture

conn = sqlite3.connect("data/menuflation.db")
conn.row_factory = sqlite3.Row

if not CAPTURE:
    # Auto-detect the capture date: the store's most recent dated observation
    # (web/exif/etc.). Avoids the stale hardcoded-default trap where a store's
    # web capture is a day later than 2026-08-10 and every exact-date match
    # (`caps`) comes up empty, making a perfectly good pair untestable.
    row = conn.execute(
        "SELECT max(observed_on) d FROM menu_lines WHERE place_id=? "
        "AND length(observed_on)>=10",
        (ANCHOR,)).fetchone()
    CAPTURE = row["d"] if row and row["d"] else "2026-08-10"
    print(f"[auto] capture date -> {CAPTURE}")

def yrs(d1, d2):
    y1, m1 = map(int, d1.split("-")[:2])
    y2, m2 = map(int, d2.split("-")[:2])
    return (y2 - y1) + (m2 - m1) / 12.0

# ---- aggregate engines (A: median, B: geo) ----
agg = aggregate_index(conn)
med_ann = agg["overall"]["annualized"]
months = agg["months"]
y_agg = yrs(months[0]["month"] + "-15", months[-1]["month"] + "-15")
geo_ann = ((months[-1]["geo"] / months[0]["geo"]) ** (1 / y_agg) - 1
           if months[0]["geo"] and months[-1]["geo"] else None)
print(f"Aggregate: {len(months)} months / {agg['overall']['n_pairs']} pairs")
print(f"  A: median annualized {med_ann*100:.2f}%")
print(f"  B: geo annualized {geo_ann*100:.2f}%")

# anchor's tier (Burgerville = inexpensive)
tier = conn.execute("SELECT tier FROM places WHERE id=?", (ANCHOR,)).fetchone()[0]
if not tier:
    tier = conn.execute(
        "SELECT tier FROM places WHERE name='Burgerville' AND tier IS NOT NULL "
        "LIMIT 1").fetchone()[0]
print(f"Anchor tier: {tier}")

# tier-matched cheeseburger family medians per year
rows = conn.execute(
    """SELECT ci.name, substr(m.observed_on,1,4) yr, m.price, pl.tier
       FROM menu_lines m JOIN canonical_items ci ON ci.id=m.canonical_id
       JOIN places pl ON pl.id=m.place_id
       WHERE m.date_source IN ('exif','dom','wayback','pdf','web')
       AND length(m.observed_on) >= 7""").fetchall()
fam_years = defaultdict(list)
for name, yr, price, t in rows:
    if item_family(name) == "cheeseburger" and (t or "unknown") == tier:
        fam_years[yr].append(price)
fam_med = {y: median(v) for y, v in sorted(fam_years.items())}
print(f"Tier-matched ({tier}) cheeseburger family medians: {fam_med}")

# anchor canonical series
series = price_series(conn, place_id=ANCHOR)
by_key = defaultdict(list)
for s in series:
    by_key[(s["item"], s["size"])].append(s)
for k in by_key:
    by_key[k].sort(key=lambda x: x["observed_on"])

HERO = [("original cheeseburger", None),
        ("bacon cheeseburger", None),
        ("double beef cheeseburger", None),
        ("french fries", "Regular"),
        ("french fries", "Large")]
if ANCHOR != "ChIJL3qwyg-hlVQRK3LBcpuq72k":
    # Non-anchor store: auto-derive hero canonicals — >=2 pre-capture points
    # plus a capture point, ranked by pre-capture depth. Stores with only ONE
    # pre-capture observation (Five Guys Medford: 2023 board + 2026 web) can't
    # meet the >=2 bar, so fall back to >=1 — the E (tier-family) engine still
    # runs; F (own-rate) just has no pre-capture pairs to draw from.
    cands = []
    for (item, size), pts in by_key.items():
        olds = [p for p in pts if p["observed_on"] < CAPTURE[:4] + "-01-01"]
        caps = [p for p in pts if p["observed_on"] == CAPTURE]
        if len(olds) >= 1 and caps:
            cands.append((len(olds), item, size))
    cands.sort(reverse=True)
    HERO = [(i, s) for _, i, s in cands[:6]]
    if not HERO:
        print("No same-canonical pre-capture+capture items found — "
              "store has no dated pair to test.")
        sys.exit(0)

def item_own_rate(pts, cap_date=CAPTURE):
    """Annualized rate from the item's OWN pre-capture pairs (>=1yr gap)."""
    rs = []
    for a, b in zip(pts, pts[1:]):
        if b["observed_on"] == cap_date or a["observed_on"] == cap_date:
            continue
        y = yrs(a["observed_on"], b["observed_on"])
        if y >= 1.0 and a["median"] and b["median"]:
            rs.append((b["median"] / a["median"]) ** (1 / y) - 1)
    return median(rs) if rs else None

print(f"\n=== PERFECTION TEST ({CAPTURE}) — tier-matched engines ===\nstore: {ANCHOR}")
for item, size in HERO:
    pts = by_key.get((item, size), [])
    olds = [p for p in pts if p["observed_on"] < CAPTURE[:4] + "-01-01"]
    caps = [p for p in pts if p["observed_on"] == CAPTURE]
    if not olds or not caps:
        print(f"{item} ({size or 'ac'}): no same-canonical old+capture pair "
              f"(era-boundary naming) — {len(pts)} pts")
        continue
    old, cap = olds[0], caps[0]
    y = yrs(old["observed_on"], CAPTURE)
    actual = cap["median"]
    out = [f"{item} ({size or 'ac'}): {old['observed_on']} ${old['median']:.2f}"
           f" -> {CAPTURE} ${actual:.2f} ({(actual/old['median'])**(1/y)-1:.1%}/yr)"]
    # E: tier family ratio
    fy = old["observed_on"][:4]
    if fy in fam_med and "2026" in fam_med:
        pred = old["median"] * fam_med["2026"] / fam_med[fy]
        out.append(f"    E_tierfamily: ${pred:.2f} ({(pred/actual-1)*100:+.0f}% off)")
    # F: item's own pre-capture drift
    own = item_own_rate(pts)
    if own is not None:
        pred = old["median"] * (1 + own) ** y
        out.append(f"    F_ownrate ({own*100:+.1f}%/yr): ${pred:.2f} "
                   f"({(pred/actual-1)*100:+.0f}% off)")
    print("\n".join(out))

# The hero item full series
print(f"\nHero item full same-store series ({HERO[0][0]}):")
for p in by_key.get(HERO[0], []):
    print(f"  {p['observed_on']} ${p['median']:.2f} ({p['date_source']})")
