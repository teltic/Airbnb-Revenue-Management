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

```
python run.py
```

(Equivalent to `python -m daily_price_analysis.main`, but works out of the
box -- that form requires `src/` on your `PYTHONPATH`, which Python doesn't
set up automatically.)

Writes `output/Daily Low & High Price Analysis.xlsx` by default. Useful flags:

- `--output PATH` -- write somewhere else.
- `--days N` -- forward window length (default 365).
- `--bookings-csv PATH` -- manual reservations-history CSV to fall back to
  if the API's reservation pull looks truncated (see below). Expected
  columns: Listing Name, Check-in Date, Check-out Date, Booked Date,
  Average Daily Rate, Rental Revenue, Total Revenue, Currency, Booking
  Source, Booking Status -- this is the format the PriceLabs dashboard's
  CSV export uses.

Rerunning is non-destructive: before regenerating, the script reads the
existing output file (if present) and preserves the **Note Date / Note**
columns on each property's main tab and the entire **Promo Tracker** tabs
(those are hand-maintained, never pulled from an API). The **Active
Overrides** tabs are always fully refreshed live -- if the API can't be
reached for that, the run fails loudly instead of silently overwriting
good override data with blanks.

## Known limitations / assumptions worth knowing before you trust this

1. **PriceLabs API endpoint paths are unverified from this build
   environment.** The sandbox this was built in blocks all outbound
   network access to pricelabs.co, so `pricelabs_client.py`'s endpoint
   paths (base URL, exact routes, HTTP methods) come from PriceLabs' public
   API documentation structure rather than a live test against the
   directly-authenticated (API-key) endpoint. What *is* verified against
   real account data (captured 2026-09-12, via this account's already-connected
   PriceLabs MCP integration, which proxies the same backend over a
   different auth path) are the JSON field names the parsing code expects
   -- `price`, `ADR`, `booking_status`, `price_type`, `min_price`, etc. are
   real. **On the first run somewhere with real internet access, watch for
   404/405 errors** -- `PriceLabsAPIError` prints the failing URL and
   response body, and a wrong path is a one-line fix in the `ENDPOINTS`
   dict at the top of `pricelabs_client.py`.

2. **No holiday/event field exists anywhere in the PriceLabs API.** Checked
   the pricing calendar, market/neighborhood-data, and overrides endpoints
   against live data -- none of them expose the "Holiday/Event" tagging
   seen in the PriceLabs dashboard's calendar UI. That tagging appears to
   be UI-only. `config/holidays.yaml` is a hand-maintained substitute;
   keep it updated alongside PriceLabs' own calendar.

3. **Reservation-history truncation bug, re-tested but not fully cleared.**
   The original prototype hit a bug where a reservations API call with
   explicit date filters silently returned only ~18 recent rows instead of
   full history. Re-tested live against this account's reservation-data
   endpoint (via the MCP-proxied path) with an explicit ~2.5-year window
   and it returned full paginated history correctly. That's encouraging
   but was tested through a different auth path than the one this script
   actually uses -- `bookings.fetch_reservations_verified` still runs a
   sanity check on every run (does the earliest returned booking reach
   back far enough?) and refuses to proceed on suspiciously thin data,
   falling back to a manual CSV export if `--bookings-csv` is given, or
   failing loudly if not.

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

## Project layout

```
config/listings.yaml       # properties to process (name, PMS, listing ID)
config/holidays.yaml       # hand-maintained holiday/event tags
src/daily_price_analysis/
  pricelabs_client.py       # REST API wrapper
  calendar.py, market.py,   # response parsers
  overrides.py, bookings.py
  promo.py                  # Promo Tracker date-range/price-range expansion
  compute.py                # row-building + flag/threshold logic
  workbook_build.py          # openpyxl workbook construction
  workbook_state.py          # read-back of Notes + Promo tabs for reruns
  main.py                    # CLI entrypoint
tests/                      # unit tests for compute/promo/workbook_build (no network)
```

Run tests with `python -m pytest tests/`.
