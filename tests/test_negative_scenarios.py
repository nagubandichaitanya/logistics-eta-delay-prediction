
import pandas as pd
import pytest

from src.logistics_eta.scenario_validation import (
    filter_known_events,
    validate_route_sequence,
    validate_shipment_lifecycle,
)


def test_late_arriving_event_is_excluded():
    prediction_at = pd.Timestamp("2026-01-01 12:00:00", tz="UTC")

    events = pd.DataFrame([
        {
            "event_id": "EVT-1",
            "event_type": "ARRIVED",
            "event_at": "2026-01-01 10:00:00",
            "ingested_at": "2026-01-01 13:00:00",
            "is_duplicate": False,
        }
    ])

    result = filter_known_events(events, prediction_at)

    assert len(result) == 0


def test_impossible_route_order_is_rejected():
    routes = pd.DataFrame([
        {
            "route_id": "R1",
            "origin_facility_id": "F1",
            "destination_facility_id": "F2",
        },
        {
            "route_id": "R2",
            "origin_facility_id": "F3",
            "destination_facility_id": "F4",
        },
    ])

    legs = pd.DataFrame([
        {
            "shipment_id": "SHP-1",
            "leg_id": "LEG-1",
            "leg_sequence": 1,
            "route_id": "R1",
        },
        {
            "shipment_id": "SHP-1",
            "leg_id": "LEG-2",
            "leg_sequence": 2,
            "route_id": "R2",
        },
    ])

    with pytest.raises(ValueError, match="disconnected route"):
        validate_route_sequence(legs, routes)


def test_future_event_is_excluded():
    prediction_at = pd.Timestamp("2026-01-01 12:00:00", tz="UTC")

    events = pd.DataFrame([
        {
            "event_id": "EVT-2",
            "event_type": "ARRIVED",
            "event_at": "2026-01-01 14:00:00",
            "ingested_at": "2026-01-01 14:30:00",
            "is_duplicate": False,
        }
    ])

    result = filter_known_events(events, prediction_at)

    assert len(result) == 0


def test_delivered_shipment_marked_in_transit_is_rejected():
    shipments = pd.DataFrame([
        {
            "shipment_id": "SHP-1",
            "current_status": "IN_TRANSIT",
            "actual_delivery_at": None,
        }
    ])

    events = pd.DataFrame([
        {
            "shipment_id": "SHP-1",
            "event_type": "DELIVERED",
        }
    ])

    with pytest.raises(ValueError, match="DELIVERED event"):
        validate_shipment_lifecycle(shipments, events)