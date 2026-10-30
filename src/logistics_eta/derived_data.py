
import pandas as pd


def generate_shipment_status_history(tracking_events):
    """
    Generate shipment status history from tracking events.

    event_at = when the event actually happened.
    ingested_at = when the system received the event.
    """

    status_mapping = {
        "PICKUP": "PICKED_UP",
        "DEPARTED": "IN_TRANSIT",
        "ARRIVED": "AT_FACILITY",
        "IN_TRANSIT": "IN_TRANSIT",
        "OUT_FOR_DELIVERY": "OUT_FOR_DELIVERY",
        "DELIVERED": "DELIVERED",
        "EXCEPTION": "EXCEPTION",
        "CUSTOMS_HOLD": "EXCEPTION"
    }

    events = tracking_events.copy()

    # Ignore duplicate tracking records
    events = events[events["is_duplicate"] == False].copy()

    # Convert event timestamps
    events["event_at"] = pd.to_datetime(
        events["event_at"], utc=True
    )

    events["ingested_at"] = pd.to_datetime(
        events["ingested_at"], utc=True
    )

    # Map tracking events to shipment statuses
    events["status"] = events["event_type"].map(status_mapping)

    # Remove events without a status mapping
    events = events.dropna(subset=["status"])

    # Sort by actual event occurrence time
    events = events.sort_values(
        ["shipment_id", "event_at", "ingested_at"]
    )

    history = []

    for _, event in events.iterrows():

        history.append({
            "status_history_id": f"STH-{len(history) + 1:08d}",
            "shipment_id": event["shipment_id"],
            "status": event["status"],
            "effective_at": event["event_at"],
            "source_event_id": event["event_id"],
            "recorded_at": event["ingested_at"]
        })

    return pd.DataFrame(history)

def generate_shipment_route_history(shipment_legs):
    """
    Generate route history from shipment legs.
    Each leg represents a route assignment.
    """

    legs = shipment_legs.copy()

    legs["planned_departure_at"] = pd.to_datetime(
        legs["planned_departure_at"], format="mixed", utc=True
    )

    legs["planned_arrival_at"] = pd.to_datetime(
        legs["planned_arrival_at"], format="mixed", utc=True
    )

    legs = legs.sort_values(
        ["shipment_id", "leg_sequence"]
    )

    history = []

    for _, leg in legs.iterrows():

        history.append({
            "route_history_id": f"RTH-{len(history) + 1:08d}",
            "shipment_id": leg["shipment_id"],
            "route_id": leg["route_id"],
            "effective_from": leg["planned_departure_at"],
            "effective_to": leg["planned_arrival_at"],
            "change_reason": "INITIAL_ROUTE_ASSIGNMENT"
        })

    return pd.DataFrame(history)
def generate_shipment_weather_exposure(shipment_legs, routes, weather_events):
    """
    Identify weather events overlapping a shipment leg
    at its origin or destination facility.

    Exposure indicates overlap, not proven causation.
    """

    legs = shipment_legs.copy()
    route_data = routes.copy()
    weather = weather_events.copy()

    # Convert timestamps
    for column in ["planned_departure_at", "planned_arrival_at"]:
        legs[column] = pd.to_datetime(
            legs[column], format="mixed", utc=True
        )

    for column in ["starts_at", "ends_at"]:
        weather[column] = pd.to_datetime(
            weather[column], format="mixed", utc=True
        )

    # Attach origin and destination facilities to each leg
    legs = legs.merge(
        route_data[
            ["route_id", "origin_facility_id", "destination_facility_id"]
        ],
        on="route_id",
        how="left"
    )

    exposure_records = []

    # Check weather at both ends of every shipment leg
    for _, leg in legs.iterrows():

        facilities = [
            leg["origin_facility_id"],
            leg["destination_facility_id"]
        ]

        matching_weather = weather[
            weather["facility_id"].isin(facilities)
        ]

        for _, event in matching_weather.iterrows():

            exposure_start = max(
                leg["planned_departure_at"],
                event["starts_at"]
            )

            exposure_end = min(
                leg["planned_arrival_at"],
                event["ends_at"]
            )

            if exposure_start < exposure_end:
                exposure_records.append({
                    "shipment_id": leg["shipment_id"],
                    "weather_event_id": event["weather_event_id"],
                    "exposed_from": exposure_start,
                    "exposed_to": exposure_end
                })

    result = pd.DataFrame(exposure_records)

    if result.empty:
        return pd.DataFrame(columns=[
            "exposure_id",
            "shipment_id",
            "weather_event_id",
            "exposed_from",
            "exposed_to"
        ])

    # Remove duplicate exposure windows
    result = result.drop_duplicates(
        subset=["shipment_id", "weather_event_id", "exposed_from"]
    ).reset_index(drop=True)

    result.insert(
        0,
        "exposure_id",
        [f"EXP-{i:08d}" for i in range(1, len(result) + 1)]
    )

    return result

