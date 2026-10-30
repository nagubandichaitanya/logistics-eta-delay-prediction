
import random
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.logistics_eta.config import DEFAULT_CONFIG


# Approximate transport speeds in kilometres per hour
TRANSPORT_SPEEDS = {
    "ROAD": 55,
    "AIR": 650,
    "RAIL": 70,
    "OCEAN": 35
}


def generate_shipments(master_data, config=None):
    if config is None:
        config = DEFAULT_CONFIG

    config.validate()
    rng = random.Random(config.seed + 1)

    carriers = master_data["carriers"]
    facilities = master_data["facilities"]
    routes = master_data["routes"]
    service_levels = master_data["service_levels"]

    shipments = []
    shipment_legs = []

    # Use a fixed date to make the dataset reproducible
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    route_records = routes.to_dict("records")
    facility_ids = set(facilities["facility_id"])
    carrier_ids = carriers["carrier_id"].tolist()

    for i in range(1, config.num_shipments + 1):

        shipment_id = f"SHP-2026-{i:06d}"

        # Select a connected route path containing 1 to 4 legs
        start_index = rng.randrange(len(route_records))
        number_of_legs = rng.randint(1, 4)

        selected_routes = []

        for j in range(number_of_legs):
            route_index = (start_index + j) % len(route_records)
            selected_routes.append(route_records[route_index])

        # Verify route continuity
        for j in range(len(selected_routes) - 1):
            if (
                selected_routes[j]["destination_facility_id"]
                != selected_routes[j + 1]["origin_facility_id"]
            ):
                raise ValueError("Disconnected shipment route detected.")

        origin = selected_routes[0]["origin_facility_id"]
        destination = selected_routes[-1]["destination_facility_id"]

        service = service_levels.iloc[
            rng.randrange(len(service_levels))
        ]

        carrier_id = rng.choice(carrier_ids)

        planned_pickup = base_time + timedelta(
            days=rng.randint(0, 270),
            hours=rng.randint(0, 23)
        )

        created_at = planned_pickup - timedelta(
            hours=rng.randint(1, 24)
        )

        promised_delivery = planned_pickup + timedelta(
            hours=float(service["target_hours"])
        )

        # Approximately 85% delivered and 15% in transit
        is_delivered = rng.random() < 0.85

        shipment_status = (
            "DELIVERED" if is_delivered else "IN_TRANSIT"
        )

        shipment_leg_records = []
        planned_departure = planned_pickup
        previous_actual_arrival = None

        for leg_number, route in enumerate(selected_routes, start=1):

            leg_id = f"LEG-{shipment_id}-{leg_number:02d}"

            mode = route["transport_mode"]
            speed = TRANSPORT_SPEEDS[mode]

            travel_hours = (
                float(route["distance_km"]) / speed
            )

            # Add handling time at each facility
            travel_hours += rng.uniform(1, 3)

            planned_arrival = planned_departure + timedelta(
                hours=travel_hours
            )

            if previous_actual_arrival is None:
                actual_departure = planned_departure + timedelta(
                    hours=rng.uniform(0, 4)
                )
            else:
                actual_departure = max(
                    planned_departure,
                    previous_actual_arrival + timedelta(
                        hours=rng.uniform(1, 4)
                    )
                )

            # The final leg remains in transit for active shipments
            is_last_leg = leg_number == number_of_legs

            if is_delivered or not is_last_leg:
                actual_arrival = actual_departure + timedelta(
                    hours=travel_hours * rng.uniform(0.85, 1.8)
                )

                leg_status = "COMPLETED"
                previous_actual_arrival = actual_arrival

            else:
                actual_arrival = None
                leg_status = "IN_PROGRESS"

            leg_record = {
                "leg_id": leg_id,
                "shipment_id": shipment_id,
                "leg_sequence": leg_number,
                "route_id": route["route_id"],
                "carrier_id": carrier_id,
                "planned_departure_at": planned_departure,
                "planned_arrival_at": planned_arrival,
                "actual_departure_at": actual_departure,
                "actual_arrival_at": actual_arrival,
                "leg_status": leg_status
            }

            shipment_leg_records.append(leg_record)

            # Next leg starts after the previous planned arrival
            planned_departure = planned_arrival + timedelta(
                hours=rng.uniform(1, 4)
            )

        if is_delivered:
            actual_delivery = shipment_leg_records[-1][
                "actual_arrival_at"
            ]
        else:
            actual_delivery = None

        shipment_record = {
            "shipment_id": shipment_id,
            "service_level_id": service["service_level_id"],
            "origin_facility_id": origin,
            "destination_facility_id": destination,
            "created_at": created_at,
            "planned_pickup_at": planned_pickup,
            "promised_delivery_at": promised_delivery,
            "actual_delivery_at": actual_delivery,
            "current_status": shipment_status,
            "priority": rng.choice(
                ["STANDARD", "HIGH", "CRITICAL"]
            ),
            "weight_kg": round(rng.uniform(0.5, 1000), 3)
        }

        if origin not in facility_ids or destination not in facility_ids:
            raise ValueError("Unknown facility in shipment.")

        shipments.append(shipment_record)
        shipment_legs.extend(shipment_leg_records)

    return {
        "shipments": pd.DataFrame(shipments),
        "shipment_legs": pd.DataFrame(shipment_legs)
    }


if __name__ == "__main__":
    from src.logistics_eta.master_data import generate_all_master_data

    master_data = generate_all_master_data()
    shipment_data = generate_shipments(master_data)

    for name, dataframe in shipment_data.items():
        print(f"\n{name.upper()}")
        print(dataframe.head())
        print("Total records:", len(dataframe))
        print("Unique IDs:", dataframe.iloc[:, 0].nunique())
