"""Harvest gotts.com Wayback PDFs for Gott's Napa — capped at 3 per tick."""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from wayback import _get, extract_and_store, CDX

PLACE_ID = "ChIJUS-dzWUGhYARysICSZjj8JU"
DOMAIN = "gotts.com"
OUT_DIR = "data/extractions/wayback"
CAP = 3

# Load .env for OpenRouter key
for line in open(".env"):
    line = line.strip()
    if line and "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

# 1. CDX query
time.sleep(1.2)
r = _get(CDX, params={
    "url": DOMAIN,
    "matchType": "domain",
    "filter": "mimetype:application/pdf",
    "output": "json",
    "fl": "timestamp,original",
    "collapse": "timestamp:6",
}, timeout=60)

if not r or r.status_code != 200:
    print(f"CDX query failed: {r}")
    sys.exit(1)

rows = r.json()
data = rows[1:] if len(rows) > 1 else []
print(f"CDX: {len(data)} PDF snapshots")

# Dedupe by normalized URL (strip :80), keep earliest snapshot
by_url = {}
for row in data:
    ts = row[0]
    url = row[1].replace(":80", "")
    if url not in by_url:
        by_url[url] = ts

sorted_urls = sorted(by_url.items(), key=lambda x: x[1])

# Filter to menu-like PDFs only
menu_urls = [(u, ts) for u, ts in sorted_urls
             if re.search(r"(?i)(menu|spring|fall|summer|winter|breakfast|lunch|dinner)", u)]
print(f"Menu-like PDFs: {len(menu_urls)}")
for u, ts in menu_urls[:15]:
    print(f"  {ts} {u}")

# 2. Harvest up to CAP
harvested = 0
total_cost = 0.0
for url, first_ts in menu_urls:
    if harvested >= CAP:
        break
    wb_url = f"https://web.archive.org/web/{first_ts}id_/{url}"
    print(f"\nFetching: {wb_url}")
    time.sleep(1.2)
    resp = _get(wb_url, timeout=90)
    if not resp or resp.status_code != 200:
        print(f"  fetch failed (status={resp.status_code if resp else 'none'})")
        continue

    content = resp.content
    if not content[:5] == b"%PDF-":
        print(f"  not a PDF (starts with {content[:20]})")
        continue

    # Date from URL (YYYY-MM pattern, must be 20xx) or from CDX timestamp
    m = re.search(r"20(\d{2})[_-]?(\d{2})", url)
    if m:
        observed_on = f"20{m.group(1)}-{m.group(2)}-15"
    else:
        observed_on = f"{first_ts[:4]}-{first_ts[4:6]}-{first_ts[6:8]}"

    ts_clean = observed_on.replace("-", "")
    try:
        payload = extract_and_store(ts_clean, url, content, PLACE_ID,
                                   out_dir=OUT_DIR, date_source="wayback")
    except Exception as e:
        print(f"  extract fail: {str(e)[:100]}")
        continue
    if payload:
        d = payload["result"]
        items = d.get("items") or []
        print(f"  {payload['observed_on']} menu={d.get('is_menu')} "
              f"items={len(items)} ${payload['cost_usd']:.5f}")
        total_cost += payload.get("cost_usd", 0)
        harvested += 1
    else:
        print("  already extracted or empty (skipped)")

print(f"\n=== Harvested {harvested} PDFs, total cost ${total_cost:.5f} ===")
