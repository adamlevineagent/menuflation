"""audit.py — data-quality audit of the menuflation DB + extractions.

Flags, in priority order:
  1. same-item adjacent price jumps >50% (misreads / size mismatches / errors)
  2. suspicious extractions: is_menu with <3 items, no currency, weird names
  3. canonical names that look like extraction garbage (length, 'add ', 'with choice')
  4. price outliers vs the place's own median
  5. size strings carrying portion words (the known size-mangling pattern)

Read-only. Prints a prioritized report; fixing is a separate step.
Usage: python audit.py
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from menuflation import db, index  # noqa: E402

JUMP = 0.50       # adjacent same-item change > 50% = suspicious
MIN_ITEMS = 3     # a real menu has >= 3 priced lines
GARBAGE = ("with choice", "add ", "choose ", "or ")
PORTION = ("double", "triple", "quarter", "meal", "basket", "side", "combo",
           "large", "small", "medium", "regular", "kids", "child")


def main():
    conn = db.connect()
    issues = []

    # 1. adjacent price jumps on same (item, size, place)
    by_key = defaultdict(list)
    for s in index.price_series(conn):
        if s.get("date_source") == "fallback":
            continue
        by_key[(s["item"], s["size"], s["place"])].append(s)
    for key, pts in by_key.items():
        pts.sort(key=lambda x: x["observed_on"])
        for a, b in zip(pts, pts[1:]):
            if a["median"] and b["median"]:
                pct = b["median"] / a["median"] - 1
                if abs(pct) > JUMP:
                    issues.append(
                        ("jump", f"{key[2][:22]} | {key[0][:24]} [{key[1] or ''}] "
                                 f"{a['observed_on']} ${a['median']} -> "
                                 f"{b['observed_on']} ${b['median']} "
                                 f"({pct*100:+.0f}%)"))

    # 2. suspicious extractions
    n_menus = n_weak = n_nocur = 0
    for jf in sorted(__import__("glob").glob(
            os.path.join("data", "extractions", "**", "*.json"), recursive=True)):
        try:
            p = json.load(open(jf, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        r = p.get("result") or {}
        if not r.get("is_menu"):
            continue
        n_menus += 1
        items = r.get("items") or []
        if len(items) < MIN_ITEMS:
            n_weak += 1
            issues.append(("weak-menu", f"{os.path.basename(jf)[:44]} "
                                        f"({len(items)} items)"))
        if not r.get("currency_iso"):
            n_nocur += 1
            issues.append(("no-currency", os.path.basename(jf)[:44]))
        for it in items:
            n = it.get("name") or ""
            if len(n) > 44 or any(g in n.lower() for g in GARBAGE):
                issues.append(("name", f"'{n[:60]}' ({os.path.basename(jf)[:32]})"))
                break
            sz = it.get("size") or ""
            if sz and any(w in sz.lower() for w in PORTION):
                issues.append(("size", f"'{n[:40]}' size='{sz}' ({os.path.basename(jf)[:32]})"))
                break

    # 3. price outliers vs place median (Python-side median)
    import statistics

    places = {r["id"]: r["name"]
              for r in conn.execute("SELECT id, name FROM places")}
    place_prices = defaultdict(list)
    for r in conn.execute("SELECT place_id, price FROM menu_lines WHERE price > 0"):
        place_prices[r["place_id"]].append(r["price"])
    place_med = {pid: statistics.median(v) for pid, v in place_prices.items()}
    for r in conn.execute(
            "SELECT place_id, item_raw, price FROM menu_lines WHERE price > 0"):
        pid, name, price = r
        med = place_med.get(pid)
        if med and (price > 6 * med or price < 0.2 * med):
            issues.append(("outlier", f"{places.get(pid, '?')[:22]} "
                                      f"'{name[:30]}' ${price} vs median ${med:.2f}"))

    # report
    counts = defaultdict(int)
    for kind, _ in issues:
        counts[kind] += 1
    print(f"menus classified: {n_menus} | weak (<{MIN_ITEMS} items): {n_weak} "
          f"| no-currency: {n_nocur}")
    print("issue counts:", dict(counts))
    for kind in ("jump", "weak-menu", "no-currency", "name", "size", "outlier"):
        hits = [t for k, t in issues if k == kind]
        if hits:
            print(f"\n--- {kind} ({len(hits)}) ---")
            for h in hits[:12]:
                print(f"  {h}")


if __name__ == "__main__":
    main()
