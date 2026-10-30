
from pathlib import Path

import pandas as pd

from src.logistics_eta.scenario_validation import filter_known_events


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

SNAPSHOT_HOURS = [0, 12, 24]


def load_data():
    tables = [
        "shipment",
        "shipment_leg",
        "tracking_event",
        "route",
        "service_level",
        "facility_queue",
        "weather_event",
    ]

    data = {}

    for table in tables:
        data[table] = pd.read_csv(RAW_DIR / f"{table}.csv")

    return data


def convert_timestamps(data):
    timestamp_columns = {
        "shipment": [
            "created_at",
            "planned_pickup_at",
            "promised_delivery_at",
            "actual_delivery_at",
        ],
        "shipment_leg": [
            "planned_departure_at",
            "planned_arrival_at",
            "actual_departure_at",
            "actual_arrival_at",
        ],
        "tracking_event": ["event_at", "ingested_at"],
        "facility_queue": ["observed_at", "valid_from", "valid_to"],
        "weather_event": ["starts_at", "ends_at"],
    }

    for table, columns in timestamp_columns.items():
        for column in columns:
            data[table][column] = pd.to_datetime(
                data[table][column],
                format="mixed",
                utc=True,
                errors="coerce",
            )

    return data


def generate_snapshots(data):
    shipments = data["shipment"]
    legs = data["shipment_leg"]
    events = data["tracking_event"]
    routes = data["route"]
    services = data["service_level"]
    queues = data["facility_queue"]
    weather = data["weather_event"]

    # Lookup dictionaries
    route_distance = routes.set_index("route_id")[
        "distance_km"
    ].to_dict()

    route_facilities = routes.set_index("route_id")[
        ["origin_facility_id", "destination_facility_id"]
    ].to_dict("index")

    service_names = services.set_index("service_level_id")[
        "service_name"
    ].to_dict()

    service_grace = services.set_index("service_level_id")[
        "late_grace_minutes"
    ].to_dict()

    # Store generated feature and label records
    feature_records = []
    label_records = []

    # Process every shipment
    for _, shipment in shipments.iterrows():

        # Step 1: Get shipment details
        shipment_id = shipment["shipment_id"]
        pickup_at = shipment["planned_pickup_at"]
        actual_delivery = shipment["actual_delivery_at"]

        # Step 2: Get shipment legs
        shipment_legs = legs[
            legs["shipment_id"] == shipment_id
        ].copy().sort_values("leg_sequence")

        total_legs = len(shipment_legs)

        # Step 3: Identify all facilities on the shipment route
        route_facility_ids = set()

        for route_id in shipment_legs["route_id"]:
            route_info = route_facilities.get(route_id)

            if route_info:
                route_facility_ids.add(
                    route_info["origin_facility_id"]
                )
                route_facility_ids.add(
                    route_info["destination_facility_id"]
                )

        # Step 4: Identify carriers assigned to the shipment
        carrier_ids = (
            shipment_legs["carrier_id"]
            .dropna()
            .unique()
            .tolist()
        )

        # Step 5: Calculate total shipment distance
        total_distance = sum(
            route_distance.get(route_id, 0)
            for route_id in shipment_legs["route_id"]
        )

        # Step 6: Generate snapshots at 0, 12 and 24 hours
        for hours in SNAPSHOT_HOURS:

            prediction_at = pickup_at + pd.Timedelta(hours=hours)

            # Do not predict for shipments already delivered
            if (
                pd.notna(actual_delivery)
                and actual_delivery <= prediction_at
            ):
                continue

            # Step 7: Filter events known at prediction time
            known_events = filter_known_events(
                events[
                    events["shipment_id"] == shipment_id
                ],
                prediction_at
            )

            known_events = known_events.sort_values(
                ["event_at", "ingested_at"]
            )

            event_count = len(known_events)

            # Step 8: Identify the latest tracking event
            if event_count > 0:

                last_event = known_events.iloc[-1]

                last_event_type = last_event["event_type"]
                last_event_at = last_event["event_at"]
                current_facility = last_event["facility_id"]

                minutes_since_last_event = (
                    prediction_at - last_event_at
                ).total_seconds() / 60

                if pd.isna(current_facility):
                    current_facility = shipment["origin_facility_id"]

            else:
                last_event_type = "NO_EVENT"
                current_facility = shipment["origin_facility_id"]
                minutes_since_last_event = None

            # Step 9: Calculate completed legs using ARRIVED events
            completed_leg_ids = set(
                known_events.loc[
                    known_events["event_type"] == "ARRIVED",
                    "leg_id",
                ].dropna()
            )

            completed_legs = shipment_legs[
                shipment_legs["leg_id"].isin(completed_leg_ids)
            ]

            completed_distance = sum(
                route_distance.get(route_id, 0)
                for route_id in completed_legs["route_id"]
            )

            remaining_distance = max(
                0,
                total_distance - completed_distance,
            )

            # Step 10: Get the latest valid facility queue observation
            known_queues = queues[
                (queues["facility_id"] == current_facility)
                & (queues["observed_at"] <= prediction_at)
                & (queues["valid_from"] <= prediction_at)
                & (queues["valid_to"] > prediction_at)
            ].copy().sort_values("observed_at")

            if len(known_queues) > 0:

                latest_queue = known_queues.iloc[-1]

                queue_length = latest_queue["queue_length"]
                estimated_wait = latest_queue["estimated_wait_minutes"]
                capacity_utilization = latest_queue[
                    "capacity_utilization"
                ]

            else:
                queue_length = None
                estimated_wait = None
                capacity_utilization = None

            # Step 11: Identify active weather events on planned route facilities
            active_weather = weather[
                weather["facility_id"].isin(route_facility_ids)
                & (weather["starts_at"] <= prediction_at)
                & (weather["ends_at"] > prediction_at)
            ]

            weather_count = len(active_weather)

            if weather_count > 0:
                max_weather_factor = active_weather[
                    "delay_factor"
                ].max()
            else:
                max_weather_factor = 1.0

            # Step 12: Calculate shipment timing features
            shipment_age = (
                prediction_at - shipment["created_at"]
            ).total_seconds() / 60

            promised_remaining = (
                shipment["promised_delivery_at"] - prediction_at
            ).total_seconds() / 60

            # Step 13: Save model features
            feature_records.append({
                "shipment_id": shipment_id,
                "snapshot_hours": hours,
                "prediction_at": prediction_at,
                "service_level": service_names.get(
                    shipment["service_level_id"]
                ),
                "priority": shipment["priority"],
                "weight_kg": shipment["weight_kg"],
                "shipment_age_minutes": shipment_age,
                "promised_remaining_minutes": promised_remaining,
                "carrier_id": carrier_ids[0] if carrier_ids else None,
                "carrier_count": len(carrier_ids),
                "total_distance_km": total_distance,
                "total_legs": total_legs,
                "completed_legs": len(completed_legs),
                "remaining_distance_km": remaining_distance,
                "tracking_event_count": event_count,
                "last_event_type": last_event_type,
                "minutes_since_last_event": minutes_since_last_event,
                "current_facility_id": current_facility,
                "queue_length": queue_length,
                "estimated_wait_minutes": estimated_wait,
                "capacity_utilization": capacity_utilization,
                "active_weather_count": weather_count,
                "max_weather_delay_factor": max_weather_factor,
            })

            # Step 14: Generate ground-truth labels separately
            is_delivered = pd.notna(actual_delivery)

            if is_delivered:

                remaining_minutes = (
                    actual_delivery - prediction_at
                ).total_seconds() / 60

                sla_deadline = (
                    shipment["promised_delivery_at"]
                    + pd.Timedelta(
                        minutes=service_grace[
                            shipment["service_level_id"]
                        ]
                    )
                )

                is_sla_late = actual_delivery > sla_deadline

            else:
                remaining_minutes = None
                is_sla_late = None

            label_records.append({
                "shipment_id": shipment_id,
                "snapshot_hours": hours,
                "prediction_at": prediction_at,
                "label_available": is_delivered,
                "actual_delivery_at": actual_delivery,
                "remaining_delivery_minutes": remaining_minutes,
                "is_sla_late": is_sla_late,
            })

    return (
        pd.DataFrame(feature_records),
        pd.DataFrame(label_records),
    )


def main():
    print("Loading source datasets...")

    data = load_data()
    data = convert_timestamps(data)

    print("Generating multi-snapshot features...")

    features, labels = generate_snapshots(data)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    features.to_csv(
        PROCESSED_DIR / "eta_features_multi_snapshot.csv",
        index=False,
    )

    labels.to_csv(
        PROCESSED_DIR / "ground_truth_multi_snapshot.csv",
        index=False,
    )

    print("\nMULTI-SNAPSHOT FEATURE ENGINEERING COMPLETED")
    print("--------------------------------------------")

    print("Total feature records:", len(features))

    print("\nRecords by snapshot:")
    print(
        features["snapshot_hours"].value_counts().sort_index()
    )

    print("\nTracking events by snapshot:")
    print(
        features.groupby("snapshot_hours")[
            "tracking_event_count"
        ].sum()
    )

    print("\nDelivered labels by snapshot:")
    print(
        labels.groupby("snapshot_hours")["label_available"].sum()
    )

    print("\nFiles saved successfully.")


if __name__ == "__main__":
    main()
