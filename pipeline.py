"""pipeline.py — ingest extractions -> SQLite -> match -> report.

Usage:
    python pipeline.py [--report-name NAME]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from menuflation import db, fx, index, match  # noqa: E402


def main():
    name = "report"
    argv = sys.argv[1:]
    if "--report-name" in argv:
        i = argv.index("--report-name")
        name = argv[i + 1]
    conn = db.connect()
    stats = db.ingest(conn)
    print(f"ingest: {stats}")
    # canonicalize per place
    places = conn.execute("SELECT id FROM places").fetchall()
    total_canon = 0
    for (pid,) in places:
        total_canon += match.canonicalize_place(conn, pid)
    print(f"canonical items created: {total_canon}")
    # USD conversion pass (short-circuits for USD)
    n_usd = 0
    for lid, cur in conn.execute("SELECT id, currency_iso FROM menu_lines").fetchall():
        if not cur or cur.upper() == "USD":
            continue
        r = fx.rate_to_usd(cur)
        if r:
            conn.execute("UPDATE menu_lines SET price_usd=price*?, fx_rate=?, "
                         "fx_date='latest' WHERE id=?", (r, r, lid))
            n_usd += 1
    conn.commit()
    print(f"fx conversions applied: {n_usd}")
    rep = index.write_report(conn, name=name)
    ps = rep["place_stats"]
    print(f"report: {len(rep['series'])} item-place observations, "
          f"{len(ps)} places with prices")
    for p in ps[:10]:
        print(f"  {p['place'][:42]:<44} ${p['median_item_price']:<6} "
              f"({p['items']} items)")
    return rep


if __name__ == "__main__":
    main()
