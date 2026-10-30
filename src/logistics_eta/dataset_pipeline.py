
from pathlib import Path

import pandas as pd

from src.logistics_eta.config import DEFAULT_CONFIG
from src.logistics_eta.master_data import generate_all_master_data
from src.logistics_eta.shipment_data import generate_shipments
from src.logistics_eta.tracking_events import generate_tracking_events
from src.logistics_eta.disruption_data import generate_all_disruption_data


def check_unique(data, column, dataset_name):
    if data[column].isna().any():
        raise ValueError(f"{dataset_name}: {column} contains null values")

    if data[column].duplicated().any():
        raise ValueError(f"{dataset_name}: duplicate {column} values found")


def check_foreign_key(data, column, parent_data, parent_column, name):
    invalid = ~data[column].isin(parent_data[parent_column])

    if invalid.any():
        raise ValueError(
            f"{name}: {invalid.sum()} invalid foreign key values"
        )


def validate_datasets(datasets):

    # Primary key checks
    primary_keys = {
        "carrier": "carrier_id",
        "facility": "facility_id",
        "route": "route_id",
        "service_level": "service_level_id",
        "shipment": "shipment_id",
        "shipment_leg": "leg_id",
        "tracking_event": "event_id",
        "weather_event": "weather_event_id",
        "facility_queue": "queue_id",
        "facility_calendar": "facility_calendar_id",
        "carrier_calendar": "carrier_calendar_id"
    }

    for name, column in primary_keys.items():
        check_unique(datasets[name], column, name)
    
    # Shipment leg status validation
        # Shipment leg status validation
    allowed_leg_statuses = {
        "PLANNED", "IN_PROGRESS", "COMPLETED", "DISRUPTED", "CANCELLED"
    }

    invalid_leg_statuses = set(
        datasets["shipment_leg"]["leg_status"]
    ) - allowed_leg_statuses

    if invalid_leg_statuses:
        raise ValueError(
            f"Invalid shipment leg statuses: {invalid_leg_statuses}"
        )

    # Foreign key checks
    check_foreign_key(
        datasets["route"], "origin_facility_id",
        datasets["facility"], "facility_id", "route origin"
    )

    check_foreign_key(
        datasets["route"], "destination_facility_id",
        datasets["facility"], "facility_id", "route destination"
    )

    check_foreign_key(
        datasets["shipment"], "service_level_id",
        datasets["service_level"], "service_level_id", "shipment service level"
    )

    check_foreign_key(
        datasets["shipment"], "origin_facility_id",
        datasets["facility"], "facility_id", "shipment origin"
    )

    check_foreign_key(
        datasets["shipment"], "destination_facility_id",
        datasets["facility"], "facility_id", "shipment destination"
    )

    check_foreign_key(
        datasets["shipment_leg"], "shipment_id",
        datasets["shipment"], "shipment_id", "shipment leg"
    )

    check_foreign_key(
        datasets["shipment_leg"], "route_id",
        datasets["route"], "route_id", "shipment leg route"
    )

    check_foreign_key(
        datasets["shipment_leg"], "carrier_id",
        datasets["carrier"], "carrier_id", "shipment leg carrier"
    )

    check_foreign_key(
        datasets["tracking_event"], "shipment_id",
        datasets["shipment"], "shipment_id", "tracking event shipment"
    )

    check_foreign_key(
        datasets["tracking_event"], "leg_id",
        datasets["shipment_leg"], "leg_id", "tracking event leg"
    )

    check_foreign_key(
        datasets["tracking_event"], "facility_id",
        datasets["facility"], "facility_id", "tracking event facility"
    )

    check_foreign_key(
        datasets["weather_event"], "facility_id",
        datasets["facility"], "facility_id", "weather facility"
    )

    check_foreign_key(
        datasets["facility_queue"], "facility_id",
        datasets["facility"], "facility_id", "queue facility"
    )

    check_foreign_key(
        datasets["facility_calendar"], "facility_id",
        datasets["facility"], "facility_id", "calendar facility"
    )

    check_foreign_key(
        datasets["carrier_calendar"], "carrier_id",
        datasets["carrier"], "carrier_id", "calendar carrier"
    )

    # Tracking event timestamp validation
    events = datasets["tracking_event"]

    if (events["ingested_at"] < events["event_at"]).any():
        raise ValueError("Tracking event ingestion time is invalid")

    allowed_events = {
        "PICKUP", "DEPARTED", "ARRIVED", "IN_TRANSIT",
        "OUT_FOR_DELIVERY", "DELIVERED", "EXCEPTION",
        "CUSTOMS_HOLD"
    }

    if not set(events["event_type"]).issubset(allowed_events):
        raise ValueError("Invalid tracking event type")

    # Weather validation
    weather = datasets["weather_event"]

    if (weather["starts_at"] >= weather["ends_at"]).any():
        raise ValueError("Invalid weather time windows")

    if (weather["delay_factor"] < 1.0).any():
        raise ValueError("Weather delay factor cannot be below 1")

    # Queue validation
    queues = datasets["facility_queue"]

    if (queues["valid_from"] >= queues["valid_to"]).any():
        raise ValueError("Invalid facility queue time windows")

    if (queues["estimated_wait_minutes"] < 0).any():
        raise ValueError("Negative facility waiting time")

    if (
        (queues["capacity_utilization"] < 0)
        | (queues["capacity_utilization"] > 1.5)
    ).any():
        raise ValueError("Invalid facility capacity utilization")

    # Shipment lifecycle validation
    shipments = datasets["shipment"]

    delivered = shipments["current_status"] == "DELIVERED"

    if shipments.loc[delivered, "actual_delivery_at"].isna().any():
        raise ValueError("Delivered shipment has no actual delivery time")

    if shipments.loc[~delivered, "actual_delivery_at"].notna().any():
        raise ValueError("Undelivered shipment has an actual delivery time")

    # Every delivered shipment must have a delivery event
    delivered_ids = set(
        shipments.loc[delivered, "shipment_id"]
    )

    delivered_event_ids = set(
        events.loc[
            events["event_type"] == "DELIVERED",
            "shipment_id"
        ]
    )

    missing_delivery_events = delivered_ids - delivered_event_ids

    if missing_delivery_events:
        raise ValueError(
            f"{len(missing_delivery_events)} delivered shipments "
            "have no DELIVERED tracking event"
        )

    # Undelivered shipments must not have a delivery event
    undelivered_ids = set(
        shipments.loc[~delivered, "shipment_id"]
    )

    false_delivery_events = undelivered_ids & delivered_event_ids

    if false_delivery_events:
        raise ValueError(
            f"{len(false_delivery_events)} undelivered shipments "
            "have false DELIVERED events"
        )

    print("\nALL DATA VALIDATION CHECKS PASSED")


