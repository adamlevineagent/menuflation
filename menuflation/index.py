"""index.py — price series, comparisons, and report generation.

Time axis: menu_lines.observed_on is the photo's upload date when known, else
the extraction date. Until the date seam is wired (upload dates from the Maps
UI), everything is a same-day baseline — so the cross-sectional report is the
primary output, and the YoY machinery is built and tested against dated data.
"""
import csv
import datetime
import json
import math
import os
import statistics
from collections import defaultdict


def price_series(conn, canonical_id=None, place_id=None):
    """[(observed_on, median_price, n)] per (canonical, place, size), sorted.

    Size-aware: menu lines with a size (S/M/L, 12oz, 1/2lb...) are keyed by
    canonical+size so price movements compare like-for-like — a $3.99 corn
    dog variant must not masquerade as inflation of the $2.99 corn dog.
    """
    q = ("SELECT ci.name, pl.name, COALESCE(m.size, '') sz, m.observed_on, "
         "m.price, m.date_source src, m.id "
         "FROM menu_lines m "
         "JOIN canonical_items ci ON ci.id=m.canonical_id "
         "JOIN places pl ON pl.id=m.place_id "
         "WHERE m.canonical_id IS NOT NULL")
    args = []
    if canonical_id:
        q += " AND m.canonical_id=?"
        args.append(canonical_id)
    if place_id:
        q += " AND m.place_id=?"
        args.append(place_id)
    q += " ORDER BY m.observed_on"
    buckets = defaultdict(list)
    for canon, place, sz, obs, price, src, _ in conn.execute(q, args):
        buckets[(canon, place, sz, obs)].append((price, src))
    out = []
    for (canon, place, sz, obs), vals in sorted(buckets.items()):
        prices = [v[0] for v in vals]
        out.append({"item": canon, "size": sz or None, "place": place,
                    "observed_on": obs, "date_source": vals[0][1],
                    "median": round(statistics.median(prices), 2),
                    "n": len(prices)})
    return out


def yoy_change(series, lookback_days=365):
    """For each (item, size, place): pct change latest vs ~1y-earlier median."""
    by_key = defaultdict(list)
    for s in series:
        by_key[(s["item"], s["size"], s["place"])].append(s)
    out = []
    for (item, size, place), pts in by_key.items():
        if len(pts) < 2:
            continue
        pts.sort(key=lambda x: x["observed_on"])
        latest = pts[-1]
        ref = None
        for p in reversed(pts[:-1]):
            d1 = p["observed_on"]
            d2 = latest["observed_on"]
            try:
                days = (datetime.date.fromisoformat(d2)
                        - datetime.date.fromisoformat(d1)).days
            except ValueError:
                days = 9999
            if days >= lookback_days * 0.8:
                ref = p
                break
        if ref and ref["median"]:
            out.append({"item": item, "size": size, "place": place,
                        "from": ref["observed_on"], "to": latest["observed_on"],
                        "from_price": ref["median"], "to_price": latest["median"],
                        "pct": round((latest["median"] / ref["median"] - 1) * 100, 1),
                        "n": latest["n"]})
    return out


# Universal-item families for the emergent averages. The cheeseburger average
# counts ANY cheeseburger (grass-fed, bacon, whatever) — same-store discipline
# still keys on exact canonicals, but the people's index is about the
# experience: what did a cheeseburger cost this year?
_FRIES_STOP = {"sweet", "loaded", "garlic", "curly", "poutine", "truffle",
               "animal", "disco", "chili", "queso", "bbq", "buffalo", "cajun",
               "zucchini", "cheese", "carnitas", "tater", "potato"}


def item_family(name):
    """Universal family for an item name: 'cheeseburger', 'french fries', etc."""
    n = (name or "").lower()
    if "cheeseburger" in n or "cheese burger" in n:
        return "cheeseburger"
    toks = n.split()
    if toks and toks[-1] == "fries" and not any(s in n for s in _FRIES_STOP):
        return "french fries"
    return None


