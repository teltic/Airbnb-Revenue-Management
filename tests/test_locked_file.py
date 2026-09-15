import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from daily_price_analysis import config as cfg
from daily_price_analysis import main as main_module


def test_locked_output_file_gives_friendly_message_not_traceback(tmp_path, monkeypatch, capsys):
    listings_yaml = tmp_path / "listings.yaml"
    listings_yaml.write_text(
        """
listings:
  - name: Prop A
    tab_name: Prop A
    short_suffix: A
    pms: testpms
    listing_id: id-a
"""
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "holidays.yaml").write_text("{}")
    monkeypatch.setattr(cfg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(main_module.cfg, "get_api_key", lambda: "fake-key")

    fake_client = MagicMock()
    fake_client.get_reservations.return_value = []
    fake_client.get_listing_prices.return_value = [
        {"date": dt.date.today().isoformat(), "price": 200, "min_stay": 1, "booking_status": ""}
    ]
    fake_client.get_neighborhood_data.return_value = {}
    fake_client.get_overrides.return_value = []
    monkeypatch.setattr(main_module, "PriceLabsClient", lambda api_key: fake_client)

    with patch("daily_price_analysis.main.new_workbook") as mock_new_wb:
        fake_wb = MagicMock()
        fake_wb.save.side_effect = PermissionError("Permission denied")
        mock_new_wb.return_value = fake_wb

        with pytest.raises(SystemExit) as exc_info:
            main_module.run(tmp_path / "out.xlsx", days=1, bookings_csv=None, listings_config=listings_yaml)

    assert "open in Excel" in str(exc_info.value)