def build_datasets(config=None):

    if config is None:
        config = DEFAULT_CONFIG

    config.validate()
    config.create_directories()

    print("\nGenerating master data...")
    master = generate_all_master_data(config)

    print("Generating shipment data...")
    shipment = generate_shipments(master, config)

    print("Generating tracking events...")
    tracking = generate_tracking_events(
        shipment, master, config
    )

    print("Generating disruption data...")
    disruption = generate_all_disruption_data(master, config)

    datasets = {
        "carrier": master["carriers"],
        "facility": master["facilities"],
        "route": master["routes"],
        "service_level": master["service_levels"],
        "shipment": shipment["shipments"],
        "shipment_leg": shipment["shipment_legs"],
        "tracking_event": tracking,
        "weather_event": disruption["weather_events"],
        "facility_queue": disruption["facility_queues"],
        "facility_calendar": disruption["facility_calendars"],
        "carrier_calendar": disruption["carrier_calendars"]
    }

    return datasets


def export_datasets(datasets, config=None):

    if config is None:
        config = DEFAULT_CONFIG

    output_dir = config.raw_data_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\nExporting CSV files...")

    for name, dataframe in datasets.items():

        file_path = output_dir / f"{name}.csv"

        dataframe.to_csv(file_path, index=False)

        print(
            f"{name}.csv: {len(dataframe)} records"
        )

    print(f"\nCSV files saved to: {output_dir}")


if __name__ == "__main__":

    datasets = build_datasets()

    print("\nRunning validation...")
    validate_datasets(datasets)

    export_datasets(datasets)

    print("\nDATASET GENERATION COMPLETED")
