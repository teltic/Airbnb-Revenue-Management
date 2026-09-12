"""Editable configuration: listings, thresholds, and reference tables.

Threshold values and the median-booking-window table are the ones a user is
expected to tune over time (see spec). They are consumed as plain data by
data_pull.py / the Excel formula generator, never hardcoded into the logic.
"""

import os

from dotenv import load_dotenv

# Loads a .env file (if present) in the current working directory into
# os.environ, so PRICELABS_API_KEY can just live in a local .env file
# instead of requiring a terminal/setx step. Does nothing if no .env exists
# or the variable is already set some other way.
load_dotenv()

# --- Listings (PMS: smartbnb / Hospitable for both) -----------------------

LISTINGS = [
    {
        "listing_id": "dec5d2ed-4400-4350-8df3-af76b5d3d09c",
        "pms": "smartbnb",
        "name": "Mesquite Vacation Rental",
    },
    {
        "listing_id": "0e251a6a-3ea4-4d32-878a-cd734591c925",
        "pms": "smartbnb",
        "name": "Game Room (5BR label, actually 4BR)",
    },
]

# --- API -------------------------------------------------------------------

PRICELABS_API_BASE_URL = os.environ.get(
    "PRICELABS_API_BASE_URL", "https://api.pricelabs.co/v1"
)
PRICELABS_API_KEY_ENV_VAR = "PRICELABS_API_KEY"

# --- Date range for the daily pull -----------------------------------------

FORECAST_DAYS = 365

# --- Report Builder source --------------------------------------------------
# Confirmed reachable via a plain Customer API key (2026-09-12, see
# scripts/check_report_builder_access.py). This template already returns
# Occupancy/Market Occupancy/LY/STLY/Pickup 3-7-14-30-60d pre-computed and
# blended across both listings -- looked up by name (not a hardcoded
# template_id) since that's stable even if the account's template list
# changes.

REPORT_BUILDER_TEMPLATE_NAME = "Master Sheet - TB"

PICKUP_WINDOWS_DAYS = [3, 7, 14, 30, 60]

# --- Thresholds (spec section "Threshold values") ---------------------------

THRESHOLDS = {
    "pace_threshold": 5,
    "pickup_3d_threshold": 1.5,
    "pickup_7d_threshold": 3,
    "pickup_14d_threshold": 5,
    "pickup_30d_threshold": 10,
    "pickup_60d_threshold": 14,
    "weekday_ly_cut_pct": 25,
    "weekend_ly_cut_pct": 40,
    "low_ly_override_pace": 20,
    "high_ly_raise_ease_threshold_pct": 90,
    "high_ly_raise_ease_ratio_bar": 1.5,
    "far_out_hold_ly_threshold_pct": 85,
    "far_out_hold_booking_window_multiple": 2,
    "far_out_hold_max_behind_pace": 10,
}

# --- Median booking window by month (spec: re-paste periodically) -----------
# 1 = January ... 12 = December

MEDIAN_BOOKING_WINDOW_BY_MONTH = {
    1: 42,
    2: 40,
    3: 45,
    4: 51,
    5: 43,
    6: 33,
    7: 21,
    8: 15,
    9: 21,
    10: 37,
    11: 53,
    12: 27,
}

WEEKEND_DAYS = {"Fri", "Sat"}  # per spec: weekend = Fri-Sat, weekday = Sun-Thu
