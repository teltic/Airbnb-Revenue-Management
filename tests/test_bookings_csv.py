import datetime as dt

import pytest

from daily_price_analysis.bookings import load_reservations_csv

CSV_HEADER = (
    "Listing Name,Check-in Date,Check-out Date,Booked Date,"
    "Average Daily Rate,Rental Revenue,Total Revenue,Currency,"
    "Booking Source,Booking Status\n"
)


def _write_csv(tmp_path, rows: list[str]):
    path = tmp_path / "bookings.csv"
    path.write_text(CSV_HEADER + "\n".join(rows), encoding="utf-8")
    return str(path)


def test_filters_to_matching_listing_only(tmp_path):
    rows = [
        "Mesquite Vacation Rental,2024-02-15,2024-02-19,2024-02-13,320,1280,1400,USD,airbnb,booked",
        "Sauna  Cold Plunge  5 BR,2024-03-01,2024-03-03,2024-02-20,500,1000,1100,USD,airbnb,booked",
    ]
    path = _write_csv(tmp_path, rows)

    sauna_only = load_reservations_csv(path, listing_name="Sauna Cold Plunge 5BR")
    assert len(sauna_only) == 1
    assert sauna_only[0].check_in == dt.date(2024, 3, 1)

    mesquite_only = load_reservations_csv(path, listing_name="Mesquite Vacation Rental")
    assert len(mesquite_only) == 1
    assert mesquite_only[0].check_in == dt.date(2024, 2, 15)


def test_no_filter_returns_everything(tmp_path):
    rows = [
        "Mesquite Vacation Rental,2024-02-15,2024-02-19,2024-02-13,320,1280,1400,USD,airbnb,booked",
        "Sauna Cold Plunge 5BR,2024-03-01,2024-03-03,2024-02-20,500,1000,1100,USD,airbnb,booked",
    ]
    path = _write_csv(tmp_path, rows)
    assert len(load_reservations_csv(path)) == 2


def test_unmatched_listing_name_raises_with_helpful_message(tmp_path):
    rows = [
        "Mesquite Vacation Rental,2024-02-15,2024-02-19,2024-02-13,320,1280,1400,USD,airbnb,booked",
    ]
    path = _write_csv(tmp_path, rows)
    with pytest.raises(ValueError, match="Mesquite Vacation Rental"):
        load_reservations_csv(path, listing_name="Some Other Property")
