
import random
from datetime import datetime, timedelta, timezone, date, time

import pandas as pd

from src.logistics_eta.config import DEFAULT_CONFIG


BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def generate_weather_events(master_data, config=None):

    if config is None:
        config = DEFAULT_CONFIG

    rng = random.Random(config.seed + 3)

    facilities = master_data["facilities"].to_dict("records")

    weather_types = [
        "RAIN", "FLOOD", "SNOW", "WIND", "FOG", "HEAT"
    ]

    severity_levels = [
        "LOW", "MODERATE", "HIGH", "SEVERE"
    ]

    delay_factors = {
        "LOW": (1.05, 1.20),
        "MODERATE": (1.21, 1.50),
        "HIGH": (1.51, 1.90),
        "SEVERE": (1.91, 2.50)
    }

    records = []

    for i in range(1, config.num_disruption_windows + 1):

        facility = rng.choice(facilities)

        starts_at = BASE_TIME + timedelta(
            days=rng.randint(0, 270),
            hours=rng.randint(0, 23)
        )

        ends_at = starts_at + timedelta(
            hours=rng.randint(1, 48)
        )

        weather_type = rng.choice(weather_types)
        severity = rng.choice(severity_levels)

        minimum, maximum = delay_factors[severity]

        delay_factor = round(
            rng.uniform(minimum, maximum), 2
        )

        records.append({
            "weather_event_id": f"WTH-2026-{i:06d}",
            "facility_id": facility["facility_id"],
            "region": f'{facility["city"]}, {facility["state"]}',
            "weather_type": weather_type,
            "severity": severity,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "delay_factor": delay_factor
        })

    return pd.DataFrame(records)


def generate_facility_queues(master_data, config=None):

    if config is None:
        config = DEFAULT_CONFIG

    rng = random.Random(config.seed + 4)

    facilities = master_data["facilities"].to_dict("records")

    records = []

    for i in range(1, config.num_disruption_windows + 1):

        facility = rng.choice(facilities)

        observed_at = BASE_TIME + timedelta(
            days=rng.randint(0, 270),
            hours=rng.randint(0, 23)
        )

        valid_from = observed_at

        valid_to = valid_from + timedelta(
            hours=rng.randint(1, 6)
        )

        capacity = int(facility["capacity_per_hour"])

        queue_length = rng.randint(
            0, max(1, int(capacity * 1.5))
        )

        capacity_utilization = round(
            queue_length / capacity, 3
        )

        estimated_wait_minutes = round(
            capacity_utilization
            * 60
            * rng.uniform(0.5, 1.5)
        )

        records.append({
            "queue_id": f"QUE-2026-{i:06d}",
            "facility_id": facility["facility_id"],
            "observed_at": observed_at,
            "queue_length": queue_length,
            "estimated_wait_minutes": estimated_wait_minutes,
            "capacity_utilization": capacity_utilization,
            "valid_from": valid_from,
            "valid_to": valid_to
        })

    return pd.DataFrame(records)


def generate_facility_calendars(master_data):

    facilities = master_data["facilities"].to_dict("records")

    records = []

    for facility in facilities:

        for weekday in range(7):

            records.append({
                "facility_calendar_id": (
                    f'FCAL-{facility["facility_id"]}-{weekday}'
                ),
                "facility_id": facility["facility_id"],
                "weekday": weekday,
                "opens_at": time(6, 0),
                "closes_at": time(22, 0),
                "timezone": facility["timezone"],
                "valid_from": date(2026, 1, 1),
                "valid_to": None
            })

    return pd.DataFrame(records)


def generate_carrier_calendars(master_data):

    carriers = master_data["carriers"].to_dict("records")

    records = []

    for carrier in carriers:

        for weekday in range(7):

            records.append({
                "carrier_calendar_id": (
                    f'CCAL-{carrier["carrier_id"]}-{weekday}'
                ),
                "carrier_id": carrier["carrier_id"],
                "weekday": weekday,
                "opens_at": time(6, 0),
                "closes_at": time(22, 0),
                "timezone": "Asia/Kolkata",
                "valid_from": date(2026, 1, 1),
                "valid_to": None
            })

    return pd.DataFrame(records)


def generate_all_disruption_data(master_data, config=None):

    if config is None:
        config = DEFAULT_CONFIG

    config.validate()

    return {
        "weather_events": generate_weather_events(
            master_data, config
        ),
        "facility_queues": generate_facility_queues(
            master_data, config
        ),
        "facility_calendars": generate_facility_calendars(
            master_data
        ),
        "carrier_calendars": generate_carrier_calendars(
            master_data
        )
    }


if __name__ == "__main__":

    from src.logistics_eta.master_data import (
        generate_all_master_data
    )

    master_data = generate_all_master_data()

    disruption_data = generate_all_disruption_data(
        master_data
    )

    for name, dataframe in disruption_data.items():

        print(f"\n{name.upper()}")

        print("Rows:", len(dataframe))

        print(dataframe.head(3))

    weather = disruption_data["weather_events"]
    queues = disruption_data["facility_queues"]

    print("\nWEATHER VALIDATION")

    print(
        "Invalid weather windows:",
        (weather["starts_at"] >= weather["ends_at"]).sum()
    )

    print(
        "Invalid delay factors:",
        (weather["delay_factor"] < 1.0).sum()
    )

    print("\nFACILITY QUEUE VALIDATION")

    print(
        "Invalid queue windows:",
        (queues["valid_from"] >= queues["valid_to"]).sum()
    )

    print(
        "Invalid capacity utilization:",
        (
            (queues["capacity_utilization"] < 0)
            | (queues["capacity_utilization"] > 1.5)
        ).sum()
    )
