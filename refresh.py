"""refresh.py — backfill price tier (Places API priceLevel) into manifests + DB.

Same-store discipline needs a segment dimension: comparing River's Edge
(fancy) with Burgerville (fast food) across years is comparing tiers, not
inflation. priceLevel is a coarse 0-4 tier (FREE..VERY_EXPENSIVE) from the
API; places.json can override with a manual "tier" for nuance.

Usage: python refresh.py
"""
import glob
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from menuflation.sources.places_api import search_places  # noqa: E402

LEVELS = {0: "free", 1: "inexpensive", 2: "moderate", 3: "expensive",
          4: "very expensive"}


def main():
    # 1) re-query each slug and merge priceLevel into manifests
    seen = {}
    for mf in sorted(glob.glob(os.path.join("data", "places", "*.json"))):
        m = json.load(open(mf, encoding="utf-8"))
        try:
            places = search_places(m["query"], page_size=10)
        except Exception as e:  # noqa: BLE001
            print(f"{mf}: search failed: {str(e)[:80]}")
            continue
        by_id = {p["id"]: p for p in places}
        for pl in m["places"]:
            api = by_id.get(pl["id"], {})
            lvl = api.get("priceLevel")
            pl["priceLevel"] = lvl
            pl["tier"] = pl.get("tier") or (LEVELS.get(lvl) if lvl is not None else None)
            pl["website_uri"] = api.get("websiteUri")
            seen[pl["id"]] = pl
        json.dump(m, open(mf, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"manifests refreshed: {len(seen)} places")

    # 2) push into the DB
    conn = sqlite3.connect(os.path.join("data", "menuflation.db"))
    cols = [c[1] for c in conn.execute("PRAGMA table_info(places)")]
    if "tier" not in cols:
        conn.execute("ALTER TABLE places ADD COLUMN tier TEXT")
        conn.execute("ALTER TABLE places ADD COLUMN price_level INTEGER")
    if "website_uri" not in cols:
        conn.execute("ALTER TABLE places ADD COLUMN website_uri TEXT")
    for pid, pl in seen.items():
        conn.execute("UPDATE places SET tier=?, price_level=?, website_uri=? "
                     "WHERE id=?",
                     (pl.get("tier"), pl.get("priceLevel"), pl.get("website_uri"), pid))
    conn.commit()
    print("\n== websites (places with one) ==")
    for row in conn.execute(
            "SELECT name, city, website_uri FROM places WHERE website_uri IS NOT NULL "
            "ORDER BY name"):
        print(f"  {row[0][:34]:<36} {str(row[1]):<12} {row[2]}")


if __name__ == "__main__":
    main()
