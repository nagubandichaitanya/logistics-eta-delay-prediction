
import random
from datetime import timedelta

import pandas as pd

from src.logistics_eta.config import DEFAULT_CONFIG


EVENT_TYPES = [
    "PICKUP",
    "DEPARTED",
    "ARRIVED",
    "IN_TRANSIT",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "EXCEPTION",
    "CUSTOMS_HOLD"
]


def generate_tracking_events(
    shipment_data,
    master_data,
    config=None
):
    if config is None:
        config = DEFAULT_CONFIG

    config.validate()

    rng = random.Random(config.seed + 2)

    shipments = shipment_data["shipments"]
    shipment_legs = shipment_data["shipment_legs"]
    routes = master_data["routes"]

    route_lookup = routes.set_index("route_id").to_dict("index")

    events = []

    # Group legs by shipment
    legs_by_shipment = {}

    for leg in shipment_legs.to_dict("records"):
        shipment_id = leg["shipment_id"]

        if shipment_id not in legs_by_shipment:
            legs_by_shipment[shipment_id] = []

        legs_by_shipment[shipment_id].append(leg)

    for shipment in shipments.to_dict("records"):

        shipment_id = shipment["shipment_id"]

        legs = sorted(
            legs_by_shipment[shipment_id],
            key=lambda x: x["leg_sequence"]
        )

        shipment_events = []

        # Event 1: Pickup
        shipment_events.append({
            "event_type": "PICKUP",
            "leg_id": legs[0]["leg_id"],
            "facility_id": shipment["origin_facility_id"],
            "event_at": legs[0]["actual_departure_at"]
        })

        for index, leg in enumerate(legs):

            route = route_lookup[leg["route_id"]]

            origin = route["origin_facility_id"]
            destination = route["destination_facility_id"]

            departure = leg["actual_departure_at"]
            arrival = leg["actual_arrival_at"]

            # Event: Shipment departed from facility
            shipment_events.append({
                "event_type": "DEPARTED",
                "leg_id": leg["leg_id"],
                "facility_id": origin,
                "event_at": departure
            })

            is_last_leg = index == len(legs) - 1

            if pd.notna(arrival):

                # Final delivery event
                if is_last_leg:
                    midpoint = departure + (
                        arrival - departure
                    ) / 2

                    shipment_events.append({
                        "event_type": "OUT_FOR_DELIVERY",
                        "leg_id": leg["leg_id"],
                        "facility_id": destination,
                        "event_at": midpoint
                    })

                    shipment_events.append({
                        "event_type": "DELIVERED",
                        "leg_id": leg["leg_id"],
                        "facility_id": destination,
                        "event_at": arrival
                    })

                else:
                    shipment_events.append({
                        "event_type": "ARRIVED",
                        "leg_id": leg["leg_id"],
                        "facility_id": destination,
                        "event_at": arrival
                    })

            else:
                # Shipment is still moving on its final leg
                transit_time = departure + timedelta(
                    minutes=rng.randint(30, 180)
                )

                shipment_events.append({
                    "event_type": "IN_TRANSIT",
                    "leg_id": leg["leg_id"],
                    "facility_id": origin,
                    "event_at": transit_time
                })

        # Add occasional operational exception events
        if rng.random() < 0.05:
            selected_leg = rng.choice(legs)

            exception_time = (
                selected_leg["actual_departure_at"]
                + timedelta(minutes=rng.randint(10, 120))
            )

            if pd.notna(selected_leg["actual_arrival_at"]):
                exception_time = min(
                    exception_time,
                    selected_leg["actual_arrival_at"]
                )

            shipment_events.append({
                "event_type": rng.choice(
                    ["EXCEPTION", "CUSTOMS_HOLD"]
                ),
                "leg_id": selected_leg["leg_id"],
                "facility_id": route_lookup[
                    selected_leg["route_id"]
                ]["origin_facility_id"],
                "event_at": exception_time
            })

        # Sort by actual event time
        shipment_events.sort(
            key=lambda x: x["event_at"]
        )

        for event in shipment_events:

            sequence = len([
                e for e in events
                if e["shipment_id"] == shipment_id
            ]) + 1

            event_id = (
                f"EVT-{shipment_id}-{sequence:06d}"
            )

            # Delayed scan ingestion: 0 to 24 hours
            ingestion_delay = timedelta(
                minutes=rng.randint(0, 1440)
            )

            ingested_at = (
                event["event_at"] + ingestion_delay
            )

            source_key = f"SRC-{event_id}"

            event_record = {
                "event_id": event_id,
                "shipment_id": shipment_id,
                "leg_id": event["leg_id"],
                "facility_id": event["facility_id"],
                "event_type": event["event_type"],
                "event_at": event["event_at"],
                "ingested_at": ingested_at,
                "source_event_key": source_key,
                "is_duplicate": False
            }

            events.append(event_record)

            # Approximately 1% duplicate tracking events
            if rng.random() < 0.01:

                duplicate = event_record.copy()

                duplicate_sequence = (
                    len([
                        e for e in events
                        if e["shipment_id"] == shipment_id
                    ]) + 1
                )

                duplicate["event_id"] = (
                    f"EVT-{shipment_id}-"
                    f"{duplicate_sequence:06d}"
                )

                duplicate["is_duplicate"] = True

                # Same source key identifies the duplicate
                duplicate["ingested_at"] = (
                    ingested_at + timedelta(
                        minutes=rng.randint(1, 60)
                    )
                )

                events.append(duplicate)

    return pd.DataFrame(events)


if __name__ == "__main__":
    from src.logistics_eta.master_data import (
        generate_all_master_data
    )

    from src.logistics_eta.shipment_data import (
        generate_shipments
    )

    master_data = generate_all_master_data()

    shipment_data = generate_shipments(
        master_data
    )

    tracking_events = generate_tracking_events(
        shipment_data,
        master_data
    )

    print("\nTRACKING EVENTS")
    print(tracking_events.head(10))

    print("\nTotal events:", len(tracking_events))

    print("\nEvent type distribution:")
    print(
        tracking_events["event_type"].value_counts()
    )

    print(
        "\nDuplicate events:",
        tracking_events["is_duplicate"].sum()
    )

    print(
        "\nDelayed ingestion events:",
        (
            tracking_events["ingested_at"]
            > tracking_events["event_at"]
        ).sum()
    )
