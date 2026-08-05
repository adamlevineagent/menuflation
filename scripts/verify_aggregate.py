"""verify_aggregate.py — permanent verification for the aggregate index +
dashboard v2 (the canonical check the tracker can always see).

Run: python scripts/verify_aggregate.py
Synthetic same-store series -> median-ratio chaining, coverage matrix,
tolerant CSV writer, dashboard template contract. NOT a test suite.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import py_compile  # noqa: E402

for f in ["dashboard.py", "menuflation/index.py", "menuflation/db.py",
          "menuflation/match.py"]:
    py_compile.compile(os.path.join(ROOT, f), doraise=True)
print("py_compile: OK")

import dashboard  # noqa: E402
from menuflation import db, index  # noqa: E402
print("imports: OK")

tmp = tempfile.mkdtemp(prefix="verify-agg-")
try:
    conn = db.connect(os.path.join(tmp, "t.db"))
    conn.execute("INSERT INTO places(id,name,city,state) VALUES('P1','Barney''s','Grants Pass','OR')")
    conn.execute("INSERT INTO places(id,name,city,state) VALUES('P2','Burgerville','Oregon City','OR')")
    conn.execute("INSERT INTO canonical_items(id,name) VALUES(1,'drinks')")
    conn.execute("INSERT INTO canonical_items(id,name) VALUES(2,'shake')")
    conn.execute("INSERT INTO canonical_items(id,name) VALUES(3,'cheeseburger')")
    rows = [
        ("r1", 1, 1.99, "Small", "2024-01-15", "dom", "P1"),
        ("r2", 1, 1.99, "Small", "2025-08-18", "dom", "P1"),
        ("r3", 1, 2.99, "Large", "2024-01-15", "dom", "P1"),
        ("r4", 1, 3.49, "Large", "2025-08-18", "dom", "P1"),
        ("r5", 2, 4.99, "Small", "2024-01-15", "dom", "P1"),
        ("r6", 2, 5.49, "Small", "2025-08-18", "dom", "P1"),
        ("r7", 1, 1.99, "Small", "2026-08-05", "fallback", "P1"),
        # cheeseburger: two stores, two years -> emergent average.
        # Years split across stores so NO same-store pair forms (keeps the
        # aggregate_index assertion at exactly 3 pairs).
        ("r8", 3, 6.95, None, "2024-03-01", "dom", "P2"),
        ("r9", 3, 7.45, None, "2024-06-01", "dom", "P2"),
        ("r10", 3, 7.95, None, "2024-09-01", "dom", "P2"),
        ("r11", 3, 7.49, None, "2025-04-01", "exif", "P1"),
        ("r12", 3, 7.99, None, "2025-07-01", "exif", "P1"),
        ("r13", 3, 8.49, None, "2025-10-01", "exif", "P1"),
    ]
    for ref, cid, price, size, obs, src, place in rows:
        conn.execute(
            "INSERT INTO menu_lines(photo_ref,place_id,item_raw,price,size,"
            "observed_on,date_source,canonical_id) VALUES(?,?,'x',?,?,?,?,?)",
            (ref, place, price, size, obs, src, cid))
    conn.commit()

    agg = index.aggregate_index(conn, min_gap_days=100)
    assert agg["months"], "no months"
    m = agg["months"][0]
    assert m["month"] == "2025-08" and m["n"] == 3, m
    assert abs(m["index"] - 1.1002) < 0.001, m  # median of 1.0, 1.167, 1.100
    assert agg["overall"] is None, "overall needs 2+ index months"
    print(f"aggregate_index: OK (month {m['month']}, n={m['n']}, median {m['index']}, fallback excluded)")

    cov = index.coverage_matrix(conn)
    assert cov["years"] == ["2024", "2025"], cov
    assert cov["matrix"]["Barney's"]["2025"] == 6, cov  # 3 drinks/shake + 3 cheeseburger
    assert cov["matrix"]["Burgerville"]["2024"] == 3, cov
    print(f"coverage_matrix: OK (years {cov['years']})")

    av = index.item_averages(conn, min_records=5)
    cb = next(a for a in av if a["item"] == "cheeseburger")
    assert cb["total"] == 6 and cb["places"] == 2, cb
    assert [s["year"] for s in cb["series"]] == ["2024", "2025"], cb
    assert cb["series"][0]["median"] == 7.45, cb  # median of 6.95,7.45,7.95
    assert cb["series"][1]["median"] == 7.99, cb  # median of 7.49,7.99,8.49
    print(f"item_averages: OK (cheeseburger total={cb['total']}, places={cb['places']}, "
          f"2024 ${cb['series'][0]['median']} -> 2025 ${cb['series'][1]['median']})")

    rep = index.write_report(conn, out_dir=tmp, name="t")
    assert os.path.exists(os.path.join(tmp, "t.json"))
    with open(os.path.join(tmp, "t_series.csv"), encoding="utf-8") as f:
        header = next(iter(f)).strip()
    assert "date_source" in header, header
    print("write_report: OK (tolerant CSV with date_source)")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

assert "__DATA__" in dashboard.TEMPLATE
for anchor in ("aggChart", "aggPairs", "yoy", "cov", "D.aggregate", "D.coverage"):
    assert anchor in dashboard.TEMPLATE, f"template missing {anchor}"
print("dashboard template: OK")

print("VERIFY: PASS")
