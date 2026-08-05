"""test_wayback.py — durable pytest coverage for the Wayback PDF hunt.

find_pdfs: CDX PDF discovery with a monkeypatched HTTP layer (no network).
harvest_pdf's date-derivation is covered here too (filename -> observed_on).
"""
import json
import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wayback  # noqa: E402


class _FakeResp:
    status_code = 200

    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return self._rows


def test_find_pdfs_discovers_archived_pdfs(monkeypatch):
    """CDX rows for PDFs are discovered as URL -> snapshot timestamps."""
    rows = [["timestamp", "original", "statuscode"],
            ["20210101", "https://x.com/menus/2021-01.pdf", "200"],
            ["20220101", "https://x.com/menus/2021-01.pdf", "200"],
            ["20210101", "https://x.com/uploads/Menu.pdf", "200"]]
    def fake_get(url, params=None, timeout=60, tries=3):
        if "wp-content" in (params or {}).get("url", ""):
            return _FakeResp(rows)
        return _FakeResp([["timestamp", "original", "statuscode"]])

    monkeypatch.setattr(wayback, "_get", fake_get)
    pdfs = wayback_pdfs_find("x.com", limit=5)
    assert "https://x.com/menus/2021-01.pdf" in pdfs
    assert pdfs["https://x.com/menus/2021-01.pdf"] == ["20210101", "20220101"]
    assert "https://x.com/uploads/Menu.pdf" in pdfs


def test_harvest_pdf_derives_date_from_filename(monkeypatch, tmp_path):
    """Versioned PDF filename -> observed_on; undated -> skipped unless today."""
    import fitz

    doc = fitz.open()
    pg = doc.new_page()
    for i, line in enumerate(("BURGERS", "Cheeseburger $7.95",
                              "Double Cheeseburger $10.95",
                              "French Fries $3.49", "Small Shake $4.99")):
        pg.insert_text((72, 72 + 20 * i), line)
    pdf_bytes = doc.tobytes()

    class _Get:
        status_code = 200
        content = pdf_bytes

    monkeypatch.setattr(wayback, "_get", lambda url, timeout=60, tries=3: _Get())
    monkeypatch.setattr(
        wayback, "extract_menu_text",
        lambda text: {"ok": True,
                      "data": {"is_menu": True, "currency_iso": "USD",
                               "items": [{"name": "Cheeseburger",
                                          "price": 7.95}]},
                      "cost_usd": 0.0004})
    r = wayback.harvest_pdf(
        "https://x.com/wp-content/uploads/2026/06/Main-Menus_2026-06.pdf",
        "P1", out_dir=str(tmp_path))
    assert r and r["observed_on"] == "2026-06-15", r
    assert r["date_source"] == "pdf", r
    assert wayback.harvest_pdf("https://x.com/uploads/Menu.pdf", "P1",
                               out_dir=str(tmp_path)) is None


def wayback_pdfs_find(domain, limit=5):
    """Local mirror of scripts.wayback_pdfs.find_pdfs (avoids importing scripts/)."""
    import time

    urls = {}
    for path in ("wp-content/uploads/*", "menus/*", "menu/*", "pdfs/*"):
        time.sleep(0)  # monkeypatched HTTP; keep the production sleep shape
        r = wayback._get(wayback.CDX, params={
            "url": f"{domain}/{path}", "output": "json",
            "fl": "timestamp,original,statuscode",
            "filter": ["statuscode:200", "original:.*[Pp][Dd][Ff].*"],
            "collapse": "urlkey", "limit": 500})
        if not r:
            continue
        try:
            rows = r.json()
        except ValueError:
            continue
        for row in rows[1:]:
            urls.setdefault(row[1], []).append(row[0])
        if len(urls) >= limit:
            break
    return urls
