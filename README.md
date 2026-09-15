# Airbnb-Revenue-Management

Generates the **Daily Low & High Price Analysis** workbook: a per-property
Excel tool for catching mispriced dates, tracking manual Airbnb promotions,
and mirroring active PriceLabs overrides. Pulls live data from PriceLabs'
API on every run; safe to rerun repeatedly (e.g. weekly).

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
  file in that same folder automatically.
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
  most recent earlier-dated file already in DIR (this is what
  `run_daily.bat` uses). Overrides `--output`.
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
whatever history the API returned. LY/2LY ADR and This-Month aggregates
for that property may just be incomplete, which is expected for a young
listing.

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
   data -- it logs a warning and proceeds (LY/2LY ADR and This-Month
   aggregates for that property may be incomplete). A `--bookings-csv`
   export is still used automatically to backfill history if you provide
   one and the API result looks thin.

4. **"This Month" Max/Floor pools every year of that calendar month.**
   e.g. a row in September 2026 is compared against *every* September in
   the available booking history, not just September 2026 -- otherwise a
   single month rarely has 3+ same-category nights to compute a floor
   from. This is a reasonable reading of the original spec but wasn't
   explicitly confirmed; flagged clearly in the "How This Works" tab.

5. **Blended ADR, not per-night.** LY/2LY ADR and the promo-range price
   lookups all come from stay-level or range-level data, not true
   per-night rates -- a multi-night reservation's average rate is applied
   to every night in that stay. By design, matching the original spec.

6. **Holiday/Event dates never get a Flag**, and comp-set methodology can
   differ silently between properties (see the Compset Overview tab) --
   both deliberate, both explained in the "How This Works" tab.

7. **A comp-set split into multiple bedroom-count segments uses the
   largest one for percentiles.** Some listings' comp-set data comes back
   as several sub-groups (one per bedroom count) instead of one blended
   group -- caught on the first live run, where a 1-listing sub-group was
   picked arbitrarily and made every percentile column identical. The
   script now picks the sub-group with the most listings for the actual
   Market Percentile numbers, and the Compset Overview tab's Notes column
   says when this happened and what the combined listing count across all
   segments is (which may double-count a listing that appears in more than
   one segment).

## Project layout

```
run_daily.bat               # double-click to generate today's workbook
setup_daily_task.bat        # run once to schedule run_daily.bat daily
config/listings.yaml        # properties to process (name, PMS, listing ID)
config/holidays.yaml        # hand-maintained holiday/event tags
src/daily_price_analysis/
  pricelabs_client.py        # REST API wrapper
  calendar.py, market.py,    # response parsers
  overrides.py, bookings.py
  promo.py                   # Promo Tracker date-range/price-range expansion
  compute.py                 # row-building + flag/threshold logic
  workbook_build.py          # openpyxl workbook construction
  workbook_state.py          # read-back of Notes + Promo tabs for reruns
  dated_output.py            # daily-snapshot filename/carry-forward logic
  main.py                    # CLI entrypoint
tests/                       # unit tests (no network required)
```

Run tests with `python -m pytest tests/`.
