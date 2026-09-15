# Airbnb-Revenue-Management

Two automated tools, both pulling live data from PriceLabs' API and both
safe to rerun repeatedly:

- **Daily Low & High Price Analysis** -- a per-property Excel tool for
  catching mispriced dates, tracking manual Airbnb promotions, and
  mirroring active PriceLabs overrides.
- **Booking Quality Log** -- one Excel log of every confirmed booking
  (both properties combined), flagging upsell/discount-worthy calendar
  gaps, below-target pricing, and other booking-quality signals. Only
  writes a new file on a day at least one brand-new confirmed booking
  shows up; otherwise that day is skipped, and a same-day rerun is safe
  too. See "Booking Quality Log" below.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # fill in PRICELABS_API_KEY
```

Get your API key from the PriceLabs dashboard: Account Settings > API.

Edit `config/listings.yaml` to add/remove properties (PMS name + listing
ID for each). `config/holidays.yaml` is a hand-maintained list of
holiday/event dates -- see "Known limitations" below for why this isn't
pulled from the API.

## Usage

### One-click / daily automated (Windows)

- **`run_daily.bat`** -- double-click to generate today's workbook. Writes
  a dated snapshot (`Daily Low & High Price Analysis - YYYY-MM-DD.xlsx`)
  into the folder set as `OUTPUT_DIR` at the top of that file, carrying
  Notes and the Promo Tracker tabs forward from the most recent earlier
  file in that same folder automatically (or from today's own file, if
  you've already generated it once today and typed into it -- a same-day
  rerun never discards those edits). If today's file is currently open in
  Excel, the run will stop with a plain "close it and try again" message
  instead of overwriting a locked file.
- **`setup_daily_task.bat`** -- run once to register a Windows Scheduled
  Task that runs `run_daily.bat` automatically every day (default 6:00 AM
  -- edit `RUN_TIME` at the top of the file, then rerun it, to change
  that). Safe to rerun any time to update the schedule.

### Manual / command line

```
python run.py
```

(Equivalent to `python -m daily_price_analysis.main`, but works out of the
box -- that form requires `src/` on your `PYTHONPATH`, which Python doesn't
set up automatically.)

Writes `output/Daily Low & High Price Analysis.xlsx` by default (always
overwriting that one file). Useful flags:

- `--output-dir DIR` -- write a dated snapshot into DIR instead of
  overwriting a single file, carrying Notes/Promo data forward from the
  most recent dated file already in DIR that's dated today or earlier
  (preferring today's own file if one already exists, so a same-day rerun
  doesn't discard edits) -- this is what `run_daily.bat` uses. Overrides
  `--output`.
- `--output PATH` -- write to (and read prior Notes/Promo from) one fixed
  file instead.
- `--days N` -- forward window length (default 365).
- `--bookings-csv PATH` -- manual reservations-history CSV to backfill
  history with when a property's API reservation pull looks thin (see
  below). Expected columns: Listing Name, Check-in Date, Check-out Date,
  Booked Date, Average Daily Rate, Rental Revenue, Total Revenue,
  Currency, Booking Source, Booking Status -- this is the format the
  PriceLabs dashboard's CSV export uses. One CSV can cover your whole
  portfolio (a multi-listing export) or just one property -- the script
  filters rows by the `name` in `config/listings.yaml` matched against the
  CSV's Listing Name column (whitespace/case-insensitive), so one property
  falling back never mixes another property's bookings into its numbers.
  If a property's name doesn't match anything in the CSV, the error
  message lists the exact Listing Name values the CSV actually contains so
  you can fix the mismatch.

Rerunning is non-destructive: before regenerating, the script reads a
prior output file (the same fixed file with `--output`, or the most recent
dated file in the folder with `--output-dir`) and preserves the **Note
Date / Note** columns on each property's main tab and the entire **Promo
Tracker** tabs (those are hand-maintained, never pulled from an API). The
**Active Overrides** tabs are always fully refreshed live -- if the API
can't be reached for that, the run fails loudly instead of silently
overwriting good override data with blanks.

If a property's reservation history looks unusually thin and no
`--bookings-csv` is given, the run does **not** stop (this matters for
unattended daily automation) -- it logs a warning and proceeds with
whatever history the API returned. The LY price lookup and that
property's own booking-window figure may just be incomplete, which is
expected for a young listing.

## Known limitations / assumptions worth knowing before you trust this

1. **PriceLabs API endpoints are now confirmed live.** The base URL, auth
   header, and all four endpoints actually used in a run (`listing_prices`,
   `neighborhood_data`, `overrides`, `reservation_data`) were verified
   against a real account on 2026-09-14 -- the first real run caught one
   wrong path (`overrides`, since fixed). `get_listings` is the one method
   nothing in the normal flow calls, so it remains unverified; if it ever
   404s, `PriceLabsAPIError` prints the failing URL and response body, and
   a wrong path is a one-line fix in the `ENDPOINTS` dict at the top of
   `pricelabs_client.py`.

2. **No holiday/event field exists anywhere in the PriceLabs API.** Checked
   the pricing calendar, market/neighborhood-data, and overrides endpoints
   against live data -- none of them expose the "Holiday/Event" tagging
   seen in the PriceLabs dashboard's calendar UI. That tagging appears to
   be UI-only. `config/holidays.yaml` is a hand-maintained substitute;
   keep it updated alongside PriceLabs' own calendar.

3. **Reservation-history truncation bug: confirmed not an issue on real
   runs so far, but can't be told apart from a young listing in general.**
   The original prototype hit a bug where a reservations API call with
   explicit date filters silently returned only ~18 recent rows instead of
   full history. Live testing across two real properties found one with
   full multi-year history (fine) and one ("Sauna Cold Plunge 5BR") with
   thin history via the API -- but a manually-exported CSV covering the
   same window was equally thin, confirming that property is just young,
   not hitting the bug. Since there's no reliable way to tell "young
   listing" apart from "API truncated it" from row count/date span alone,
   and this script needs to run unattended on a schedule,
   `bookings.fetch_reservations_verified` no longer hard-stops on thin
   data -- it logs a warning and proceeds (the LY price lookup and that
   property's own booking-window figure may be incomplete). A
   `--bookings-csv` export is still used automatically to backfill
   history if you provide one and the API result looks thin.

4. **Flag logic is occupancy-driven, not history-driven** (redesigned
   2026-09-15 -- an earlier version inferred "typical" price from this
   property's own past booked prices, which just launders forward
   whatever pricing mistakes already happened). See the "How This Works"
   tab for the full rule; in short, Flag only fires once a date is close
   enough to check-in that still being unbooked means something (that
   property's own median days-between-booking-and-check-in, or 45 days if
   there isn't history to compute that yet), then compares market
   occupancy against Market Percentile. A secondary check flags a >20%
   price swing vs. the same date last year regardless of that gate. Flag
   is now a plain computed value rather than a live Excel formula (unlike
   Market Percentile, which still is) -- see caveat 6.

5. **The Airbnb price-adjustment factor is a placeholder, not a validated
   number.** The Promo Tracker's "Current Price (Airbnb-adjusted)" column
   multiplies PriceLabs' Current Price by a flat 0.90 (config:
   `promo.AIRBNB_ADJUSTMENT_FACTOR`) to approximate Airbnb's own combined
   discount + PMS markup on top of the PriceLabs feed. That factor hasn't
   been validated against real side-by-side numbers yet -- treat the
   adjusted column as a rough comparison point until it has been.

6. **Blended, not per-night.** LY price and the promo-range price
   lookups all come from stay-level or range-level data, not true
   per-night rates -- a multi-night reservation's average rate is applied
   to every night in that stay. By design, matching the original spec.
   Also worth knowing: Flag no longer recalculates live if you hand-edit
   Current Price in Excel (Market Percentile still does) -- not expected
   to matter in normal use, since Current Price is pulled fresh from
   PriceLabs every run rather than something you'd hand-edit for real
   decisions.

7. **Holiday/Event dates never get a Flag**, and comp-set methodology can
   differ silently between properties (see the Compset Overview tab) --
   both deliberate, both explained in the "How This Works" tab.

8. **A comp-set split into multiple bedroom-count segments uses the
   largest one for percentiles.** Some listings' comp-set data comes back
   as several sub-groups (one per bedroom count) instead of one blended
   group -- caught on the first live run, where a 1-listing sub-group was
   picked arbitrarily and made every percentile column identical. The
   script now picks the sub-group with the most listings for the actual
   Market Percentile numbers, and the Compset Overview tab's Notes column
   says when this happened and what the combined listing count across all
   segments is (which may double-count a listing that appears in more than
   one segment).

## Booking Quality Log

One workbook, two tabs ("Read Me" + "Booking Quality Log"), covering both
properties combined -- one row per booking with check-in on or after
**2026-09-01** (a fixed cutoff, by explicit request -- not a rolling
"today onward" window, so it won't silently start showing fewer rows as
time passes; ask if you'd rather it rolled forward instead), sorted by
**Booked date, newest first** (not by check-in).

Each row carries: nights/stay pattern/1-night flag, booking-window vs. that
property's own median lead time, your ADR vs. the comp set's 75th-percentile
target (both properties are Premium tier), market P25/P90 for context,
same-date-last-year ADR where available, a demand tier from comp-set
occupancy, a Gap Before/After signal ("Upsell candidate" on a 1-night gap,
"LOS-discount candidate" on a 2-night gap, each noting how often the comp
set's occupancy suggests that gap fills on its own), and a **Status**
column (Confirmed / Cancelled) -- a booking that later gets cancelled stays
on the log, grayed out, instead of disappearing, so any note already typed
on it isn't lost and a cancelled booking is still there to learn from. Gap
Before/After don't apply to a cancelled booking (it no longer holds any
calendar space), so those show "n/a (cancelled)" instead of a number. Full
plain-language descriptions are in the workbook's own "Read Me" tab.

### Usage

- **`run_daily_bql.bat`** -- double-click to check PriceLabs for brand-new
  confirmed bookings and, if there are any, write today's dated workbook
  (`Booking Quality Log - YYYY-MM-DD.xlsx`) into the folder set as
  `OUTPUT_DIR` at the top of that file. If nothing new booked since the
  last file it wrote (even if that was several days ago), it skips
  writing anything and exits quietly -- that's expected, not a failure.
- **`setup_daily_task_bql.bat`** -- run once to register a Windows
  Scheduled Task that runs `run_daily_bql.bat` every day (default 7:00 AM
  -- edit `RUN_TIME` at the top of the file, then rerun it, to change
  that). Safe to rerun any time to update the schedule.
- Manual / command line: `python run_bql.py [--output-dir DIR] [--force]`.
  `--force` writes today's file even if nothing new booked (useful for
  testing, or to pick up a change you made by hand to the pulled data).

**What counts as "new":** only a brand-new confirmed booking appearing
since the last file was written triggers a new file -- a cancellation or a
guest's dates changing on an existing booking does not, by itself, trigger
one (ask if you'd rather those also triggered a refresh).

**Manual note columns never get erased.** Comp Check (Airbnb), LY occ.,
Pacing Push %, LOS Discount, Final PL Check, and Notes/Verdict are
hand-typed, never computed. A hidden **Reservation ID** column (PriceLabs'
own channel confirmation code, e.g. an Airbnb code like `HMT5EBPQ54`) keys
each row so that whenever a new file is written, any note you typed on a
booking that's still in view -- including one that's since been cancelled
-- is carried forward from the most recent prior file automatically. This
lookup is done by each column's header text at read time (not a fixed
column position), so it also survives a future column being added or a
manual column being renamed.

## Project layout

```
run_daily.bat               # double-click to generate today's Price Analysis workbook
setup_daily_task.bat        # run once to schedule run_daily.bat daily
run_daily_bql.bat           # double-click to check for new bookings / generate today's Booking Quality Log
setup_daily_task_bql.bat    # run once to schedule run_daily_bql.bat daily
config/listings.yaml        # properties to process (name, PMS, listing ID) -- shared by both tools
config/holidays.yaml        # hand-maintained holiday/event tags
src/daily_price_analysis/
  pricelabs_client.py        # REST API wrapper -- shared by both tools
  calendar.py, market.py,    # response parsers -- market.py shared by both tools
  overrides.py, bookings.py
  promo.py                   # Promo Tracker date-range/price-range expansion
  compute.py                 # row-building + occupancy-driven Flag logic
  workbook_build.py          # openpyxl workbook construction
  workbook_state.py          # read-back of Notes + Promo tabs for reruns
  dated_output.py            # daily-snapshot filename/carry-forward logic
  main.py                    # CLI entrypoint
src/booking_quality_log/
  reservations.py            # confirmed-reservation fetch/parse (own copy: needs different fields/window than bookings.py above)
  compute.py                 # gap/target-ADR/demand-tier/BW-median/STLY row-building logic
  workbook_build.py          # openpyxl workbook construction (Read Me + Booking Quality Log tabs)
  workbook_state.py          # read-back of Reservation IDs + manual notes for reruns and the skip check
  dated_output.py            # daily-snapshot filename/most-recent-prior-file lookup
  main.py                    # CLI entrypoint, including the new-booking skip check
tests/                       # unit tests (no network required)
```

Run tests with `python -m pytest tests/`.
