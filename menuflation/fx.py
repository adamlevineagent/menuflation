"""fx.py — price conversion to USD (ECB rates via Frankfurter, cached).

USD short-circuits to 1.0. US-first: most data is already USD; this exists so
the machinery is ready when the dataset goes international.
"""
import json
import os
import time

import requests

CACHE = os.path.join("data", "fx_cache.json")


def _load_cache():
    if os.path.exists(CACHE):
        try:
            return json.load(open(CACHE, encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(c):
    os.makedirs("data", exist_ok=True)
    json.dump(c, open(CACHE, "w", encoding="utf-8"))


def rate_to_usd(currency, on_date=None):
    """USD per 1 unit of currency on on_date (ISO). USD -> 1.0. None if unknown."""
    if not currency or currency.upper() == "USD":
        return 1.0
    c = _load_cache()
    key = f"{currency.upper()}:{on_date or 'latest'}"
    if key in c and time.time() - c[key]["t"] < 7 * 86400:
        return c[key]["rate"]
    try:
        url = "https://api.frankfurter.app/latest"
        r = requests.get(url, params={"from": "USD", "to": currency.upper()}, timeout=30)
        r.raise_for_status()
        # Frankfurter gives units of `to` per 1 USD; we want USD per 1 unit
        rate = 1.0 / r.json()["rates"][currency.upper()]
    except Exception:
        return None
    c[key] = {"rate": rate, "t": time.time()}
    _save_cache(c)
    return rate
