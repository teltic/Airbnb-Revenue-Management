# Airbnb-Revenue-Management

Daily pacing/pickup tracker for two PriceLabs listings (Mesquite Vacation
Rental, Game Room), built against PriceLabs' Customer API. See
`pricelabs_script_spec.md` (shared separately) for the full spec this
implements.

## Status

- [x] Data pull (`pacing_tracker/data_pull.py`) — pulls Occupancy, Market
      Occupancy, LY/STLY, and Pickup 3/7/14/30/60d for the next 366 days
      (today through +365), pre-blended across both listings by PriceLabs
      itself. Verified end-to-end against the live account.
- [x] Excel report generation (`pacing_tracker/excel_report.py`) — builds
      the Daily Pacing workbook with live formulas (Pace vs STLY, Signal,
      Suggested Bump, Override Status, New Since Last Review), matching a
      real reference workbook the user built via chat-based Claude.
      Formulas verified by direct comparison against that file's actual
      cell contents. Verified end-to-end (generated, opened in Excel, no
      formula errors, conditional formatting renders correctly) against
      the live account.
- [x] Push mode (`pacing_tracker/push.py`) — reads Override Request/Notes
      from a reviewed workbook and pushes them to PriceLabs as
      date-specific percent overrides. Dry-run by default. **Not yet
      smoke-tested against the live account** — the write endpoint's
      exact path is an assumption (see "Known limitation" below); test
      with `--dry-run` (the default) before ever passing `--confirm`.

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
Weekday is passed through exactly as PriceLabs returns it (e.g. `"05.Fri"`)
to match the reference workbook, rather than recomputed from `Date`.

## Excel report generation

`pacing_tracker/excel_report.py` reads a `data_pull.py` JSON output and
builds the "Daily Pacing" workbook. It's built to match a real reference
file (`Daily_Pacing_Pickup_9.11.26.xlsx`) the user had already produced via
chat-based Claude — same headers, same formulas, same threshold cell
layout (`Z1:AA30` on Daily Pacing), same conditional formatting. The
Suggested Bump, Signal, Override Status, and New Since Last Review formulas
in `excel_report.py` were extracted verbatim from that file (see the
`REFERENCE_*` constants in `tests/test_excel_report.py`) and are only
templated by row number — not redesigned or reverse-engineered from the
spec text alone.

A few things worth knowing about how it works:

- **Occupancy/Market Occ/LY/STLY/Pickup are raw pulled values, not
  formulas** — they can't recalculate from anything else, they *are* the
  data. Pace vs STLY, the two ratio columns, Suggested Bump, Signal, Days
  Out, Median Booking Window, Override Status, and New Since Last Review
  are all live formulas.
- **Suggested Note bakes in the pull date as a literal string** (e.g.
  `"9/12 - Pacing behind by..."`), matching the reference file — it's a
  timestamp of when the observation was made, not a `TODAY()` formula that
  would silently reword itself every time the file is reopened.
- **Override Request/Notes are carried forward** from the most recent
  earlier `Daily_Pacing_Pickup_*.xlsx` in `config.DRIVE_SYNC_FOLDER`, keyed
  by date (see `carryforward.py`) — a rebuild never wipes manual input.
  With no prior file (e.g. the very first run), these are just blank.
- **New Since Last Review also needs carry-forward**: it bakes the
  *previous* file's Signal for that date into the formula as a literal
  string, compared against the *live* Signal formula for the same row —
  so it's really asking "does today's live Signal show something the
  snapshot from last time didn't." A date with no prior snapshot compares
  against `""`.
- `config.DRIVE_SYNC_FOLDER` should point at a folder synced by the Google
  Drive desktop app — this only ever touches plain files on disk, no
  Drive API/OAuth. Set via the `PACING_DRIVE_SYNC_FOLDER` env var (or in
  `.env`, same as the API key); defaults to `data/` if unset.
- Only the **Daily Pacing** and **Booking Window** sheets are generated —
  the reference file's How To Use / Daily Process / Properties & Overrides
  tabs were left out (by choice) to keep the generator focused on the data
  itself.

