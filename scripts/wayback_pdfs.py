"""wayback_pdfs.py — find and harvest archived PDF menus for a domain.

CDX search for PDFs under a domain's uploads/menu paths, then harvest each
URL's snapshot history (observed_on = snapshot date, date_source='wayback').
The archive's PDF snapshots are dated history from the SAME store — the
temporal-depth seam.

Usage: python scripts/wayback_pdfs.py <domain> [place_id]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wayback import CDX, _get, harvest  # noqa: E402


def find_pdfs(domain, limit=20):
    """Unique archived PDF URLs for a domain (uploads + menu-ish paths)."""
    urls = {}
    for path in ("wp-content/uploads/*", "menus/*", "menu/*", "pdfs/*"):
        time.sleep(1.2)
        r = _get(CDX, params={
            "url": f"{domain}/{path}", "output": "json",
            "fl": "timestamp,original,statuscode",
            "filter": ["statuscode:200", "original:.*[Pp][Dd][Ff].*"],
            "collapse": "urlkey", "limit": 500})
        if not r:
            continue
        try:
            rows = r.json()
        except ValueError:
            continue
        for row in rows[1:]:
            urls.setdefault(row[1], []).append(row[0])
        if len(urls) >= limit:
            break
    return urls


def main():
    domain = sys.argv[1]
    place_id = sys.argv[2] if len(sys.argv) > 2 else None
    pdfs = find_pdfs(domain)
    print(f"{domain}: {len(pdfs)} archived PDFs")
    for url, tss in sorted(pdfs.items())[:15]:
        print(f"  {len(tss):>2} snapshots  {url[:90]}")
        harvest(url, place_id, max_snapshots=8)


if __name__ == "__main__":
    main()
