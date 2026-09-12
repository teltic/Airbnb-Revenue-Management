# Airbnb-Revenue-Management

Daily pacing/pickup tracker for two PriceLabs listings (Mesquite Vacation
Rental, Game Room), built against PriceLabs' Customer API. See
`pricelabs_script_spec.md` (shared separately) for the full spec this
implements.

## Status

- [x] Data pull (`pacing_tracker/`) — pulls occupancy, market occupancy,
      LY/STLY, and self-computed pickup for the next 365 days, blended
      across both listings.
- [ ] Excel report generation with live formulas (next phase).
- [ ] Push mode (reads reviewed Override Request/Notes columns back to
      PriceLabs) (later phase, separate from this one).

## Setup

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PRICELABS_API_KEY=...   # from PriceLabs Account Settings > API Details
```

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

## Known unknowns — verify against your real API key

This dev environment's network policy blocks outbound calls to
`api.pricelabs.co`, so none of this has been smoke-tested against a live
key yet — only against the shapes of real responses fetched via an
already-authenticated internal tool during development. Before relying on
scheduled daily runs, do one manual run and check:

1. **Base URL / auth header** (`pacing_tracker/config.py`,
   `pacing_tracker/api_client.py`): currently assumes
   `https://api.pricelabs.co/v1` and an `X-API-Key` header. Adjust either
   via `PRICELABS_API_BASE_URL` env var or by editing `api_client.py` if
   your account's API docs (Settings > API Details) say otherwise.
2. **neighborhood_data comp-set category**: if a listing's response has
   more than one entry under `Future Occ/New/Canc.Category`, the code
   currently auto-picks the one with the most `Listings Used` and logs a
   warning — confirm that's the right one for these two listings.
3. **reservation_data pagination**: uses `limit`/`offset` query params
   based on the field names PriceLabs' own tooling exposes; if the real
   API paginates differently, `_fetch_all_reservations` in
   `pacing_tracker/data_pull.py` needs updating.

## Configuration

Listings, thresholds, and the median-booking-window reference table all
live in `pacing_tracker/config.py` as plain data — no thresholds are
hardcoded into the pacing/signal/bump logic (that logic is the next
phase, once the Excel generation step is built).
