# GOALS — menuflation

## Mission (operator-assigned, self-adopted)

> Build and fully populate a web dashboard that shows the menuflation rate —
> real food-price inflation measured from restaurant menus — **in aggregate and
> in every useful way we find it expressable**.

Same-store discipline is non-negotiable: inflation is measured only as
same-item, same-size, same-store price movement across DATED observations
(photo EXIF dates, Maps gallery labels, Wayback snapshot dates). Cross-store
differences are tiers, not inflation.

## Definition of done (all must hold)

1. **Aggregate index live**: the median-ratio chained index has **≥ 2 distinct
   index months with ≥ 5 same-store pairs each**, and the annualized-rate card
   is rendering.
2. **Temporal depth**: **≥ 3 stores** each have **≥ 3 dated observations of at
   least one identical item** (multi-year series, not snapshots).
3. **Breakdowns**: the dashboard expresses the rate per city/state, per price
   tier (inexpensive/moderate/expensive), and per data source
   (exif/dom/wayback) — as charts or tables, with a filter or selector.
4. **Wayback contribution**: ≥ 20 dated lines harvested from ≥ 2 stores via
   the Wayback Machine (PDF menus or server-rendered price pages).
5. **Coverage map**: the coverage matrix shows ≥ 3 places with ≥ 3 calendar
   years of dated observations.
6. **Ground-truth validation**: the data SHOWS the operator's known reality —
   Barney's Burgers and El Charro Viejo price increases over their real
   histories. If it doesn't, the gap is documented (temporal depth missing,
   not noise).
7. **Hygiene**: every working state committed; changed paths verified
   (`python scripts/verify_aggregate.py` + focused hermes-verify passes);
   OpenRouter budget tracked (≈ $9.9 remaining as of Aug 2026).

## Current state (Aug 2026)

- ✅ Aggregate machinery built and verified (median-ratio chaining, coverage
  matrix, dashboard v2 with index chart / pair evidence / YoY / coverage).
- ⚠️ Only ONE index month exists (2025-08, 7 pairs) — no annualized card yet.
- ⚠️ Temporal depth thin: Barney's 2024→2025 (flat), Genova 2024→now (flat);
  no store has 3+ dated same-item observations.
- ⚠️ Wayback: 0 lines harvested. Discovery shows menu pages are JS shells
  (Burgerville 91 snapshots, Dutch Bros 80 — no inline prices); PDF menus are
  the hunt.
- ✅ Coverage matrix exists; 4 calendar years (2022-2026) but few multi-year
  places.

## How the heartbeat measures progress

Each tick updates the skill Status with numbers against these criteria. The
goal is met when all 7 hold; the operator's eyeball on the dashboard is the
final acceptance test.
