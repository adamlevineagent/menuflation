"""Barney's dedup: merge the curly-apostrophe place (ChIJTcrn...)
into the straight-apostrophe place (ChIJ7_x7...) under one canonical
place_id.  Same restaurant; the two place IDs came from two different
searchText queries (per-request refs gave different results).

Approach:
  1. Patch extraction JSONs for the curly place to carry place_id=canonical.
  2. Rebuild DB from scratch via upgrade_menus pipeline (fast, no API).
  3. Verify the merge: one Barney's, combined lines, both date sources.
"""
import glob, json, os, sys

CURLY = "ChIJTcrnJGN7xVQR5mTCV1bRiuo"
STRAIGHT = "ChIJ7_x7vtJ7xVQRJrPkfXCJAKA"

# Patch the extraction JSONs
patched = 0
for jf in sorted(glob.glob(f"data/extractions/grants-pass-barneys/{CURLY}/*.json")):
    p = json.load(open(jf, encoding="utf-8"))
    if p.get("place_id") != STRAIGHT:
        p["place_id"] = STRAIGHT
        json.dump(p, open(jf, "w", encoding="utf-8"), ensure_ascii=False)
        patched += 1
print(f"Patched {patched} extraction JSONs: place_id -> {STRAIGHT}")

# Also patch the manifest so the curly entry is dropped (it'll be a
# duplicate of the straight one in the places table after ingest).
manifest = json.load(open("data/places/grants-pass-barneys.json", encoding="utf-8"))
before = len(manifest["places"])
manifest["places"] = [p for p in manifest["places"] if p["id"] != CURLY]
after = len(manifest["places"])
if before != after:
    json.dump(manifest, open("data/places/grants-pass-barneys.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Manifest: removed curly Barney's ({before} -> {after} places)")
else:
    print("Manifest: curly already gone")
