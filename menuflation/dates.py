"""dates.py — EXIF capture dates for collected photos.

The Places API media endpoint preserves DateTimeOriginal on most contributor
photos (verified: 531/758 dated, 2014-2026). A capture date is the best
available proxy for "when this menu was in effect" — it's what anchors a price
observation on the time axis. Photos without EXIF fall back to the ingestion
date (undated flag), so cross-sectional stats stay honest.
"""
import logging
import os
import re

import exifread

logging.getLogger("exifread").setLevel(logging.CRITICAL)  # quiet the PNG spam

_ISO = re.compile(r"^\d{4}:\d{2}:\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")
_MDY = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def exif_date(path):
    """ISO date string (YYYY-MM-DD) from EXIF, or None."""
    try:
        with open(path, "rb") as fh:
            tags = exifread.process_file(fh, details=False)
        dt = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        if not dt:
            return None
        s = str(dt).strip()
        if _ISO.match(s):
            return s[:10].replace(":", "-")
        m = _MDY.match(s)
        if m:
            mo, d, y = s.split("/")
            return f"{y}-{int(mo):02d}-{int(d):02d}"
        return None
    except Exception:
        return None


def photo_dates(photos_dir="data/places"):
    """Map photo ref -> EXIF date by scanning files under photos_dir.

    Returns dict ref -> iso date. File layout:
    data/places/<slug>/<place_id>/<ref>.jpg
    """
    out = {}
    for slug in os.listdir(photos_dir):
        slug_dir = os.path.join(photos_dir, slug)
        if not os.path.isdir(slug_dir):
            continue
        for pid in os.listdir(slug_dir):
            pdir = os.path.join(slug_dir, pid)
            if not os.path.isdir(pdir):
                continue
            for fname in os.listdir(pdir):
                if not fname.lower().endswith((".jpg", ".jpeg")):
                    continue
                d = exif_date(os.path.join(pdir, fname))
                if d:
                    # ref is the last path segment of the photo name
                    out[fname[:-4]] = d
    return out