def family_averages(conn, min_records=5):
    """Emergent universal averages: per family per year, the median price
    across ALL dated records (any store, any source). The cheeseburger
    average. Groupings emerge; no basket is imposed."""
    rows = conn.execute(
        "SELECT ci.name, substr(m.observed_on,1,4) yr, m.price, pl.id "
        "FROM menu_lines m "
        "JOIN canonical_items ci ON ci.id=m.canonical_id "
        "JOIN places pl ON pl.id=m.place_id "
        "WHERE m.date_source IN ('exif','dom','wayback','pdf','web') "
        "AND length(m.observed_on) >= 7").fetchall()
    fam = defaultdict(lambda: defaultdict(list))
    pids = defaultdict(set)
    for name, yr, price, pid in rows:
        f = item_family(name)
        if not f:
            continue
        fam[f][yr].append(price)
        pids[f].add(pid)
    out = []
    for f, years in fam.items():
        total = sum(len(v) for v in years.values())
        if total < min_records:
            continue
        series = [{"year": y, "median": round(statistics.median(v), 2),
                   "n": len(v)} for y, v in sorted(years.items())]
        out.append({"family": f, "total": total, "places": len(pids[f]),
                    "series": series})
    out.sort(key=lambda x: -x["total"])
    return out


def item_averages(conn, min_records=5):
    """Emergent 'cheeseburger average' series: per canonical item, the median
    price per year across ALL stores (dated observations only).

    This is the LEVEL index — what a cheeseburger actually costs per year,
    experienced by people — as opposed to the same-store inflation index.
    Groupings emerge from the data: any item with enough records gets a
    series; no fixed basket is imposed.
    """
    rows = conn.execute(
        "SELECT ci.name, substr(m.observed_on,1,4) yr, m.price, pl.id "
        "FROM menu_lines m "
        "JOIN canonical_items ci ON ci.id=m.canonical_id "
        "JOIN places pl ON pl.id=m.place_id "
        "WHERE m.date_source IN ('exif','dom','wayback','pdf','web') "
        "AND length(m.observed_on) >= 7").fetchall()
    by_item = defaultdict(lambda: defaultdict(list))
    pids = defaultdict(set)
    for name, yr, price, pid in rows:
        by_item[name][yr].append(price)
        pids[name].add(pid)
    out = []
    for name, years in by_item.items():
        total = sum(len(v) for v in years.values())
        if total < min_records:
            continue
        series = [{"year": y,
                   "median": round(statistics.median(v), 2),
                   "n": len(v)}
                  for y, v in sorted(years.items())]
        out.append({"item": name, "total": total, "places": len(pids[name]),
                    "series": series})
    out.sort(key=lambda x: -x["total"])
    return out


def tier_rates(conn):
    """Per-tier price-movement summary: same-store pairs bucketed by the
    place's tier (expensive/moderate/inexpensive). Median ratio + span.

    The tier-divergence view: fancy vs fast-food inflate differently.
    """
    tiers = {r["name"]: r["tier"] or "unknown"
             for r in conn.execute("SELECT name, tier FROM places")}
    by_key = defaultdict(list)
    for s in price_series(conn):
        if s.get("date_source") == "fallback":
            continue
        by_key[(s["item"], s["size"], s["place"])].append(s)
    by_tier = defaultdict(list)
    for key, pts in by_key.items():
        pts.sort(key=lambda x: x["observed_on"])
        for a, b in zip(pts, pts[1:]):
            if a["median"] and b["median"]:
                by_tier[tiers.get(key[2], "unknown")].append(
                    (b["observed_on"], b["median"] / a["median"]))
    out = []
    for tier in ("inexpensive", "moderate", "expensive", "unknown"):
        pairs = by_tier.get(tier, [])
        if len(pairs) < 3:
            continue
        ratios = [r for _, r in pairs]
        med = round(statistics.median(ratios) * 100, 1)
        geo = round(math.exp(sum(math.log(r) for r in ratios) / len(ratios)) * 100, 1)
        span = (min(d for d, _ in pairs)[:7], max(d for d, _ in pairs)[:7])
        out.append({"tier": tier, "n_pairs": len(pairs), "median_ratio": med,
                    "geo_ratio": geo, "span": span})
    order = {"inexpensive": 0, "moderate": 1, "expensive": 2, "unknown": 3}
    out.sort(key=lambda t: order.get(t["tier"], 9))
    return out


