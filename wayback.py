"""wayback.py — Wayback Machine menu harvesting (apples-to-apples series).

The same menu URL snapshotted by the Wayback Machine over years is the
cleanest same-store comparison available: the snapshot date IS the observation
date and the item list is stable. Works best on server-rendered menu pages
and PDF menus (JS-shelled pages carry no prices in the archive).

Pipeline per menu URL:
    discover()  -> menu/PDF URLs from a site (homepage + sitemap)
    cdx_list()  -> snapshot timestamps (collapsed to ~1 per 6 months)
    fetch_snapshot() -> raw archived bytes (HTML or PDF)
    extract     -> text -> qwen text-mode extraction (same JSON schema)
    write       -> extraction JSONs with observed_on=snapshot date,
                   date_source='wayback' (honored by db.ingest)

Politeness: single UA, ~1s between CDX/fetch calls, backoff on 429/503.
"""
import datetime
import html as htmlmod
import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from menuflation.extract.qwen_vision import extract_menu_text  # noqa: E402

UA = "menuflation/0.1 (food-price research; contact: adamlevineagent)"
CDX = "https://web.archive.org/cdx/search/cdx"
WEB = "https://web.archive.org/web/"


def _get(url, params=None, timeout=60, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": UA},
                             timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503):
                time.sleep(2 + 4 * i)
                continue
            return r
        except requests.RequestException:
            time.sleep(2 + 4 * i)
    return None


def cdx_list(url, collapse="timestamp:6"):
    """Snapshot timestamps for a URL (~1 per 6 months). Empty on failure."""
    time.sleep(1.2)
    r = _get(CDX, params={"url": url, "output": "json",
                          "fl": "timestamp,statuscode",
                          "filter": "statuscode:200", "collapse": collapse})
    if not r:
        return []
    try:
        rows = r.json()
    except ValueError:
        return []
    return [row[0] for row in rows[1:]] if rows else []


def fetch_snapshot(ts, url):
    """Raw archived bytes (id_ = original page, no wayback banner)."""
    time.sleep(1.2)
    r = _get(f"{WEB}{ts}id_/{url}")
    return r.content if r else None


def is_pdf(content):
    return bool(content) and content[:5] == b"%PDF-"


def pdf_to_text(content):
    import fitz  # pymupdf
    doc = fitz.open(stream=content, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


def html_to_text(content):
    """Strip scripts/styles/tags from an HTML snapshot; keep visible text."""
    text = content.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = htmlmod.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def discover_menu_urls(base_url):
    """Find menu/PDF candidate URLs on a site (homepage + sitemap)."""
    found = []
    for url in (base_url, base_url.rstrip("/") + "/sitemap.xml"):
        r = _get(url, timeout=40)
        if not r or r.status_code != 200:
            continue
        text = r.text
        for href in re.findall(r'(?i)href="([^"]+)"', text):
            if re.search(r"(?i)(menu|our-food|pdf)", href) and not re.search(
                    r"(?i)(policy|privacy|terms|login|cart|account)", href):
                full = href if href.startswith("http") else (
                    base_url.rstrip("/") + "/" + href.lstrip("/"))
                if full not in found:
                    found.append(full)
    return found[:10]


def extract_and_store(ts, url, content, place_id, out_dir="data/extractions/wayback",
                      date_source="wayback"):
    """Extract prices from a snapshot and write a dated extraction JSON."""
    if is_pdf(content):
        text = pdf_to_text(content)
    else:
        text = html_to_text(content)
    if len(text) < 40:
        return None
    res = extract_menu_text(text)
    obs = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
    payload = {"photo": f"wb/{ts}/{url}", "place_id": place_id,
               "src": f"{WEB}{ts}/{url}", "observed_on": obs,
               "date_source": date_source,
               "result": res["data"], "cost_usd": res["cost_usd"],
               "wayback_ts": ts}
    outdir = os.path.join(out_dir, place_id or "unknown")
    os.makedirs(outdir, exist_ok=True)
    fname = re.sub(r"[^a-z0-9]+", "_", url.split("//")[-1])[:40] + f"_{ts}.json"
    dest = os.path.join(outdir, fname)
    if os.path.exists(dest):  # idempotent: don't re-spend on re-runs
        return None
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    return payload


def harvest_pdf(url, place_id=None, observed_on=None):
    """Download a live PDF menu, extract, store as a dated observation.

    Versioned menu PDFs (e.g. Long Meadow Ranch's Main_Menu_2026_06.pdf)
    carry their menu date in the filename — that wins when present.
    observed_on='today' is a sentinel: use today ONLY as a fallback for
    undated live menus (the price as experienced now). date_source='pdf'.
    """
    r = _get(url, timeout=90)
    if not r or not is_pdf(r.content):
        print(f"{url}: not a PDF or fetch failed")
        return None
    sentinel_today = observed_on == "today"
    if sentinel_today:
        observed_on = None
    if not observed_on:
        m = re.search(r"(\d{4})[_-]?(\d{2})", url)
        observed_on = f"{m.group(1)}-{m.group(2)}-15" if m else None
    if not observed_on and sentinel_today:
        observed_on = datetime.date.today().isoformat()
    if not observed_on:
        print(f"{url}: no date in filename — skipping (undated PDFs aren't "
              f"observations; pass observed_on='today' to date them now)")
        return None
    ts = observed_on.replace("-", "")
    return extract_and_store(ts, url, r.content, place_id,
                             out_dir="data/extractions/wayback",
                             date_source="pdf")


def harvest(url, place_id=None, max_snapshots=24):
    """Full pipeline for one menu URL. Returns list of extraction payloads."""
    tss = cdx_list(url)
    print(f"{url}: {len(tss)} snapshots")
    out = []
    # spread: keep first, last, and evenly spaced in between
    if len(tss) > max_snapshots:
        idx = sorted(set([0, len(tss) - 1] +
                         [int(i * (len(tss) - 1) / (max_snapshots - 1))
                          for i in range(1, max_snapshots - 1)]))
        tss = [tss[i] for i in idx]
    for ts in tss:
        content = fetch_snapshot(ts, url)
        if not content:
            continue
        try:
            p = extract_and_store(ts, url, content, place_id)
        except Exception as e:  # noqa: BLE001
            print(f"  {ts}: extract fail: {str(e)[:80]}")
            continue
        if p:
            d = p["result"]
            print(f"  {p['observed_on']} menu={d.get('is_menu')} "
                  f"items={len(d.get('items') or [])} ${p['cost_usd']}")
            out.append(p)
    return out


if __name__ == "__main__":
    # usage: python wayback.py <menu-url> [place_id]
    url = sys.argv[1]
    pid = sys.argv[2] if len(sys.argv) > 2 else None
    harvest(url, pid)