def generate_delay_reasons(
    shipments,
    service_levels,
    weather_exposure,
    shipment_legs,
    routes,
    facility_queue,
    observation_cutoff
):
    """
    Generate SLA delay records using observed weather and
    facility queue evidence.

    Evidence indicates possible contributing factors,
    not confirmed causation.
    """

    shipments = shipments.copy()
    services = service_levels.copy()
    weather = weather_exposure.copy()
    legs = shipment_legs.copy()
    route_data = routes.copy()
    queues = facility_queue.copy()

    # Parse timestamps
    for column in ["promised_delivery_at", "actual_delivery_at"]:
        shipments[column] = pd.to_datetime(
            shipments[column], format="mixed", utc=True
        )

    for column in ["exposed_from", "exposed_to"]:
        weather[column] = pd.to_datetime(
            weather[column], format="mixed", utc=True
        )

    for column in ["planned_departure_at", "planned_arrival_at"]:
        legs[column] = pd.to_datetime(
            legs[column], format="mixed", utc=True
        )

    for column in ["valid_from", "valid_to"]:
        queues[column] = pd.to_datetime(
            queues[column], format="mixed", utc=True
        )

    cutoff = pd.to_datetime(observation_cutoff, utc=True)

    # Attach SLA grace periods
    shipments = shipments.merge(
        services[["service_level_id", "late_grace_minutes"]],
        on="service_level_id",
        how="left"
    )

    if shipments["late_grace_minutes"].isna().any():
        raise ValueError("Missing service-level grace period")

    shipments["evaluation_time"] = (
        shipments["actual_delivery_at"].fillna(cutoff)
    )

    shipments["sla_deadline"] = (
        shipments["promised_delivery_at"]
        + pd.to_timedelta(shipments["late_grace_minutes"], unit="m")
    )

    # Only shipments exceeding their SLA deadline are late
    late_shipments = shipments[
        shipments["evaluation_time"] > shipments["sla_deadline"]
    ]

    # Attach facility information to shipment legs
    legs = legs.merge(
        route_data[
            ["route_id", "origin_facility_id", "destination_facility_id"]
        ],
        on="route_id",
        how="left"
    )

    records = []

    for _, shipment in late_shipments.iterrows():

        shipment_id = shipment["shipment_id"]

        # Delay measured from promised delivery time
        delay_minutes = max(
            0,
            int(
                (shipment["evaluation_time"]
                 - shipment["promised_delivery_at"]).total_seconds() / 60
            )
        )

        evidence = []

        # 1. Weather evidence
        weather_matches = weather[
            weather["shipment_id"] == shipment_id
        ]

        if not weather_matches.empty:
            total_weather_overlap = sum(
                max(
                    0,
                    int(
                        (row["exposed_to"] - row["exposed_from"])
                        .total_seconds() / 60
                    )
                )
                for _, row in weather_matches.iterrows()
            )

            evidence.append({
                "reason_code": "WEATHER",
                "description": (
                    f"{len(weather_matches)} weather exposure window(s) "
                    f"overlapped planned shipment legs. "
                    f"Total overlap: {total_weather_overlap} minutes. "
                    "Potential contributing factor; causation not established."
                ),
                "evidence_minutes": total_weather_overlap
            })

        # 2. Facility queue evidence
        shipment_leg_rows = legs[
            legs["shipment_id"] == shipment_id
        ]

        queue_matches = []

        for _, leg in shipment_leg_rows.iterrows():

            relevant_facilities = [
                leg["origin_facility_id"],
                leg["destination_facility_id"]
            ]

            facility_queues = queues[
                queues["facility_id"].isin(relevant_facilities)
            ]

            for _, queue in facility_queues.iterrows():

                overlap_start = max(
                    leg["planned_departure_at"],
                    queue["valid_from"]
                )

                overlap_end = min(
                    leg["planned_arrival_at"],
                    queue["valid_to"]
                )

                if overlap_start < overlap_end:
                    queue_matches.append(queue)

        if queue_matches:
            max_wait = max(
                int(queue["estimated_wait_minutes"])
                for queue in queue_matches
            )

            total_queue_overlap = sum(
                max(
                    0,
                    int(
                        (min(leg["planned_arrival_at"], queue["valid_to"])
                         - max(leg["planned_departure_at"], queue["valid_from"]))
                        .total_seconds() / 60
                    )
                )
                for _, leg in shipment_leg_rows.iterrows()
                for _, queue in queues[
                    queues["facility_id"].isin([
                        leg["origin_facility_id"],
                        leg["destination_facility_id"]
                    ])
                ].iterrows()
                if max(leg["planned_departure_at"], queue["valid_from"])
                < min(leg["planned_arrival_at"], queue["valid_to"])
            )

            evidence.append({
                "reason_code": "FACILITY_QUEUE",
                "description": (
                    f"{len(queue_matches)} facility queue observation(s) "
                    f"overlapped planned shipment legs. "
                    f"Maximum estimated wait: {max_wait} minutes. "
                    "Potential contributing factor; causation not established."
                ),
                "evidence_minutes": total_queue_overlap
            })

        # 3. No supporting weather or queue evidence
        if not evidence:
            evidence.append({
                "reason_code": "OTHER",
                "description": (
                    "Shipment exceeded its SLA deadline, but no matching "
                    "weather exposure or facility queue evidence was found."
                ),
                "evidence_minutes": 0
            })

        # Mark the strongest recorded signal as primary.
        # This is evidence ranking, not causal attribution.
        primary_index = max(
            range(len(evidence)),
            key=lambda index: evidence[index]["evidence_minutes"]
        )

        for index, item in enumerate(evidence):
            records.append({
                "shipment_id": shipment_id,
                "reason_code": item["reason_code"],
                "reason_description": item["description"],
                "delay_minutes": delay_minutes,
                "observed_at": shipment["evaluation_time"],
                "is_primary": index == primary_index
            })

    result = pd.DataFrame(records)

    if result.empty:
        return pd.DataFrame(columns=[
            "delay_reason_id",
            "shipment_id",
            "reason_code",
            "reason_description",
            "delay_minutes",
            "observed_at",
            "is_primary"
        ])

    result.insert(
        0,
        "delay_reason_id",
        [f"DLY-2026-{i:06d}" for i in range(1, len(result) + 1)]
    )

    return result



