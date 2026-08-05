# menuflation

Reads menu photos from Google Maps listings, extracts item prices with a cheap
vision model (qwen/qwen3.7-flash via OpenRouter, ~$0.0001/photo), and tracks
real food-price inflation across places, cities, and countries over time.

## Why it works

Google Maps menu photos carry upload dates. A photo of a menu board uploaded
in 2019 is a price observation for 2019 — so a place's photo history is a
price time-series, and the whole planet's is a global inflation dataset.

## Pipeline

1. **collect** — pull menu photos (upload dates included) for places on a
   curated list. Backends: Google Maps, official Places API (needs a Google
   key), or a local import folder.
2. **extract** — qwen vision -> strict JSON (items, prices, currency,
   struck-through old prices, size/unit/qty).
3. **match** — normalize item names/units, match across photos -> canonical
   items per place.
4. **index** — FX to USD (ECB rates via Frankfurter), per-place and
   per-country price series, YoY % change, basket indices.
5. **report** — CSV export + HTML dashboard.

## Quickstart

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env   # or edit .env with your OPENROUTER_API_KEY
.venv/Scripts/python spike.py some_menu_photo.jpg
```

## Budget

qwen/qwen3.7-flash: $0.03 in / $0.13 out per 1M tokens. One menu photo is
roughly 1.5k in + 400 out tokens ≈ $0.0001. The $10 test key ≈ 100k photos.
