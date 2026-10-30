
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def load_source_data():
    """Load the source CSV datasets."""

    files = [
        "shipment",
        "shipment_leg",
        "tracking_event",
        "route",
        "carrier",
        "service_level",
        "facility_queue",
        "weather_event",
    ]

    data = {}

    for name in files:
        data[name] = pd.read_csv(RAW_DIR / f"{name}.csv")

    return data


def convert_timestamps(data):
    """Convert timestamp columns into UTC datetime values."""

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
        "tracking_event": [
            "event_at",
            "ingested_at",
        ],
        "facility_queue": [
            "observed_at",
            "valid_from",
            "valid_to",
        ],
        "weather_event": [
            "starts_at",
            "ends_at",
        ],
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


def generate_eta_features(data):
    """
    Generate one historical ETA prediction snapshot per shipment.

    Snapshot time = planned pickup time.

    Only information available by prediction time is used.
    Ground-truth labels are generated separately.
    """

    shipments = data["shipment"]
    legs = data["shipment_leg"]
    events = data["tracking_event"]
    routes = data["route"]
    queues = data["facility_queue"]
    weather = data["weather_event"]
    services = data["service_level"]

    # Lookup dictionaries
    route_distance = routes.set_index("route_id")[
        "distance_km"
    ].to_dict()

    service_names = services.set_index("service_level_id")[
        "service_name"
    ].to_dict()

    service_grace = services.set_index("service_level_id")[
        "late_grace_minutes"
    ].to_dict()

    route_facilities = routes.set_index("route_id")[
        ["origin_facility_id", "destination_facility_id"]
    ].to_dict("index")

    feature_records = []
    label_records = []

    for _, shipment in shipments.iterrows():

        shipment_id = shipment["shipment_id"]

        # Historical prediction timestamp
        prediction_at = shipment["planned_pickup_at"]

        if pd.isna(prediction_at):
            raise ValueError(
                f"Missing planned pickup time: {shipment_id}"
            )

        # Shipment legs
        shipment_legs = legs[
            legs["shipment_id"] == shipment_id
        ].copy()

        shipment_legs = shipment_legs.sort_values(
            "leg_sequence"
        )

        total_distance = sum(
            route_distance.get(route_id, 0)
            for route_id in shipment_legs["route_id"]
        )

        total_legs = len(shipment_legs)

        # Carrier identity
        carrier_ids = sorted(
            shipment_legs["carrier_id"].dropna().unique().tolist()
        )

        # Tracking events known at prediction time
        known_events = events[
            (events["shipment_id"] == shipment_id)
            & (events["is_duplicate"] == False)
            & (events["event_at"] <= prediction_at)
            & (events["ingested_at"] <= prediction_at)
        ].copy()

        known_events = known_events.sort_values("event_at")

        event_count = len(known_events)

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

        # Completed legs based only on known ARRIVED events
        completed_leg_ids = set(
            known_events.loc[
                known_events["event_type"] == "ARRIVED",
                "leg_id"
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
            total_distance - completed_distance
        )

        # Historical queue information at current facility
        known_queues = queues[
            (queues["facility_id"] == current_facility)
            & (queues["observed_at"] <= prediction_at)
            & (queues["valid_from"] <= prediction_at)
            & (queues["valid_to"] > prediction_at)
        ].copy()

        known_queues = known_queues.sort_values("observed_at")

        if not known_queues.empty:
            latest_queue = known_queues.iloc[-1]

            queue_length = latest_queue["queue_length"]
            estimated_wait = latest_queue["estimated_wait_minutes"]
            capacity_utilization = latest_queue["capacity_utilization"]

        else:
            queue_length = None
            estimated_wait = None
            capacity_utilization = None

        # Facilities along the planned shipment route
        route_facilities_set = set()

        for route_id in shipment_legs["route_id"]:
            facility_info = route_facilities.get(route_id)

            if facility_info:
                route_facilities_set.add(
                    facility_info["origin_facility_id"]
                )
                route_facilities_set.add(
                    facility_info["destination_facility_id"]
                )

        # Weather disruptions active at prediction time
        active_weather = weather[
            weather["facility_id"].isin(route_facilities_set)
            & (weather["starts_at"] <= prediction_at)
            & (weather["ends_at"] > prediction_at)
        ]

        active_weather_count = len(active_weather)

        if active_weather_count > 0:
            max_weather_delay_factor = active_weather[
                "delay_factor"
            ].max()
        else:
            max_weather_delay_factor = 1.0

        # Shipment age at prediction time
        shipment_age_minutes = (
            prediction_at - shipment["created_at"]
        ).total_seconds() / 60

        # Feature record: do not include actual delivery or final status
        feature_records.append({

            "shipment_id": shipment_id,
            "prediction_at": prediction_at,

            "service_level": service_names.get(
                shipment["service_level_id"]
            ),

            "priority": shipment["priority"],
            "weight_kg": shipment["weight_kg"],

            "shipment_age_minutes": shipment_age_minutes,

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

            "active_weather_count": active_weather_count,
            "max_weather_delay_factor": max_weather_delay_factor,
        })

        # Ground-truth labels are stored separately
        actual_delivery = shipment["actual_delivery_at"]

        is_delivered = pd.notna(actual_delivery)

        if is_delivered:
            if actual_delivery < prediction_at:
                raise ValueError(
                    f"Delivery before prediction time: {shipment_id}"
                )

            remaining_delivery_minutes = (
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
            remaining_delivery_minutes = None
            is_sla_late = None

        label_records.append({

            "shipment_id": shipment_id,
            "prediction_at": prediction_at,

            "is_delivered": is_delivered,
            "actual_delivery_at": actual_delivery,

            "remaining_delivery_minutes":
                remaining_delivery_minutes,

            "is_sla_late": is_sla_late,
        })

    features = pd.DataFrame(feature_records)
    labels = pd.DataFrame(label_records)

    return features, labels


def run_feature_engineering():

    print("Loading source datasets...")

    data = load_source_data()
    data = convert_timestamps(data)

    print("Generating historical ETA features...")

    features, labels = generate_eta_features(data)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    features.to_csv(
        PROCESSED_DIR / "eta_features.csv",
        index=False
    )

    labels.to_csv(
        PROCESSED_DIR / "ground_truth.csv",
        index=False
    )

    print("\nFEATURE ENGINEERING COMPLETED")

    print("Feature records:", len(features))
    print("Feature columns:", len(features.columns))

    print(
        "Delivered labels:",
        labels["is_delivered"].sum()
    )

    print(
        "Undelivered labels:",
        (~labels["is_delivered"]).sum()
    )

    print(
        "SLA-late delivered shipments:",
        (labels["is_sla_late"] == True).sum()
    )

    print("\nFeature preview:")
    print(features.head().to_string(index=False))


if __name__ == "__main__":
    run_feature_engineering()
