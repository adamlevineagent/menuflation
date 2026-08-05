"""test_place_id_keying.py — durable pytest for the same-store place_id keying fix.

The bug: price_series/aggregate_index/tier_rates keyed same-store pairs by
place NAME, not place_id. Multiple locations of the same chain (e.g. 5
In-N-Out Burgers across Eugene, Medford, Napa) all named "In-N-Out Burger"
collapsed into one key — cross-store price differences (Napa $2.25 vs
Medford $3.95 cheeseburger) masqueraded as 43% price drops in the
aggregate index.  The fix keys by place_id so each location is its own
same-store series.
"""
import os
import sys
import sqlite3
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from menuflation.index import price_series, aggregate_index


@pytest.fixture
def db():
    """Build a minimal DB with two same-named places at different price levels."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE places (
            id TEXT PRIMARY KEY, name TEXT, address TEXT,
            lat REAL, lng REAL, city TEXT, state TEXT,
            source TEXT, price_level INTEGER, tier TEXT, website_uri TEXT
        );
        CREATE TABLE menu_lines (
            id TEXT PRIMARY KEY, photo_ref TEXT, place_id TEXT,
            item_raw TEXT, price REAL, old_price REAL, size TEXT,
            qty INTEGER, unit TEXT, notes TEXT, currency_iso TEXT,
            confidence REAL, canonical_id INTEGER, price_usd REAL,
            fx_rate REAL, fx_date TEXT, observed_on TEXT, date_source TEXT,
            date_hints TEXT
        );
        CREATE TABLE canonical_items (
            id INTEGER PRIMARY KEY, name TEXT, place_id TEXT
        );
    """)
    # Two In-N-Out stores, same name, different place_ids
    conn.execute("INSERT INTO places VALUES ('place_a','In-N-Out Burger','addr',0,0,'Eugene','OR','test',1,'inexpensive',NULL)")
    conn.execute("INSERT INTO places VALUES ('place_b','In-N-Out Burger','addr',0,0,'Napa','CA','test',1,'inexpensive',NULL)")
    conn.execute("INSERT INTO canonical_items VALUES (1, 'cheeseburger', NULL)")
    # Place A: cheeseburger $3.95 in 2025-02
    conn.execute("INSERT INTO menu_lines (id,place_id,item_raw,price,canonical_id,price_usd,observed_on,date_source) "
                 "VALUES ('la1','place_a','Cheeseburger',3.95,1,3.95,'2025-02-25','exif')")
    # Place A: cheeseburger $4.10 in 2026-06 (>180d gap, same store)
    conn.execute("INSERT INTO menu_lines (id,place_id,item_raw,price,canonical_id,price_usd,observed_on,date_source) "
                 "VALUES ('la2','place_a','Cheeseburger',4.10,1,4.10,'2026-06-11','exif')")
    # Place B: cheeseburger $2.25 in 2026-05 (different store, different price level)
    conn.execute("INSERT INTO menu_lines (id,place_id,item_raw,price,canonical_id,price_usd,observed_on,date_source) "
                 "VALUES ('lb1','place_b','Cheeseburger',2.25,1,2.25,'2026-05-09','exif')")
    conn.commit()
    yield conn
    conn.close()
    os.unlink(tmp.name)


class TestPlaceIdKeying:
    def test_price_series_has_place_id(self, db):
        """Each series point must carry a place_id."""
        ps = price_series(db)
        assert all("place_id" in s for s in ps)

    def test_cross_store_not_paired(self, db):
        """The aggregate must NOT pair place_a 2025-02 with place_b 2026-05
        (different stores, despite same name).  Only the same-store pair
        (place_a 2025-02 → 2026-06, ratio ~1.038) should appear."""
        idx = aggregate_index(db)
        months = idx.get("months", [])
        # Should have exactly one month (2026-06) with one pair
        assert len(months) == 1
        m = months[0]
        assert m["n"] == 1
        assert m["month"] == "2026-06"
        # Ratio = 4.10 / 3.95 ≈ 1.038
        assert abs(m["index"] - 1.038) < 0.01

    def test_no_cross_store_ratio(self, db):
        """The bogus ~0.57 ratio (2.25/3.95) must NOT appear anywhere."""
        idx = aggregate_index(db)
        for m in idx.get("months", []):
            for item in m.get("items", []):
                # 2.25/3.95 ≈ 0.5696 — must not exist
                assert item["ratio"] > 0.7, f"Suspicious cross-store ratio: {item}"
