"""Regression test: workbook tabs must be grouped by type (all property
tabs, then all Promo tabs, then all Overrides tabs), not interleaved
per-listing -- a real bug caught by inspecting the first live-run output.
"""

import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock

from daily_price_analysis import config as cfg
from daily_price_analysis import main as main_module


def _fake_calendar_rows(date_from: str, date_to: str) -> list[dict]:
    start = dt.date.fromisoformat(date_from)
    end = dt.date.fromisoformat(date_to)
    rows = []
    d = start
    while d < end:
        rows.append({"date": d.isoformat(), "price": 200, "min_stay": 1, "booking_status": ""})
        d += dt.timedelta(days=1)
    return rows


def test_tab_order_groups_by_type(tmp_path, monkeypatch):
    listings_yaml = tmp_path / "listings.yaml"
    listings_yaml.write_text(
        """
listings:
  - name: Prop A
    tab_name: Prop A
    short_suffix: A
    pms: testpms
    listing_id: id-a
  - name: Prop B
    tab_name: Prop B
    short_suffix: B
    pms: testpms
    listing_id: id-b
"""
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "holidays.yaml").write_text("{}")
    monkeypatch.setattr(cfg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(main_module.cfg, "get_api_key", lambda: "fake-key")

    old_date = (dt.date.today() - dt.timedelta(days=730)).isoformat()
    old_checkout = (dt.date.today() - dt.timedelta(days=729)).isoformat()

    fake_client = MagicMock()
    fake_client.get_reservations.return_value = [
        {
            "listing_name": "x",
            "check_in": old_date,
            "check_out": old_checkout,
            "booking_status": "booked",
            "rental_revenue": "200",
            "no_of_days": 1,
        }
    ]
    fake_client.get_listing_prices.side_effect = lambda listing_id, pms, date_from, date_to: _fake_calendar_rows(
        date_from, date_to
    )
    fake_client.get_neighborhood_data.return_value = {}
    fake_client.get_overrides.return_value = []
    monkeypatch.setattr(main_module, "PriceLabsClient", lambda api_key: fake_client)

    output_path = tmp_path / "output.xlsx"
    main_module.run(output_path, days=3, bookings_csv=None, listings_config=listings_yaml)

    import openpyxl

    wb = openpyxl.load_workbook(output_path)
    assert wb.sheetnames == [
        "Prop A",
        "Prop B",
        "Promo - A",
        "Promo - B",
        "Overrides - A",
        "Overrides - B",
        "Compset Overview",
        "How This Works",
    ]
