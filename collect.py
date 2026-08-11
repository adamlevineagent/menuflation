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


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(places_json="places.json", photos_per_place=20, force=False,
            slug_filter=None):
    specs = json.load(open(places_json, encoding="utf-8"))
    os.makedirs(OUT_ROOT, exist_ok=True)
    total_photos = 0
    for spec in specs:
        slug = spec["slug"]
        if slug_filter and slug != slug_filter:
            continue
        manifest, manifest_path = _load(spec)
        # index existing places by id so force can refresh them in place
        by_id = {p["id"]: p for p in manifest["places"]}
        try:
            places = search_places(spec["query"], page_size=10)
        except Exception as e:
            print(f"[{slug}] SEARCH FAILED: {e}")
            continue
        for pl in places:
            pid = pl["id"]
            if pid in by_id and not force:
                continue
            if pid in by_id:
                entry = by_id[pid]
            else:
                loc = pl.get("location", {})
                entry = {
                    "id": pid,
                    "name": (pl.get("displayName") or {}).get("text"),
                    "address": pl.get("formattedAddress"),
                    "lat": loc.get("latitude"), "lng": loc.get("longitude"),
                    "photos": [],
                }
                manifest["places"].append(entry)
            pdir = os.path.join(OUT_ROOT, slug, pid)
            os.makedirs(pdir, exist_ok=True)
            got = 0
            # force dedupes by CONTENT HASH (searchText refs are per-request:
            # the same photo reappears under a new ref token, so ref-dedupe
            # would accumulate dupes across a force re-fetch).
            have_hashes = set()
            for p in entry.get("photos", []):
                fp = os.path.join(OUT_ROOT, p["file"])
                if os.path.exists(fp):
                    have_hashes.add(_sha256(fp))
            for ph in pl.get("photos", [])[:photos_per_place]:
                pname = ph["name"]
                ref = pname.rsplit("/", 1)[-1][:40]
                dest = os.path.join(pdir, ref + ".jpg")
                # non-force: keep existing files (resumable/idempotent).
                if os.path.exists(dest) and not force:
                    continue
                try:
                    download_photo(pname, dest, max_width=2048 if force else 1280)
                    # dedupe a freshly-downloaded file against known content
                    h = _sha256(dest)
                    if h in have_hashes:
                        print(f"    [{slug}] skip dup content {ref}")
                        got += 1  # refreshed in place, not a new photo
                        continue
                    entry["photos"].append({
                        "name": pname, "file": os.path.relpath(dest, OUT_ROOT),
                        "width": ph.get("widthPx"), "height": ph.get("heightPx"),
                    })
                    have_hashes.add(h)
                    got += 1
                    total_photos += 1
                    time.sleep(0.1)
                except Exception as e:
                    print(f"  [{slug}] photo fail {ref}: {e}")
            if force and pid in by_id:
                print(f"[{slug}] force-refresh {entry['name']}: {got} photos "
                      f"(2048px, {len(entry['photos'])} total in manifest)")
            json.dump(manifest, open(manifest_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            if pid not in by_id:
                print(f"[{slug}] {entry['name']}: {len(entry['photos'])} photos")
        print(f"[{slug}] done ({len(manifest['places'])} places, "
              f"{sum(len(p['photos']) for p in manifest['places'])} photos)")
    print(f"\nTOTAL new photos: {total_photos}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    pp = 20
    force = "--force" in argv
    if force:
        argv.remove("--force")
    slug_filter = None
    if "--slug" in argv:
        i = argv.index("--slug")
        slug_filter = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if "--photos-per-place" in argv:
        i = argv.index("--photos-per-place")
        pp = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    collect(places_json=argv[0] if argv else "places.json", photos_per_place=pp,
            force=force, slug_filter=slug_filter)
