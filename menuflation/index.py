"""index.py — price series, comparisons, and report generation.

Time axis: menu_lines.observed_on is the photo's upload date when known, else
the extraction date. Until the date seam is wired (upload dates from the Maps
UI), everything is a same-day baseline — so the cross-sectional report is the
primary output, and the YoY machinery is built and tested against dated data.
"""
import csv
import datetime
import json
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
         "m.price, m.id "
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
    for canon, place, sz, obs, price, _ in conn.execute(q, args):
        buckets[(canon, place, sz, obs)].append(price)
    out = []
    for (canon, place, sz, obs), prices in sorted(buckets.items()):
        out.append({"item": canon, "size": sz or None, "place": place,
                    "observed_on": obs,
                    "median": round(statistics.median(prices), 2), "n": len(prices)})
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
        w = csv.DictWriter(f, fieldnames=["item", "place", "observed_on",
                                          "median", "n"])
        w.writeheader()
        w.writerows(rep["series"])
    with open(os.path.join(out_dir, f"{name}_places.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["place", "items", "median_item_price"])
        w.writeheader()
        w.writerows(rep["place_stats"])
    return rep