if __name__ == "__main__":

    from pathlib import Path

    raw_dir = Path("data/raw")
    processed_dir = Path("data/processed")

    processed_dir.mkdir(parents=True, exist_ok=True)

    print("Loading raw datasets...")

    tracking_events = pd.read_csv(raw_dir / "tracking_event.csv")
    shipment_legs = pd.read_csv(raw_dir / "shipment_leg.csv")
    routes = pd.read_csv(raw_dir / "route.csv")
    weather_events = pd.read_csv(raw_dir / "weather_event.csv")
    shipments = pd.read_csv(raw_dir / "shipment.csv")
    service_levels = pd.read_csv(raw_dir / "service_level.csv")
    facility_queue = pd.read_csv(raw_dir / "facility_queue.csv")

    # Use the latest ingestion timestamp as the dataset observation cutoff.
    observation_cutoff = pd.to_datetime(
        tracking_events["ingested_at"],
        format="mixed",
        utc=True
    ).max()

    print("Observation cutoff:", observation_cutoff)

    # 1. Generate shipment status history.
    print("\nGenerating shipment status history...")

    status_history = generate_shipment_status_history(
        tracking_events
    )

    status_history.to_csv(
        processed_dir / "shipment_status_history.csv",
        index=False
    )

    print("Status history records:", len(status_history))

    # 2. Generate shipment route history.
    print("\nGenerating shipment route history...")

    route_history = generate_shipment_route_history(
        shipment_legs
    )

    route_history.to_csv(
        processed_dir / "shipment_route_history.csv",
        index=False
    )

    print("Route history records:", len(route_history))

    # 3. Generate shipment weather exposure.
    print("\nGenerating shipment weather exposure...")

    weather_exposure = generate_shipment_weather_exposure(
        shipment_legs,
        routes,
        weather_events
    )

    weather_exposure.to_csv(
        processed_dir / "shipment_weather_exposure.csv",
        index=False
    )

    print("Weather exposure records:", len(weather_exposure))

    # 4. Generate shipment delay reasons.
    print("\nGenerating shipment delay reasons...")

    delay_reasons = generate_delay_reasons(
        shipments,
        service_levels,
        weather_exposure,
        shipment_legs,
        routes,
        facility_queue,
        observation_cutoff
    )

    delay_reasons.to_csv(
        processed_dir / "delay_reason.csv",
        index=False
    )

    print("Delay reason records:", len(delay_reasons))

    print("\nALL FOUR DERIVED DATASETS GENERATED")
    print("-----------------------------------")

    for file_path in sorted(processed_dir.glob("*.csv")):
        print(f"{file_path.name}: {file_path.stat().st_size:,} bytes")