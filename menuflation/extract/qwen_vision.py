"""qwen_vision.py — menu-photo -> structured prices via OpenRouter qwen vision.

One photo, one call. Tracks real cost from the usage payload so the
$10 budget is visible at every step.
"""
import base64
import json
import os
import time

import requests

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.7-flash")
IN_PRICE_PER_M, OUT_PRICE_PER_M = 0.03, 0.13  # $ per 1M tokens (qwen/qwen3.7-flash)

EXTRACTION_PROMPT = """You are a menu-price extraction engine for a global food-inflation study. Read the menu photo and return STRICT JSON only — no markdown, no commentary, no code fences.

Schema:
{
  "is_menu": true|false,          // false if this is not a menu photo
  "currency_iso": "USD",          // ISO 4217 code if identifiable, else null
  "currency_symbol": "$",         // symbol as printed
  "items": [
    {
      "name": "Reuben Sandwich",  // exact transcription, title case
      "price": 24.95,             // numeric, no symbol. null if not readable
      "old_price": 22.95,         // struck-through/previous price if visible, else null
      "size": null,               // "S"/"M"/"L", "16 oz", "1/2 lb", "small plate" etc
      "qty": null,                // if a price covers multiple, e.g. "2 for $5" -> 2
      "unit": null,               // ONLY measurement units: per item, per kg, per 100g, per dozen, per lb. NEVER preparation or serving style.
      "notes": "with fries"       // any qualifier that changes the price: "on rye", "with fries", "add cheese", "for 2" etc
    }
  ],
  "date_hints": ["dates or date-ish text visible on the photo, e.g. 'prices as of 2024'"],
  "restaurant_hint": "name visible on the menu, else null",
  "confidence": 0.9               // 0..1 how readable the prices were
}

Rules:
- Transcribe item names as printed; never invent or guess items.
- Parse prices to numbers; a price like "9." or ".99" with context is allowed only if clearly resolvable.
- If an item has no readable price, omit it.
- Handwritten prices count. Discounts, happy-hour rows, and combos count — capture them with notes.
- old_price is for struck-through or crossed-out prices — critical for inflation tracking.
- Measurements and sizes go in size or unit, NEVER in the name: "1/2 lb Colossal Burger" -> name "Colossal Burger", size "1/2 lb". "Coffee 12 oz" -> name "Coffee", size "12 oz".
- If is_menu is false, return {"is_menu": false, "items": []} and nothing else.
"""


class ExtractionError(Exception):
    pass


# Text-mode variant of the extraction prompt — same schema, no image. Used for
# Wayback menu pages and PDF menus: clean text in, structured prices out.
TEXT_EXTRACTION_PROMPT = """You are a menu-price extraction engine for a global food-inflation study. Below is the text of a restaurant menu. Return STRICT JSON only — no markdown, no commentary, no code fences.

Schema:
{
  "is_menu": true|false,
  "currency_iso": "USD",
  "currency_symbol": "$",
  "items": [
    {
      "name": "Cheeseburger",
      "price": 7.95,
      "old_price": null,
      "size": null,
      "qty": null,
      "unit": null,
      "notes": null
    }
  ],
  "date_hints": [],
  "restaurant_hint": null,
  "confidence": 0.9
}

Rules:
- Extract every menu item that has a price. Skip items without prices.
- Parse prices as numbers; ignore taxes, fees, and non-item text.
- Measurements and sizes go in size or unit, NEVER in the name.
- Multiple size variants of one item ("Small/Large Fries" or separate lines) are separate items with their size filled in.
- If the text is not a menu, return {"is_menu": false, "items": []}.

Menu text follows:
"""


def image_to_data_url(path):
    ext = path.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def cost_usd(usage):
    i = usage.get("prompt_tokens", 0)
    o = usage.get("completion_tokens", 0)
    return i * IN_PRICE_PER_M / 1e6 + o * OUT_PRICE_PER_M / 1e6, i, o


