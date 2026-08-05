"""discover_pool.py — find Wayback-datable menu URLs across the pool.

For each place website: discover menu/PDF links (homepage + sitemap), then
count Wayback snapshots for each candidate. Prints site -> URL -> snapshots.
Control URLs (chipotle, barneys) included manually.

Usage: python discover_pool.py [--limit N]
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wayback import cdx_list, discover_menu_urls  # noqa: E402

CONTROLS = ["https://chipotle.com/menu", "https://www.barneysbetterburgers.com/menu"]


def main():
    conn = sqlite3.connect(os.path.join("data", "menuflation.db"))
    sites = [r[0] for r in conn.execute(
        "SELECT DISTINCT website_uri FROM places "
        "WHERE website_uri IS NOT NULL AND website_uri NOT LIKE '%facebook%'")]
    sites += CONTROLS
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if limit:
        sites = sites[:limit]
    print(f"scanning {len(sites)} sites (politely, ~1.2s between calls)")
    for site in sites:
        try:
            cands = discover_menu_urls(site)
        except Exception as e:  # noqa: BLE001
            print(f"{site[:40]:<42} ERROR {str(e)[:60]}")
            continue
        for c in cands[:4]:
            n = len(cdx_list(c))
            mark = "  <-- PDF" if c.lower().endswith(".pdf") else ""
            print(f"{site[:36]:<38} {c[:64]:<66} {n:>3} snapshots{mark}")
        if not cands:
            print(f"{site[:36]:<38} (no menu links found)")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
