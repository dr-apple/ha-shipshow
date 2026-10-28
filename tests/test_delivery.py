"""Tests for the ShipShow delivery stop and arrival helpers."""

from custom_components.shipshow.delivery import stops_field, tracking_arrival


def test_stops_field_integer() -> None:
    assert stops_field({"deliverystopsremaining": 4}) == (True, 4)


def test_stops_field_zero_is_a_value() -> None:
    assert stops_field({"deliverystopsremaining": 0}) == (True, 0)


def test_stops_field_null_is_authoritative() -> None:
    assert stops_field({"deliverystopsremaining": None}) == (True, None)


def test_stops_field_missing_falls_back() -> None:
    assert stops_field({"last_status": "transit"}) == (False, None)


def test_stops_field_ignores_booleans() -> None:
    assert stops_field({"deliverystopsremaining": True}) == (True, None)


def test_arrival_window() -> None:
    arrival = tracking_arrival(
        {"earliestdeliverytime": "11:15:00", "scheduleddeliverytime": "13:30:00"}
    )
    assert arrival["text"] == "11:15–13:30"
    assert arrival["von"] == "11:15"
    assert arrival["bis"] == "13:30"
    assert arrival["geschaetzt"] is None


def test_arrival_single_time() -> None:
    arrival = tracking_arrival({"scheduleddeliverytime": "17:00:00"})
    assert arrival["text"] == "17:00"
    assert arrival["von"] is None


def test_arrival_estimate_wins_over_window() -> None:
    arrival = tracking_arrival(
        {
            "earliestdeliverytime": "11:15:00",
            "scheduleddeliverytime": "13:30:00",
            "derivedeta": "2026-10-28T10:45:00.000Z",
        }
    )
    assert arrival["text"].startswith("ca. ")
    assert arrival["geschaetzt"] is not None


def test_arrival_without_data() -> None:
    assert tracking_arrival({})["text"] is None
    assert tracking_arrival(None)["text"] is None


def test_arrival_ignores_invalid_estimate() -> None:
    arrival = tracking_arrival({"derivedeta": "kaputt", "scheduleddeliverytime": "12:00:00"})
    assert arrival["text"] == "12:00"