Run it:

```
python3 -m pacing_tracker.excel_report --in data/pull_today.json
```

### Note: this dev environment can't run LibreOffice to self-check

This dev environment's LibreOffice hangs indefinitely on *any* file
(even a trivial one-formula test), which is the tool this environment
would normally use to mechanically verify zero formula errors before
calling a spreadsheet done. That check could not run here, so verification
happened two other ways instead: every generated formula that has a
real-world counterpart was compared character-for-character against the
actual cell contents of the user's reference workbook (see
`tests/test_excel_report.py`), and the user opened a real generated file
in Excel directly (2026-09-12) — no `#REF!`/`#VALUE!`/`#NAME?` errors,
correct formulas and thresholds. One real bug was caught this way that
the character-comparison approach couldn't have found on its own:
conditional-format fills need color in `bgColor` with `patternType`
unset, not the `fgColor`/`"solid"` convention for an ordinary cell fill —
using the wrong one meant every color rule wrote successfully but
rendered invisibly. Fixed and covered by a regression test.

## Push mode

`pacing_tracker/push.py` reads Override Request (column Q) and Notes
(column R) from a reviewed workbook and pushes them to PriceLabs as
date-specific `price_type: "percent"` overrides, per the spec's push
workflow:

- Blank Override Request cells and any date already in the past are
  skipped.
- Pushed to **both** configured listings by default (`--listing-id` to
  restrict to one) — Pace/Pickup are market-level signals shared by both
  listings, not listing-specific.
- Notes text becomes the override's `reason` (truncated to 255 chars,
  PriceLabs' own limit).
- **Dry-run by default.** Nothing is ever written to PriceLabs unless you
  pass `--confirm`.

```
python3 -m pacing_tracker.push --workbook path/to/Daily_Pacing_Pickup_9.12.26.xlsx              # dry run
python3 -m pacing_tracker.push --workbook path/to/Daily_Pacing_Pickup_9.12.26.xlsx --confirm     # actually pushes
```

**Why even a dry run makes API calls**: PriceLabs bundles multiple
settings into one override object per date (confirmed against a real
override on the live account: `{"date": "2026-09-12", "price": "-10",
"price_type": "percent", "min_stay": 2, "min_price": 650,
"min_price_type": "fixed", "currency": "USD", "reason": "..."}`), and the
update endpoint replaces a date's override wholesale — it doesn't merge
field-by-field. So a bare `{date, price}` push would silently wipe any
existing `min_stay`/`min_price`/etc. on that date. To prevent that,
`push.py` first does a **read-only** GET of each listing's current
overrides and merges the new price/reason on top of whatever's already
there, in both dry-run and real mode — only the final write is gated by
`--confirm`.

### Known limitation: the write endpoint is unverified

Both endpoints live at `listings/{listing_id}/overrides` (GET to read,
POST to write) — not `listing_data/{listing_id}/overrides` as first
assumed by mirroring the internal MCP tool's own routing path, which
404'd against the live account. Found the real path empirically (see git
history for `scripts/check_overrides_endpoint.py`, since removed once it
had served its purpose) by trying several plausible alternatives.
`get_listing_date_overrides` (GET) is now confirmed working, response
shape pulled directly from the live account. `update_listing_date_overrides`
(POST) uses the same now-confirmed base path, but this environment can't
reach `api.pricelabs.co` to test a real POST, and a write isn't something
to guess-and-check with real pricing data. **Before trusting this daily:
run without `--confirm` first (the default; sanity-check the printed
plan), then test with `--confirm --listing-id <one listing>` on a single
low-stakes date and verify the result via PriceLabs' own dashboard or
`get_listing_date_overrides` before ever pushing a full batch.**

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
hardcoded into the pacing/signal/bump logic; they're all cell references
(`$AA$2` etc.) into the threshold block `excel_report.py` writes onto the
Daily Pacing sheet itself, editable there without touching any formula.
`LISTINGS` isn't used by the data-pull or Excel stages (Report Builder
already blends both listings), but will be needed by the push phase,
which pushes overrides per listing.
