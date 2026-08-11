"""Tests for collect.py force-refresh affordance."""
import json
import os

import pytest

import collect


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A temp OUT_ROOT with a pre-populated manifest, plus mocked API."""
    root = tmp_path / "places"
    root.mkdir()
    monkeypatch.setattr(collect, "OUT_ROOT", str(root))

    # a place already in the manifest with one existing photo file on disk
    slug = "test-place"
    pid = "place-1"
    pdir = root / slug / pid
    pdir.mkdir(parents=True)
    existing_photo = pdir / "ref1.jpg"
    existing_photo.write_bytes(b"OLD-1280-BYTES")

    manifest = {
        "query": "test query", "city": "X", "state": "ST",
        "places": [{
            "id": pid, "name": "Test Place",
            "address": "1 Main", "lat": 1.0, "lng": 2.0,
            "photos": [{"name": "photos/ref1", "file": f"{slug}/{pid}/ref1.jpg",
                        "width": 1280, "height": 960}],
        }],
    }
    mp = root / f"{slug}.json"
    mp.write_text(json.dumps(manifest), encoding="utf-8")
    spec = root / "spec.json"
    spec.write_text(json.dumps([{"slug": slug, "query": "q"}]), encoding="utf-8")

    calls = []

    def fake_search(query, page_size=10):
        # returns the same place, now with an extra NEW photo (ref2)
        return [{
            "id": pid, "displayName": {"text": "Test Place"},
            "formattedAddress": "1 Main",
            "location": {"latitude": 1.0, "longitude": 2.0},
            "photos": [
                {"name": "photos/ref1", "widthPx": 1280, "heightPx": 960},
                {"name": "photos/ref2", "widthPx": 2048, "heightPx": 1536},
            ],
        }]

    def fake_download(name, dest, max_width):
        calls.append((name, os.path.basename(dest), max_width))
        with open(dest, "wb") as f:
            f.write(f"IMG-{max_width}".encode())

    monkeypatch.setattr(collect, "search_places", fake_search)
    monkeypatch.setattr(collect, "download_photo", fake_download)
    monkeypatch.setattr(collect, "time", type("T", (), {"sleep": staticmethod(lambda s: None)})())

    return {"root": root, "slug": slug, "pid": pid, "calls": calls,
            "manifest_path": mp}


def test_non_force_skips_existing_place(env):
    collect.collect(env["root"] / "spec.json", photos_per_place=20)
    # existing place + photo untouched
    assert env["calls"] == []


def test_force_refreshes_and_picks_new_photo(env):
    collect.collect(str(env["root"] / "spec.json"), photos_per_place=20, force=True)
    # force re-downloads the existing photo at 2048 + grabs the new ref2
    basenames = sorted(os.path.basename(c[1]) for c in env["calls"])
    assert basenames == ["ref1.jpg", "ref2.jpg"]
    assert all(c[2] == 2048 for c in env["calls"])  # EXIF-preserving width
    # manifest now carries both photos
    man = json.load(open(env["manifest_path"], encoding="utf-8"))
    p = man["places"][0]
    assert len(p["photos"]) == 2
    assert os.path.basename(p["photos"][1]["file"]) == "ref2.jpg"
    # disk has the 2048-byte refreshed file
    disk = env["root"] / env["slug"] / env["pid"] / "ref1.jpg"
    assert disk.read_bytes() == b"IMG-2048"


def test_slug_filter_only_touches_target(env):
    spec = env["manifest_path"].parent / "spec.json"
    spec.write_text(json.dumps([{"slug": env["slug"], "query": "q"},
                                {"slug": "other", "query": "q2"}]), encoding="utf-8")
    collect.collect(str(spec), photos_per_place=20, force=True, slug_filter=env["slug"])
    assert len(env["calls"]) == 2  # only the target slug's two photos
