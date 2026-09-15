# Airbnb-Revenue-Management

**Booking Quality Log** -- one Excel log of every confirmed booking (both
properties combined), flagging upsell/discount-worthy calendar gaps,
below-target pricing, and other booking-quality signals. Pulls live data
from PriceLabs' API; safe to rerun repeatedly. Only writes a new file on a
day at least one brand-new confirmed booking shows up; otherwise that day
is skipped, and a same-day rerun is safe too.

This repo used to also hold a second, unrelated tool (Daily Low & High
Price Analysis -- per-property mispricing flags, promo tracking, and an
overrides mirror). That's been split out into its own repo,
[teltic/Airbnb-Promotion-Price-Range-Tool](https://github.com/teltic/Airbnb-Promotion-Price-Range-Tool),
to keep the two separate.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # fill in PRICELABS_API_KEY
```

Get your API key from the PriceLabs dashboard: Account Settings > API.

Edit `config/listings.yaml` to add/remove properties (PMS name + listing
ID for each).

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
same-date-last-year ADR where available, comp-set market occupancy from the
same calendar dates last year shown one value per night of the stay (e.g.
"20%, 65%" for a 2-night stay, not averaged, so a weak night doesn't get
smoothed away by a strong one), a demand tier from comp-set occupancy, a
Gap Before/After signal ("Upsell candidate" on a 1-night gap,
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

**Manual note columns never get erased.** Comp Check (Airbnb), Pacing
Push %, LOS Discount, Final PL Check, and Notes/Verdict are hand-typed,
never computed (LY occ. used to be manual too, but is now automated -- see
above). A hidden **Reservation ID** column (PriceLabs'
own channel confirmation code, e.g. an Airbnb code like `HMT5EBPQ54`) keys
each row so that whenever a new file is written, any note you typed on a
booking that's still in view -- including one that's since been cancelled
-- is carried forward from the most recent prior file automatically. This
lookup is done by each column's header text at read time (not a fixed
column position), so it also survives a future column being added or a
manual column being renamed.

## Project layout

```
run_daily_bql.bat           # double-click to check for new bookings / generate today's log
setup_daily_task_bql.bat    # run once to schedule run_daily_bql.bat daily
run_bql.py                  # manual / command-line entrypoint
config/listings.yaml        # properties to process (name, PMS, listing ID)
src/booking_quality_log/
  pricelabs_client.py        # REST API wrapper
  config.py                  # listings.yaml / .env loading
  market.py                  # neighborhood/market-data response parser
  reservations.py            # confirmed-reservation fetch/parse
  compute.py                 # gap/target-ADR/demand-tier/BW-median/STLY row-building logic
  workbook_build.py          # openpyxl workbook construction (Read Me + Booking Quality Log tabs)
  workbook_state.py          # read-back of Reservation IDs + manual notes for reruns and the skip check
  dated_output.py            # daily-snapshot filename/most-recent-prior-file lookup
  main.py                    # CLI entrypoint, including the new-booking skip check
tests/                       # unit tests (no network required)
```

`pricelabs_client.py`, `config.py`, and `market.py` used to be shared with
the pricing tool via a single `daily_price_analysis` package in this same
repo; each tool now carries its own copy since splitting into separate
repos. Keep that in mind if you're fixing a bug in one -- e.g. the PriceLabs
API endpoint paths in this tool's `pricelabs_client.py` -- it won't
automatically apply to the pricing tool's copy in its own repo, and vice
versa.

Run tests with `python -m pytest tests/`.
