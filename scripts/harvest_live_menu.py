"""harvest_live_menu.py — extract a dated observation from a live web menu.

Server-rendered menu pages with inline prices (e.g. Barney's Squarespace
/menu) become dated observations: date_source='web', observed_on = today
(the price as experienced now — auditable: the live URL).

Usage: python scripts/harvest_live_menu.py <url> <place_id> [observed_on]
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from menuflation.extract.qwen_vision import extract_menu_text  # noqa: E402
from wayback import _get, html_to_text  # noqa: E402


def main():
    url = sys.argv[1]
    place_id = sys.argv[2]
    observed_on = sys.argv[3] if len(sys.argv) > 3 else datetime.date.today().isoformat()
    r = _get(url, timeout=60)
    if not r or r.status_code != 200:
        print(f"{url}: fetch failed")
        return
    text = html_to_text(r.content)
    if len(text) < 40:
        print(f"{url}: too little text ({len(text)} chars)")
        return
    res = extract_menu_text(text)
    d = res["data"]
    payload = {"photo": f"web/{url}", "place_id": place_id,
               "src": url, "observed_on": observed_on,
               "date_source": "web", "result": d, "cost_usd": res["cost_usd"]}
    outdir = os.path.join("data", "extractions", "web", place_id)
    os.makedirs(outdir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", url.split("//")[-1])[:40]
    fname = f"{slug}_{observed_on}.json"
    dest = os.path.join(outdir, fname)
    if os.path.exists(dest):
        print(f"{dest}: exists (idempotent)")
        return
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    print(f"{observed_on} menu={d.get('is_menu')} items={len(d.get('items') or [])} "
          f"${res['cost_usd']} -> {dest}")


if __name__ == "__main__":
    main()
