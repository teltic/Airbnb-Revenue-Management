import datetime as dt
from unittest.mock import MagicMock

from daily_price_analysis.bookings import fetch_reservations_verified


def test_thin_history_without_csv_warns_and_proceeds(caplog):
    """A young listing's genuinely-thin history must not block a run when
    no --bookings-csv fallback is configured -- this is what makes
    unattended daily automation possible.
    """
    recent_checkin = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    recent_checkout = (dt.date.today() - dt.timedelta(days=29)).isoformat()
    client = MagicMock()
    client.get_reservations.return_value = [
        {
            "listing_name": "Young Listing",
            "check_in": recent_checkin,
            "check_out": recent_checkout,
            "booking_status": "booked",
            "rental_revenue": "200",
            "no_of_days": 1,
        }
    ]

    with caplog.at_level("WARNING"):
        reservations = fetch_reservations_verified(
            client, pms="testpms", listing_id="id-1", listing_name="Young Listing"
        )

    assert len(reservations) == 1
    assert any("looks thin" in r.message for r in caplog.records)


def test_complete_history_logs_info_not_warning(caplog):
    old_checkin = (dt.date.today() - dt.timedelta(days=700)).isoformat()
    old_checkout = (dt.date.today() - dt.timedelta(days=699)).isoformat()
    client = MagicMock()
    client.get_reservations.return_value = [
        {
            "listing_name": "Established Listing",
            "check_in": old_checkin,
            "check_out": old_checkout,
            "booking_status": "booked",
            "rental_revenue": "200",
            "no_of_days": 1,
        }
    ]

    with caplog.at_level("WARNING"):
        reservations = fetch_reservations_verified(
            client, pms="testpms", listing_id="id-2", listing_name="Established Listing"
        )

    assert len(reservations) == 1
    assert not any(r.levelname == "WARNING" for r in caplog.records)
