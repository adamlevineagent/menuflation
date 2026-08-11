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

    slug = "test-place"
    pid = "place-1"
    pdir = root / slug / pid
    pdir.mkdir(parents=True)
    existing_photo = pdir / "ref1.jpg"
    existing_photo.write_bytes(b"CONTENT-REF1")  # same content the API serves

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
        # content keyed by the photo name's UPPER base (matches the seed file)
        content = f"CONTENT-{os.path.basename(name).upper()}".encode()
        with open(dest, "wb") as f:
            f.write(content)

    monkeypatch.setattr(collect, "search_places", fake_search)
    monkeypatch.setattr(collect, "download_photo", fake_download)
    monkeypatch.setattr(collect, "time",
                        type("T", (), {"sleep": staticmethod(lambda s: None)})())

    return {"root": root, "slug": slug, "pid": pid, "calls": calls,
            "manifest_path": mp}


def test_non_force_skips_existing_place(env):
    collect.collect(env["root"] / "spec.json", photos_per_place=20)
    assert env["calls"] == []


def test_force_refreshes_and_picks_new_photo_no_dup(env):
    collect.collect(str(env["root"] / "spec.json"), photos_per_place=20, force=True)
    # both photos touched (ref1 re-downloaded at 2048, ref2 new)
    basenames = sorted(os.path.basename(c[1]) for c in env["calls"])
    assert basenames == ["ref1.jpg", "ref2.jpg"]
    assert all(c[2] == 2048 for c in env["calls"])  # EXIF-preserving width
    # manifest has exactly the 2 unique photos (ref1 content-deduped, NOT dup'd)
    man = json.load(open(env["manifest_path"], encoding="utf-8"))
    p = man["places"][0]
    assert len(p["photos"]) == 2
    names = sorted(os.path.basename(x["file"]) for x in p["photos"])
    assert names == ["ref1.jpg", "ref2.jpg"]
    # ref1 refreshed in place at 2048
    disk = env["root"] / env["slug"] / env["pid"] / "ref1.jpg"
    assert disk.read_bytes() == b"CONTENT-REF1"


def test_force_dup_ref_token_not_duplicated(env):
    # simulate the searchText ref-per-request quirk: the API returns the SAME
    # photo under a NEW ref token; content-hash dedupe must not accumulate it.
    collect.collect(str(env["root"] / "spec.json"), photos_per_place=20, force=True)
    # now force again with a different ref name but same content
    import collect as _c
    calls = []

    def fake_search2(query, page_size=10):
        return [{
            "id": env["pid"], "displayName": {"text": "Test Place"},
            "formattedAddress": "1 Main",
            "location": {"latitude": 1.0, "longitude": 2.0},
            "photos": [
                {"name": "photos/ref1", "widthPx": 1280, "heightPx": 960},
                # same content as ref1, new token
                {"name": "photos/ref2", "widthPx": 2048, "heightPx": 1536},
            ],
        }]

    def fake_download2(name, dest, max_width):
        calls.append(name)
        with open(dest, "wb") as f:
            f.write(b"CONTENT-REF1")  # SAME content as ref1 despite new token

    _c.search_places = fake_search2
    _c.download_photo = fake_download2
    collect.collect(str(env["root"] / "spec.json"), photos_per_place=20, force=True)
    man = json.load(open(env["manifest_path"], encoding="utf-8"))
    assert len(man["places"][0]["photos"]) == 2  # no dup accumulation


def test_slug_filter_only_touches_target(env):
    spec = env["root"] / "spec2.json"
    spec.write_text(json.dumps([{"slug": env["slug"], "query": "q"},
                                {"slug": "other", "query": "q2"}]), encoding="utf-8")
    collect.collect(str(spec), photos_per_place=20, force=True, slug_filter=env["slug"])
    assert len(env["calls"]) == 2  # only the target slug's two photos
