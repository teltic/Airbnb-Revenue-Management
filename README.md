# Airbnb-Revenue-Management

Daily pacing/pickup tracker for two PriceLabs listings (Mesquite Vacation
Rental, Game Room), built against PriceLabs' Customer API. See
`pricelabs_script_spec.md` (shared separately) for the full spec this
implements.

## Status

- [x] Data pull (`pacing_tracker/`) — pulls occupancy, market occupancy,
      LY/STLY, and self-computed pickup for the next 365 days, blended
      across both listings. Verified end-to-end against the live account.
- [ ] Excel report generation with live formulas (next phase).
- [ ] Push mode (reads reviewed Override Request/Notes columns back to
      PriceLabs) (later phase, separate from this one).

## Setup

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Then create a file named `.env` in the project root (same folder as this
README) containing one line:

```
PRICELABS_API_KEY=your-actual-key-here
```

The script loads it automatically — no terminal environment-variable step
needed. `.env` is already excluded from git via `.gitignore`, so it never
gets committed.

Run the tests (no API key or network needed — they run against fake/mocked
responses shaped like real API replies):

```
python3 -m unittest discover -s tests -v
```

Run a real pull once you have a key:

```
python3 -m pacing_tracker.data_pull --out data/pull_today.json
```

## How pacing/pickup is sourced

The chat-based prototype pulled this data from a PriceLabs Report Builder
template ("Master Sheet - TB") that returns exactly the fields the spec
wants (Market Occupancy, LY, STLY, Pickup 3/7/14/30/60d) pre-blended across
both listings. That template is reachable through PriceLabs' internal MCP
tools, but it's unconfirmed whether it's exposed on the public,
API-key-based Customer API used by this script — PriceLabs' own docs
weren't reachable to verify from this dev environment (see "Known
unknowns" below).

So this script instead combines two endpoints that **are** documented as
part of the Customer API:

- `neighborhood_data` (per listing) — daily Market Occupancy / LY / STLY
  curve for the listing's comp set.
- `reservation_data` (per listing) — actual reservations, used to derive
  whether a given date is booked for that listing (0%/100%).

Both listings' results are then averaged per date to produce the
portfolio-blended numbers the spec calls for.

**Pickup is self-computed**, not pulled directly: `neighborhood_data` only
ever returns *today's* curve, so `pacing_tracker/snapshot_cache.py` saves
each day's curve to `data/snapshot_cache.json`, and pickup for a given
window = today's value minus the value recorded N days ago for that same
future date. Practical effect: pickup3d/7d/14d become meaningful within
2-3 weeks of the script running daily; pickup30d/60d need 30-60 days of
accumulated history. Until a window has enough history, that field is
`None` (renders blank in the report) rather than a misleading zero.

## Verified against the live account (2026-09-12)

The assumptions below were unconfirmed during initial development (this
dev environment's network policy blocks outbound calls to
`api.pricelabs.co`) but have since been smoke-tested end-to-end from the
user's own machine, against real data for both listings:

1. **Base URL / auth header**: `https://api.pricelabs.co/v1` with an
   `X-API-Key` header both work as assumed.
2. **neighborhood_data comp-set category**: Mesquite has a single category
   (no ambiguity). Game Room has 5 (bedroom-count buckets `9/5/4/2/3`) —
   `NEIGHBORHOOD_CATEGORY_OVERRIDES` in `config.py` pins it to `"4"`,
   confirmed against that listing's actual "Bedrooms" field in PriceLabs
   (its title text still says 5BR/2BA, but that field is what
   neighborhood_data segments by, and it correctly reads 4). If this
   listing's bedroom count is ever corrected/changed in PriceLabs, or a
   new listing gets added with more than one comp-set category, re-check
   this override.
3. **reservation_data pagination**: the live response shape is
   `{"data": [...rows...], "next_page": ...}` — `"data"` is directly the
   row list, not a further-nested object. `_extract_reservation_rows` in
   `data_pull.py` handles this (and, defensively, a nested shape too).
4. **neighborhood_data's future curve doesn't quite cover the full 365
   days**: live, it covers 360 of 365 (blank for roughly the last 5 days
   of the window). `occupancy_pct` still populates for those tail dates
   since it comes from `reservation_data`, not the curve. Not treated as a
   bug — nobody's acting on pacing signals 360+ days out anyway — but
   worth knowing if the Excel report shows blank Market Occ%/pace columns
   right at the far edge of the sheet.

## Configuration

Listings, thresholds, and the median-booking-window reference table all
live in `pacing_tracker/config.py` as plain data — no thresholds are
hardcoded into the pacing/signal/bump logic (that logic is the next
phase, once the Excel generation step is built).
