"""upgrade_menus.py — re-download menu photos at hi-res (EXIF-preserving)
and rebuild the price DB with real observed dates.

The 1280px media downloads strip EXIF; 2048px serves DateTimeOriginal on most
contributor photos. Run this after a collect to anchor the time axis.

Usage: python upgrade_menus.py
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from menuflation import db, index, match  # noqa: E402
from menuflation.dates import exif_date  # noqa: E402
from menuflation.sources.places_api import download_photo  # noqa: E402


def menu_photos():
    out = []
    for jf in sorted(glob.glob(os.path.join("data", "extractions", "**", "*.json"),
                               recursive=True)):
        if os.path.basename(jf) == "index.json":
            continue
        p = json.load(open(jf, encoding="utf-8"))
        if (p.get("result") or {}).get("is_menu"):
            out.append(p)
    return out


def main():
    menus = menu_photos()
    print(f"checking {len(menus)} menu photos (skip already-dated)...")
    dated = 0
    for p in menus:
        if exif_date(p["src"]):
            dated += 1
            continue
        try:
            download_photo(p["photo"], p["src"], max_width=2048)
            if exif_date(p["src"]):
                dated += 1
        except Exception as e:  # noqa: BLE001
            print("  fail:", os.path.basename(p["src"])[:30], str(e)[:80])
    print(f"dated: {dated}/{len(menus)}")

    if os.path.exists("data/menuflation.db"):
        os.remove("data/menuflation.db")
    conn = db.connect()
    stats = db.ingest(conn)
    print("ingest:", stats)
    for (pid,) in conn.execute("SELECT id FROM places"):
        match.canonicalize_place(conn, pid)
    index.write_report(conn)

    print("\n== date sources ==")
    for row in conn.execute(
            "SELECT date_source, COUNT(*) FROM menu_lines GROUP BY date_source"):
        print(f"  {row[0]}: {row[1]}")
    print("\n== EXIF-dated observations per place ==")
    for row in conn.execute(
            "SELECT pl.name, COUNT(m.id), MIN(m.observed_on), MAX(m.observed_on) "
            "FROM menu_lines m JOIN places pl ON pl.id=m.place_id "
            "WHERE m.date_source='exif' GROUP BY pl.name ORDER BY MIN(m.observed_on)"):
        print(f"  {row[0][:40]:<42} {row[1]:>3} lines  {row[2]} .. {row[3]}")


if __name__ == "__main__":
    main()
