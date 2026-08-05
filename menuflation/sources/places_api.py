"""places_api.py — official Google Places API (New) backend, with IP pinning.

This machine's network blackholes some googleapis.com IPs (172.217.x.x) while
Google anycast front-ends on 142.251.x.x work fine. We pin places.googleapis.com
to known-good IPs via a getaddrinfo shim. SNI still carries the real hostname,
so TLS validates normally — this is a routing workaround, not a hack.

Calling patterns (per Google, as of 2026):
- searchText: POST /v1/places:searchText  (text query -> places with photo refs)
- photo bytes: GET /v1/{photo_name}/media?maxWidthPx=N   (returns image bytes)
Official API returns NO photo upload dates — the DOM route stays for that seam.
"""
import os
import socket

import requests

BASE = "https://places.googleapis.com/v1"

# Verified reachable from this host (Aug 2026). Only add IPs that serve BOTH
# searchText AND photo media — 142.251.215.219 passes the root test but
# misroutes both (GCS NoSuchBucket / InvalidArgument).
PINNED_IPS = ["142.251.153.119"]
PINNED_HOSTS = {"places.googleapis.com": PINNED_IPS}

_real_getaddrinfo = socket.getaddrinfo
_pin_index = 0


def _pinned_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    global _pin_index
    if host in PINNED_HOSTS:
        ips = PINNED_HOSTS[host]
        ip = ips[_pin_index % len(ips)]
        _pin_index += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    return _real_getaddrinfo(host, port, family, type, proto, flags)


def _install_pinning():
    if not getattr(socket, "_menuflation_pinned", False):
        socket.getaddrinfo = _pinned_getaddrinfo
        socket._menuflation_pinned = True


_install_pinning()


def _key():
    k = os.environ.get("GOOGLE_API_KEY")
    if not k:
        raise RuntimeError("GOOGLE_API_KEY not set (see .env)")
    return k


def _headers(field_mask):
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _key(),
        "X-Goog-FieldMask": field_mask,
    }


def search_places(text_query, page_size=20,
                  field_mask=("places.id,places.displayName,places.formattedAddress,"
                              "places.location,places.photos")):
    """Text search -> list of place dicts with .photos[].name references."""
    r = requests.post(f"{BASE}/places:searchText", headers=_headers(field_mask),
                      json={"textQuery": text_query, "pageSize": page_size,
                            "languageCode": "en"},
                      timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"searchText {r.status_code}: {r.text[:400]}")
    return r.json().get("places", [])


def download_photo(photo_name, dest_path, max_width=2048):
    """Fetch photo bytes for a photo reference like places/ChIJ.../photos/AU...

    maxWidthPx=2048 preserves EXIF DateTimeOriginal on most contributor photos
    (the 1280 re-encode strips it) — that EXIF date anchors the time axis.

    Note: the media endpoint takes the key as a QUERY PARAM — the
    X-Goog-Api-Key header gets misrouted to GCS and 404s (NoSuchBucket).
    """
    url = f"{BASE}/{photo_name}/media?maxWidthPx={max_width}&key={_key()}"
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"photo media {r.status_code}: {r.text[:200]}")
    with open(dest_path, "wb") as f:
        f.write(r.content)
    return dest_path