def _parse_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def extract_menu_photo(photo_path, api_key=None, model=DEFAULT_MODEL, timeout=180):
    """One menu photo -> extraction dict. Returns {ok, data|error, usage, cost_usd}."""
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ExtractionError("OPENROUTER_API_KEY not set")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/adamlevineagent/menuflation",
        "X-Title": "menuflation",
    }
    content = [
        {"type": "text", "text": EXTRACTION_PROMPT},
        {"type": "image_url", "image_url": {"url": image_to_data_url(photo_path)}},
    ]
    payload = {"model": model, "messages": [{"role": "user", "content": content}], "temperature": 0}
    last_err = None
    for outer in range(3):  # transient 429/5xx — back off and retry
        for attempt in range(2):  # try strict json mode, then plain
            body = dict(payload)
            if attempt == 0:
                body["response_format"] = {"type": "json_object"}
            try:
                r = requests.post(ENDPOINT, headers=headers, json=body, timeout=timeout)
                if r.status_code != 200:
                    last_err = f"HTTP {r.status_code}: {r.text[:300]}"
                    if r.status_code in (429, 500, 502, 503):
                        time.sleep(3 + 4 * outer)
                        break  # transient: outer retry
                    if r.status_code in (400, 404, 422):
                        continue  # retry without response_format
                    break
                data = r.json()
                usage = data.get("usage", {})
                c, tin, tout = cost_usd(usage)
                msg = data["choices"][0]["message"]["content"]
                try:
                    parsed = _parse_response(msg)
                except json.JSONDecodeError:
                    parsed = {"raw": msg}
                return {"ok": True, "data": parsed, "usage": usage, "tokens_in": tin,
                        "tokens_out": tout, "cost_usd": round(c, 6), "model": model}
            except requests.RequestException as e:
                last_err = str(e)
                time.sleep(1)
    raise ExtractionError(f"extraction failed: {last_err}")


def extract_menu_text(menu_text, api_key=None, model=DEFAULT_MODEL, timeout=120):
    """Menu TEXT -> extraction dict (Wayback/PDF pipeline, no image tokens).

    Returns {ok, data, usage, tokens_in, tokens_out, cost_usd, model}.
    """
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ExtractionError("OPENROUTER_API_KEY not set")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/adamlevineagent/menuflation",
        "X-Title": "menuflation",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user",
                      "content": TEXT_EXTRACTION_PROMPT + menu_text[:12000]}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    last_err = None
    for attempt in range(3):  # upstream 429s are transient — back off, retry
        r = requests.post(ENDPOINT, headers=headers, json=payload, timeout=timeout)
        if r.status_code == 200:
            break
        last_err = f"extract_menu_text HTTP {r.status_code}: {r.text[:200]}"
        if r.status_code in (429, 500, 502, 503):
            time.sleep(3 + 4 * attempt)
            continue
        raise ExtractionError(last_err)
    if r.status_code != 200:
        raise ExtractionError(last_err)
    data = r.json()
    usage = data.get("usage", {})
    c, tin, tout = cost_usd(usage)
    try:
        parsed = _parse_response(data["choices"][0]["message"]["content"])
    except (json.JSONDecodeError, KeyError) as e:
        raise ExtractionError(f"bad JSON from model: {e}") from e
    return {"ok": True, "data": parsed, "usage": usage, "tokens_in": tin,
            "tokens_out": tout, "cost_usd": round(c, 6), "model": model}


def check_key(api_key=None):
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    r = requests.get("https://openrouter.ai/api/v1/auth/key",
                     headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    if r.status_code != 200:
        return {"ok": False, "error": r.text[:300]}
    d = r.json().get("data", {})
    return {"ok": True, "label": d.get("label"), "usage": d.get("usage", 0),
            "limit": d.get("limit"), "is_free": d.get("is_free_tier"),
            "rate_limit": d.get("rate_limit")}
