# Airbnb-Revenue-Management

Daily pacing/pickup tracker for two PriceLabs listings (Mesquite Vacation
Rental, Game Room), built against PriceLabs' Customer API. See
`pricelabs_script_spec.md` (shared separately) for the full spec this
implements.

## Status

- [x] Data pull (`pacing_tracker/`) — pulls Occupancy, Market Occupancy,
      LY/STLY, and Pickup 3/7/14/30/60d for the next 365 days, pre-blended
      across both listings by PriceLabs itself. Verified end-to-end
      against the live account.
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

This pulls directly from PriceLabs' **Report Builder** — specifically the
"Master Sheet - TB" template, the same one the chat-based prototype used —
via `report_builder/templates`, `report_builder/data`, and
`report_builder/poll`. This was originally assumed to be internal/session-only
(not reachable from a plain Customer API key), so an earlier version of this
script instead combined `neighborhood_data` + `reservation_data` and
self-computed pickup from a local snapshot history. Live testing
(2026-09-12) showed Report Builder **is** reachable from a plain API key,
so that whole workaround was removed — this is simpler and gives correct
pickup values immediately instead of needing 30-60 days of accumulated
history.

Each report row already comes blended across both listings
(`Listing Count: 2`) and pre-computed:

```
Date, Weekday, Occupancy,
Average Market Occupancy, Average Market Occupancy LY, Average Market Occupancy STLY,
Average Market Occupancy Pickup 3/7/14/30/60
```

`data_pull.py` looks up the template by name (`config.REPORT_BUILDER_TEMPLATE_NAME`,
not a hardcoded template_id, since that's stable even if the account's
template list changes), fetches it (polling if PriceLabs computes it
asynchronously), and filters/sorts rows down to the requested date window.
Weekday is recomputed from `Date` directly rather than trusting PriceLabs'
own weekday string format, since we need a plain 3-letter name to match
`config.WEEKEND_DAYS`.

## Verified against the live account (2026-09-12)

- **Base URL / auth header**: `https://api.pricelabs.co/v1` with an
  `X-API-Key` header both work.
- **Report Builder reachable via API key**: confirmed — see above.
- **Report Builder's horizon isn't quite a full 365 days out**: in one
  live pull, 360 of 365 requested days had data (blank for roughly the
  last 5 days of the window). Not treated as a bug — nobody's acting on
  pacing signals 360+ days out anyway — but worth knowing if the Excel
  report shows blank rows right at the far edge of the sheet.

## Configuration

Listings, thresholds, and the median-booking-window reference table all
live in `pacing_tracker/config.py` as plain data — no thresholds are
hardcoded into the pacing/signal/bump logic (that logic is the next
phase, once the Excel generation step is built). `LISTINGS` isn't used by
the data-pull stage (Report Builder already blends both listings), but
will be needed by the push phase, which pushes overrides per listing.