def aggregate_index(conn, min_gap_days=180):
    """Chained menuflation index from dated same-store same-item series.

    Every (item, size, place) with 2+ dated observations contributes a price
    ratio per consecutive pair (only pairs >= min_gap_days apart, so
    same-day re-photographs don't masquerade as movement). Ratios are
    bucketed by observation month and combined with the geometric mean —
    a mini-CPI over our own menu data.

    Returns {"months": [{month, n, index, items:[...]}], "overall": {...}}
    (tier/city/source breakdowns are composed in the dashboard from the
    same series — see dashboard.py).
    """
    import datetime as _dt

    series = price_series(conn)
    by_key = defaultdict(list)
    for s in series:
        if s["date_source"] == "fallback":
            continue
        by_key[(s["item"], s["size"], s["place"])].append(s)
    pairs = []  # (month, ratio, item, size, place)
    for key, pts in by_key.items():
        pts.sort(key=lambda x: x["observed_on"])
        for a, b in zip(pts, pts[1:]):
            if not (a["median"] and b["median"]):
                continue
            try:
                gap = (_dt.date.fromisoformat(b["observed_on"])
                       - _dt.date.fromisoformat(a["observed_on"])).days
            except ValueError:
                gap = min_gap_days  # unparseable dates: count it
            if gap < min_gap_days:
                continue
            pairs.append((b["observed_on"][:7], b["median"] / a["median"],
                          key[0], key[2], key[1]))
    months = defaultdict(list)
    for month, r, item, place, size in pairs:
        months[month].append({"ratio": r, "item": item, "place": place,
                              "size": size})
    out = []
    for month in sorted(months):
        rs = [m["ratio"] for m in months[month]]
        # median ratio: robust — a single mismatched pair (e.g. a flavor
        # variant read as a size change) must not move the aggregate.
        geo = (math.exp(sum(math.log(r) for r in rs) / len(rs))
               if all(r > 0 for r in rs) else None)
        out.append({"month": month, "n": len(rs),
                    "index": round(statistics.median(rs), 4),
                    "geo": round(geo, 4) if geo else None,
                    "items": months[month]})
    overall = None
    if len(out) >= 2:
        first, last = out[0], out[-1]
        days = (_dt.date.fromisoformat(last["month"] + "-15")
                - _dt.date.fromisoformat(first["month"] + "-15")).days
        years = max(days / 365.25, 0.25)
        overall = {"from": first["month"], "to": last["month"],
                   "n_pairs": sum(m["n"] for m in out),
                   "annualized": round((last["index"] / first["index"])
                                       ** (1 / years) - 1, 4)}
    return {"months": out, "overall": overall}


def coverage_matrix(conn):
    """places x year counts of DATED observations — the temporal-depth map."""
    rows = conn.execute(
        "SELECT pl.name, substr(m.observed_on,1,4) yr, COUNT(*) "
        "FROM menu_lines m JOIN places pl ON pl.id=m.place_id "
        "WHERE m.date_source IN ('exif','dom','wayback','pdf','web') "
        "GROUP BY pl.name, yr").fetchall()
    years = sorted({r[1] for r in rows})
    matrix = {r[0]: {} for r in rows}
    for name, yr, n in rows:
        matrix[name][yr] = n
    return {"years": years, "matrix": matrix}


def cross_sectional(conn):
    """Median price per (canonical item, place) + place and chain stats."""
    series = price_series(conn)
    rows = []
    for s in series:
        rows.append(s)
    # place-level: median of item medians (a mini basket per place)
    place_med = defaultdict(list)
    for s in rows:
        place_med[s["place"]].append(s["median"])
    place_stats = [{"place": p, "items": len(v),
                    "median_item_price": round(statistics.median(v), 2)}
                   for p, v in place_med.items()]
    return {"series": rows, "place_stats": sorted(place_stats,
            key=lambda x: x["median_item_price"])}


def write_report(conn, out_dir="data/reports", name="report"):
    os.makedirs(out_dir, exist_ok=True)
    rep = cross_sectional(conn)
    json.dump(rep, open(os.path.join(out_dir, f"{name}.json"), "w",
                        encoding="utf-8"), indent=1, ensure_ascii=False)
    with open(os.path.join(out_dir, f"{name}_series.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["item", "size", "place",
                                          "observed_on", "date_source",
                                          "median", "n"])
        w.writeheader()
        # tolerant: only the declared columns, whatever else series carries
        w.writerows({k: s.get(k) for k in w.fieldnames} for s in rep["series"])
    with open(os.path.join(out_dir, f"{name}_places.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["place", "items", "median_item_price"])
        w.writeheader()
        w.writerows(rep["place_stats"])
    return rep
