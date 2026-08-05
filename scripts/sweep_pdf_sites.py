"""sweep_pdf_sites.py — harvest versioned menu PDFs across the pool's sites.

For each place with a website: discover menu/PDF URLs (homepage + sitemap),
then harvest every dated PDF (date from filename, date_source='pdf').

Usage: python scripts/sweep_pdf_sites.py [--limit N]
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayback import discover_menu_urls, harvest_pdf  # noqa: E402


def main():
    conn = sqlite3.connect(os.path.join("data", "menuflation.db"))
    sites = [r for r in conn.execute(
        "SELECT DISTINCT website_uri FROM places "
        "WHERE website_uri IS NOT NULL AND website_uri NOT LIKE '%facebook%' "
        "AND website_uri NOT LIKE '%dutchbros%'")]
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if limit:
        sites = sites[:limit]
    print(f"scanning {len(sites)} sites")
    for (site,) in sites:
        try:
            cands = discover_menu_urls(site)
        except Exception as e:  # noqa: BLE001
            print(f"{site[:44]}: discover error {str(e)[:60]}")
            continue
        for c in cands[:5]:
            if c.lower().endswith(".pdf"):
                p = harvest_pdf(c)
                if p:
                    d = p["result"]
                    print(f"  PDF {p['observed_on']} {d.get('is_menu')} "
                          f"{len(d.get('items') or [])} items")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
