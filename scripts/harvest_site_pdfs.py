"""harvest_site_pdfs.py — find PDF menus on a site page and harvest them.

Versioned menu PDFs (WordPress uploads like Main_Menu_2026_06.pdf) carry
their menu date in the filename; observed_on is derived from it
(YYYY-MM or YYYY/MM in the URL), date_source='pdf'.

Usage:
    python scripts/harvest_site_pdfs.py <page_url> [place_id]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayback import _get, harvest_pdf  # noqa: E402


def main():
    page = sys.argv[1]
    place_id = sys.argv[2] if len(sys.argv) > 2 else None
    r = _get(page, timeout=60)
    if not r or r.status_code != 200:
        print(f"{page}: fetch failed")
        return
    pdfs = sorted(set(re.findall(r'(?i)https?://[^"\'\s]+\.pdf', r.text)))
    print(f"{page}: {len(pdfs)} PDF links")
    for url in pdfs:
        if not re.search(r"(?i)(menu|dinner|lunch|brunch|breakfast|dessert|kids)", url):
            continue
        p = harvest_pdf(url, place_id)
        if p:
            d = p["result"]
            print(f"  {p['observed_on']} menu={d.get('is_menu')} "
                  f"items={len(d.get('items') or [])} ${p['cost_usd']}")


if __name__ == "__main__":
    main()
