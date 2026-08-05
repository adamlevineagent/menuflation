# GOALS — menuflation

## Mission (operator-assigned, self-adopted)

> Build and fully populate a web dashboard that shows the menuflation rate —
> real food-price inflation measured from restaurant menus — **in aggregate and
> in every useful way we find it expressable**.

### Why this exists (the maximal solution)

Official inflation is measured **for government purposes** — which structurally
includes avoiding blame for high inflation and avoiding cost-of-living
obligations to low-income Americans, service workers, and retirees. Official
numbers are therefore systematically shaped by that conflict.

menuflation is the counterweight: **provably and historically measure inflation
as it is experienced by people.** Every number traces to an artifact (a dated
menu photo, a Wayback snapshot, a menu PDF) — auditable by anyone. We shouldn't
need to build this, but we can, it's easy, and it's fun — so maximum fun, no
grimness. The dashboard is OURS, not BLS's.

### Emergent baskets (design principle)

Groupings **emerge from the data** — they are not imposed. The universal items
(cheeseburger, french fries, drinks) are the anchors: once we hold ~100 dated
historical records of cheeseburger and french-fries prices across many
restaurants, the **cheeseburger average** and **fries average** simply exist.
From there every other grouping (per city, per tier, per chain, per year)
emerges the same way. The fixed-basket CPI methodology is the thing we're
replacing, not copying.

## Definition of done (all must hold)

1. **Aggregate index live**: the median-ratio chained index has **≥ 2 distinct
   index months with ≥ 5 same-store pairs each**, and the annualized-rate card
   is rendering.
2. **Emergent averages**: **≥ 100 dated records each** for **cheeseburger** and
   **french fries** across ≥ 10 distinct restaurants, with per-year median
   series (the cheeseburger average / fries average) rendering on the
   dashboard.
3. **Temporal depth**: **≥ 3 stores** each have **≥ 3 dated observations of at
   least one identical item** (multi-year series, not snapshots).
4. **Breakdowns**: the dashboard expresses the rate per city/state, per price
   tier (inexpensive/moderate/expensive), and per data source
   (exif/dom/wayback) — as charts or tables, with a filter or selector.
5. **Wayback contribution**: ≥ 20 dated lines harvested from ≥ 2 stores via
   the Wayback Machine (PDF menus or server-rendered price pages).
6. **Coverage map**: the coverage matrix shows ≥ 3 places with ≥ 3 calendar
   years of dated observations.
7. **Ground-truth validation**: the data SHOWS the operator's known reality —
   Barney's Burgers and El Charro Viejo price increases over their real
   histories. If it doesn't, the gap is documented (temporal depth missing,
   not noise).
8. **Provenance**: every priced line links to its artifact (photo file,
   snapshot URL, PDF) — provability is the point.
9. **Hygiene**: every working state committed; changed paths verified
   (`python scripts/verify_aggregate.py` + focused hermes-verify passes);
   OpenRouter budget tracked (≈ $9.9 remaining as of Aug 2026).

## Current state (Aug 2026)

- ✅ Aggregate machinery built and verified (median-ratio chaining, coverage
  matrix, dashboard v2 with index chart / pair evidence / YoY / coverage).
- ✅ Emergent-average machinery (item_averages) being added — cross-store
  dated medians per year per canonical item.
- ⚠️ Only ONE index month exists (2025-08, 7 pairs) — no annualized card yet.
- ⚠️ Cheeseburger records ≈ 20; fries ≈ 15 — far from the 100-record target.
  Collection strategy should deliberately favor places/sources yielding the
  universal items.
- ⚠️ Wayback: 0 lines harvested. Menu pages are JS shells; PDFs are the hunt.
- ✅ Coverage matrix exists; 4 calendar years (2022-2026) but few multi-year
  places.

## How the heartbeat measures progress

Each tick updates the skill Status with numbers against these criteria. The
goal is met when all 9 hold; the operator's eyeball on the dashboard is the
final acceptance test.
