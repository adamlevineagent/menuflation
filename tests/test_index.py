"""test_index.py — durable pytest suite for the aggregate/emergent index.

Mirrors scripts/verify_aggregate.py as a standard, detectable test command:
    python -m pytest tests/ -q
Covers aggregate_index (median-ratio chaining), coverage_matrix,
item_averages (emergent, distinct restaurants), and write_report's CSV.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from menuflation import db, index  # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(str(tmp_path / "t.db"))
    c.execute("INSERT INTO places(id,name,city,state) "
              "VALUES('P1','Barney''s','Grants Pass','OR')")
    c.execute("INSERT INTO places(id,name,city,state) "
              "VALUES('P2','Burgerville','Oregon City','OR')")
    c.execute("INSERT INTO canonical_items(id,name) VALUES(1,'drinks')")
    c.execute("INSERT INTO canonical_items(id,name) VALUES(2,'shake')")
    c.execute("INSERT INTO canonical_items(id,name) VALUES(3,'cheeseburger')")
    rows = [
        ("r1", 1, 1.99, "Small", "2024-01-15", "dom", "P1"),
        ("r2", 1, 1.99, "Small", "2025-08-18", "dom", "P1"),
        ("r3", 1, 2.99, "Large", "2024-01-15", "dom", "P1"),
        ("r4", 1, 3.49, "Large", "2025-08-18", "dom", "P1"),
        ("r5", 2, 4.99, "Small", "2024-01-15", "dom", "P1"),
        ("r6", 2, 5.49, "Small", "2025-08-18", "dom", "P1"),
        ("r7", 1, 1.99, "Small", "2026-08-05", "fallback", "P1"),
        # cheeseburger: two stores, two years -> emergent average.
        # Years split across stores so NO same-store pair forms.
        ("r8", 3, 6.95, None, "2024-03-01", "dom", "P2"),
        ("r9", 3, 7.45, None, "2024-06-01", "dom", "P2"),
        ("r10", 3, 7.95, None, "2024-09-01", "dom", "P2"),
        ("r11", 3, 7.49, None, "2025-04-01", "exif", "P1"),
        ("r12", 3, 7.99, None, "2025-07-01", "exif", "P1"),
        ("r13", 3, 8.49, None, "2025-10-01", "exif", "P1"),
    ]
    for ref, cid, price, size, obs, src, place in rows:
        c.execute(
            "INSERT INTO menu_lines(photo_ref,place_id,item_raw,price,size,"
            "observed_on,date_source,canonical_id) VALUES(?,?,'x',?,?,?,?,?)",
            (ref, place, price, size, obs, src, cid))
    c.commit()
    return c


def test_aggregate_index_median_ratio(conn):
    agg = index.aggregate_index(conn, min_gap_days=100)
    assert agg["months"], "no months"
    m = agg["months"][0]
    assert m["month"] == "2025-08" and m["n"] == 3, m
    # ratios 1.0, 1.167, 1.100 -> median 1.1002
    assert abs(m["index"] - 1.1002) < 0.001, m
    assert agg["overall"] is None, "overall needs 2+ index months"


def test_coverage_matrix(conn):
    cov = index.coverage_matrix(conn)
    assert cov["years"] == ["2024", "2025"], cov
    assert cov["matrix"]["Barney's"]["2025"] == 6, cov
    assert cov["matrix"]["Burgerville"]["2024"] == 3, cov


def test_item_averages_emergent(conn):
    av = index.item_averages(conn, min_records=5)
    cb = next(a for a in av if a["item"] == "cheeseburger")
    assert cb["total"] == 6 and cb["places"] == 2, cb
    assert [s["year"] for s in cb["series"]] == ["2024", "2025"], cb
    assert cb["series"][0]["median"] == 7.45, cb  # median of 6.95,7.45,7.95
    assert cb["series"][1]["median"] == 7.99, cb  # median of 7.49,7.99,8.49


def test_item_family():
    """Universal families: any cheeseburger counts; fries minus variants."""
    fam = index.item_family
    assert fam("grass fed cheeseburger") == "cheeseburger"
    assert fam("cheese burger") == "cheeseburger"
    assert fam("bacon cheeseburger") == "cheeseburger"
    assert fam("french fries") == "french fries"
    assert fam("fries") == "french fries"
    assert fam("fries large") == "french fries"      # size-suffixed head noun
    assert fam("fries regular") == "french fries"
    assert fam("fries little") == "french fries"
    assert fam("sweet potato fries") is None
    assert fam("carnitas fries") is None
    assert fam("loaded fries") is None
    # combos / entree descriptions are NOT plain fries (meal/steak prices)
    assert fam("double double french fries and medium drink") is None
    assert fam("new york steak french fries sauce bordelaise") is None
    assert fam("hamburger") is None


def test_family_averages(conn):
    """The cheeseburger average: cross-store, cross-year median."""
    fa = index.family_averages(conn, min_records=5)
    cb = next(a for a in fa if a["family"] == "cheeseburger")
    assert cb["total"] == 6 and cb["places"] == 2, cb
    assert [s["year"] for s in cb["series"]] == ["2024", "2025"], cb
    assert cb["series"][0]["median"] == 7.45, cb
    assert cb["series"][1]["median"] == 7.99, cb


def test_tier_mapping():
    """Places API priceLevel strings map to tiers (the int-key bug)."""
    import refresh  # repo-root pipeline script (guarded main)

    assert refresh.PL2INT["PRICE_LEVEL_INEXPENSIVE"] == 1
    assert refresh.LEVELS[refresh.PL2INT["PRICE_LEVEL_INEXPENSIVE"]] == "inexpensive"
    assert refresh.LEVELS[refresh.PL2INT["PRICE_LEVEL_EXPENSIVE"]] == "expensive"
    assert refresh.PL2INT.get("PRICE_LEVEL_VERY_EXPENSIVE") == 4


def test_tier_rates(conn):
    """Same-store pairs bucket into tiers; median+geo ratios computed."""
    conn.execute("UPDATE places SET tier='moderate' WHERE id='P1'")
    conn.commit()
    tr = index.tier_rates(conn)
    mod = next(t for t in tr if t["tier"] == "moderate")
    # drinks S/L + shake S (2024->2025) plus cheeseburger intra-year pairs
    # (3 dates per store -> 2 pairs each at P1/P2's tiered stores... P2 is
    # untiered so P1 carries: 3 drinks/shake + 2 cheeseburger = 5 pairs
    assert mod["n_pairs"] == 5, mod
    assert mod["median_ratio"] == 106.7, mod
    assert abs(mod["geo_ratio"] - 107.8) < 0.2, mod


def test_write_report_csv_schema(conn, tmp_path):
    index.write_report(conn, out_dir=str(tmp_path), name="t")
    with open(tmp_path / "t_series.csv", encoding="utf-8") as f:
        header = next(iter(f)).strip()
    assert "date_source" in header and "size" in header, header


def test_ingest_honors_date_source(tmp_path):
    """db.ingest must honor an explicit observed_on + date_source override."""
    import json as _json

    from menuflation import db as _db

    (tmp_path / "places").mkdir()
    (tmp_path / "extractions" / "wb").mkdir(parents=True)
    _json.dump({"query": "q", "slug": "s", "places": [
        {"id": "P1", "name": "Farmstead", "website_uri": "https://farmstead.example",
         "photos": [
            {"name": "places/P1/photos/X", "file": "x"}]}]},
        open(tmp_path / "places" / "s.json", "w"))
    _json.dump({"photo": "wb/20260615/https://x/menu.pdf",
                "place_id": "P1", "src": "https://x/menu.pdf",
                "observed_on": "2026-06-15", "date_source": "pdf",
                "result": {"is_menu": True, "currency_iso": "USD",
                           "items": [{"name": "Burger", "price": 9.95}]}},
        open(tmp_path / "extractions" / "wb" / "m.json", "w"))
    _json.dump({"photo": "wb/20260615/https://x/bad.pdf",
                "place_id": "P1", "src": "https://x/bad.pdf",
                "observed_on": "2026-06-15", "date_source": "pdf", "exclude": True,
                "exclude_reason": "audit: misread",
                "result": {"is_menu": True, "currency_iso": "USD",
                           "items": [{"name": "Burger", "price": 2.25}]}},
        open(tmp_path / "extractions" / "wb" / "bad.json", "w"))
    conn = _db.connect(str(tmp_path / "t.db"))
    _db.ingest(conn, extractions_dir=str(tmp_path / "extractions"),
               places_dir=str(tmp_path / "places"), observed_on="2026-08-05")
    rows = conn.execute(
        "SELECT observed_on, date_source, price FROM menu_lines").fetchall()
    assert len(rows) == 1, [dict(r) for r in rows]  # excluded payload skipped
    assert rows[0]["price"] == 9.95, dict(rows[0])
    assert rows[0]["date_source"] == "pdf", dict(rows[0])
    # places carry website_uri/tier through ingest (schema-drift fix)
    pl = conn.execute(
        "SELECT website_uri FROM places WHERE id='P1'").fetchone()
    assert pl["website_uri"] == "https://farmstead.example", dict(pl)
