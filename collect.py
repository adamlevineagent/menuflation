"""collect.py — M1 acquisition: run the place list through the Places API.

Resumable: manifests in data/places/<slug>.json; already-collected places are
skipped. Photos land in data/places/<slug>/<place_id>/.

Usage:
    python collect.py [places.json] [--photos-per-place N]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from menuflation.sources.places_api import download_photo, search_places  # noqa: E402

OUT_ROOT = os.path.join("data", "places")


def _load(spec):
    slug = spec["slug"]
    manifest_path = os.path.join(OUT_ROOT, f"{slug}.json")
    if os.path.exists(manifest_path):
        return json.load(open(manifest_path, encoding="utf-8")), manifest_path
    return {"query": spec["query"], "city": spec.get("city"),
            "state": spec.get("state"), "places": []}, manifest_path


def collect(places_json="places.json", photos_per_place=20):
    specs = json.load(open(places_json, encoding="utf-8"))
    os.makedirs(OUT_ROOT, exist_ok=True)
    total_photos = 0
    for spec in specs:
        slug = spec["slug"]
        manifest, manifest_path = _load(spec)
        seen = {p["id"] for p in manifest["places"]}
        try:
            places = search_places(spec["query"], page_size=10)
        except Exception as e:
            print(f"[{slug}] SEARCH FAILED: {e}")
            continue
        for pl in places:
            pid = pl["id"]
            if pid in seen:
                continue
            loc = pl.get("location", {})
            entry = {
                "id": pid,
                "name": (pl.get("displayName") or {}).get("text"),
                "address": pl.get("formattedAddress"),
                "lat": loc.get("latitude"), "lng": loc.get("longitude"),
                "photos": [],
            }
            pdir = os.path.join(OUT_ROOT, slug, pid)
            os.makedirs(pdir, exist_ok=True)
            for ph in pl.get("photos", [])[:photos_per_place]:
                pname = ph["name"]
                ref = pname.rsplit("/", 1)[-1][:40]
                dest = os.path.join(pdir, ref + ".jpg")
                try:
                    download_photo(pname, dest, max_width=1280)
                    entry["photos"].append({
                        "name": pname, "file": os.path.relpath(dest, OUT_ROOT),
                        "width": ph.get("widthPx"), "height": ph.get("heightPx"),
                    })
                    total_photos += 1
                    time.sleep(0.1)
                except Exception as e:
                    print(f"  [{slug}] photo fail {ref}: {e}")
            manifest["places"].append(entry)
            json.dump(manifest, open(manifest_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            print(f"[{slug}] {entry['name']}: {len(entry['photos'])} photos")
        print(f"[{slug}] done ({len(manifest['places'])} places, "
              f"{sum(len(p['photos']) for p in manifest['places'])} photos)")
    print(f"\nTOTAL new photos: {total_photos}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    pp = 20
    if "--photos-per-place" in argv:
        i = argv.index("--photos-per-place")
        pp = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    collect(places_json=argv[0] if argv else "places.json", photos_per_place=pp)
