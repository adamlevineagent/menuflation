"""db.py — SQLite storage + ingest from extraction JSONs."""
import glob
import json
import os
import sqlite3
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS places(
  id TEXT PRIMARY KEY,
  name TEXT, address TEXT, lat REAL, lng REAL,
  city TEXT, state TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS photos(
  ref TEXT PRIMARY KEY,
  place_id TEXT, file TEXT, width INTEGER, height INTEGER,
  extracted_at TEXT, cost_usd REAL
);
CREATE TABLE IF NOT EXISTS canonical_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE, category TEXT
);
CREATE TABLE IF NOT EXISTS menu_lines(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  photo_ref TEXT, place_id TEXT,
  item_raw TEXT, price REAL, old_price REAL,
  size TEXT, qty INTEGER, unit TEXT, notes TEXT,
  currency_iso TEXT, confidence REAL,
  canonical_id INTEGER, price_usd REAL, fx_rate REAL, fx_date TEXT,
  observed_on TEXT, date_hints TEXT
);
CREATE INDEX IF NOT EXISTS idx_lines_place ON menu_lines(place_id);
CREATE INDEX IF NOT EXISTS idx_lines_canon ON menu_lines(canonical_id);
CREATE INDEX IF NOT EXISTS idx_lines_obs ON menu_lines(observed_on);
"""


def connect(path="data/menuflation.db"):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def _place_id_from_photo_name(photo_name):
    parts = photo_name.split("/")
    return parts[1] if len(parts) >= 3 else None


def ingest(conn, extractions_dir="data/extractions",
           places_dir="data/places", observed_on=None):
    """Load manifests into places; load extraction JSONs into photos+menu_lines.

    Idempotent: upserts by key. Re-running after a resume re-covers everything.
    """
    observed_on = observed_on or date.today().isoformat()
    # --- places from manifests ---
    for mf in sorted(glob.glob(os.path.join(places_dir, "*.json"))):
        m = json.load(open(mf, encoding="utf-8"))
        for p in m["places"]:
            conn.execute(
                "INSERT INTO places(id,name,address,lat,lng,city,state,source) "
                "VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
                "address=excluded.address,lat=excluded.lat,lng=excluded.lng",
                (p["id"], p.get("name"), p.get("address"), p.get("lat"),
                 p.get("lng"), m.get("city"), m.get("state"), "places-api"))
    # --- photos + menu lines from extractions ---
    n_photos = n_lines = n_menus = 0
    for jf in sorted(glob.glob(os.path.join(extractions_dir, "**", "*.json"),
                               recursive=True)):
        if os.path.basename(jf) == "index.json":
            continue
        try:
            payload = json.load(open(jf, encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        name = payload.get("photo", "")
        pid = _place_id_from_photo_name(name)
        result = payload.get("result") or {}
        conn.execute(
            "INSERT INTO photos(ref,place_id,file,extracted_at,cost_usd) "
            "VALUES(?,?,?,?,?) ON CONFLICT(ref) DO NOTHING",
            (name, pid, payload.get("src"), payload.get("extracted_at")
             or observed_on, payload.get("cost_usd")))
        n_photos += 1
        if not result.get("is_menu"):
            continue
        n_menus += 1
        cur = result.get("currency_iso")
        hints = json.dumps(result.get("date_hints") or [], ensure_ascii=False)
        for it in result.get("items") or []:
            price = it.get("price")
            if price is None:
                continue
            conn.execute(
                "INSERT INTO menu_lines(photo_ref,place_id,item_raw,price,"
                "old_price,size,qty,unit,notes,currency_iso,confidence,"
                "observed_on,date_hints) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, pid, it.get("name"), price, it.get("old_price"),
                 it.get("size"), it.get("qty"), it.get("unit"),
                 it.get("notes"), cur, result.get("confidence"),
                 observed_on, hints))
            n_lines += 1
    conn.commit()
    nplaces = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
    return {"places": nplaces, "photos": n_photos, "menus": n_menus,
            "menu_lines": n_lines}
