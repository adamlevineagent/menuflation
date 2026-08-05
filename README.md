# menuflation

**Real food-price inflation, tracked from Google Maps menu photos.**

Restaurant menu photos on Google Maps are a decade-long global price
time-series sitting in plain sight. menuflation collects them, reads the
prices with a cheap vision model, and turns them into dated price series —
per item, per place, per city.

## How it works

1. **collect** — `collect.py` runs a place list (`places.json`) through the
   official Google Places API (new): `searchText` → photo references →
   photo downloads at 2048px. Resumable per-place manifests.
2. **extract** — `extract.py` sends every photo to `qwen/qwen3.7-flash`
   (OpenRouter) with a strict JSON schema: items, prices, struck-through
   old prices, sizes, currency. ~$0.0001/photo; resumable, deduped by ref.
3. **date** — `upgrade_menus.py` re-downloads menu photos at 2048px, which
   preserves EXIF `DateTimeOriginal` on most contributor photos (the 1280px
   re-encode strips it). That capture date anchors the observation on the
   time axis. `date_source` keeps EXIF-dated rows honest vs fallbacks.
4. **match** — `pipeline.py` ingests into SQLite, canonicalizes item names
   with portion-aware token-set matching (`Double Cheeseburger` ≠
   `Cheeseburger`; `cheese burger` = `cheeseburger`), converts FX to USD
   (ECB via Frankfurter), and writes price series + YoY + CSVs.
5. **dashboard** — `dashboard.py` emits a self-contained dark-theme HTML
   dashboard: dated price-series charts, per-place stats, budget meter.

## Quickstart

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
# .env: OPENROUTER_API_KEY, GOOGLE_API_KEY
.venv/Scripts/python collect.py      # photos for places.json
.venv/Scripts/python extract.py      # classify + extract (OpenRouter)
.venv/Scripts/python upgrade_menus.py  # hi-res menu photos + EXIF dates
.venv/Scripts/python pipeline.py     # DB, matching, series
.venv/Scripts/python dashboard.py    # data/reports/dashboard.html
```

## Budget

- qwen3.7-flash: $0.03 in / $0.13 out per 1M tokens ≈ **$0.0001/photo**
  (578 photos cost $0.045).
- Places API (new): free tier covers ~11k place calls/month.
- FX: Frankfurter (ECB) — free.

## Notes

- Photo upload dates would be ideal; the API doesn't expose them. EXIF
  capture dates are the best available proxy and work on most contributor
  photos at 2048px.
- Some networks blackhole specific `googleapis.com` IPs — `places_api.py`
  pins a verified-good anycast IP (getaddrinfo shim).
