"""dom_extract.py — deep-harvest pool: Maps gallery photos with DOM date labels.

The Places API caps at ~10 photos per place. The Maps gallery (browser) shows
the full photo history with per-photo date labels ("Photo - Jan 2024",
"Posted 3 years ago"). This ingests a harvested manifest of
{token: label} pairs: downloads the photos from the lh CDN at hi-res,
classifies/extracts with qwen, and writes extraction JSONs carrying the label
date (date_source='dom').

Harvest manifest format (data/dom/<slug>/dates.json):
    {"<lh-token>": "Photo - Jan 2024", ...}

Usage: python dom_extract.py <slug> <place_id> <dates.json> [--download-only]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests  # noqa: E402

from menuflation.dates import label_to_date  # noqa: E402
from menuflation.extract.qwen_vision import extract_menu_photo  # noqa: E402
from menuflation.sources import places_api  # noqa: E402,F401  (installs IP-pin shim)

CDN = "https://lh3.googleusercontent.com/gps-cs-s/{}={}"


def download_lh(token, dest, size="s1600-k-no"):
    r = requests.get(CDN.format(token, size), timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)


def main(slug, place_id, dates_json):
    dates = json.load(open(dates_json, encoding="utf-8"))
    photos_dir = os.path.join("data", "dom", slug, "photos")
    os.makedirs(photos_dir, exist_ok=True)
    for token, label in dates.items():
        fname = token[:40] + ".jpg"
        dest = os.path.join(photos_dir, fname)
        if not os.path.exists(dest):
            download_lh(token, dest)
            print(f"downloaded {token[:24]} ({label})")
        obs = label_to_date(label)
        res = extract_menu_photo(dest)
        out = {
            "photo": f"dom/{token}", "place_id": place_id, "src": dest,
            "observed_on": obs, "label": label,
            "result": res.get("data"), "cost_usd": res.get("cost_usd"),
        }
        outdir = os.path.join("data", "extractions", "dom", place_id)
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, fname[:-4] + ".json"),
                  "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
        d = res["data"]
        print(f"  {label:16} is_menu={d.get('is_menu')} "
              f"items={len(d.get('items') or [])} ${res['cost_usd']:.6f} -> {obs}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
