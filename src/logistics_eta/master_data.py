
import random
import pandas as pd

from src.logistics_eta.config import DEFAULT_CONFIG


def generate_carriers(rng):
    carrier_names = [
        "FastTrack Logistics",
        "BlueDart Express",
        "Global Freight",
        "Swift Cargo",
        "Prime Logistics",
        "SkyRoute Transport",
        "Reliable Movers",
        "ExpressWay Cargo",
        "Metro Logistics",
        "National Freight"
    ]

    records = []

    for i, name in enumerate(carrier_names, start=1):
        records.append({
            "carrier_id": f"CAR-{i:03d}",
            "carrier_name": name,
            "carrier_type": rng.choice(
                ["ROAD", "AIR", "RAIL", "OCEAN", "MULTIMODAL"]
            ),
            "active": True
        })

    return pd.DataFrame(records)


def generate_facilities(config, rng):
    locations = [
        ("Hyderabad", "Telangana"),
        ("Bengaluru", "Karnataka"),
        ("Chennai", "Tamil Nadu"),
        ("Mumbai", "Maharashtra"),
        ("Delhi", "Delhi"),
        ("Pune", "Maharashtra"),
        ("Kolkata", "West Bengal"),
        ("Ahmedabad", "Gujarat"),
        ("Jaipur", "Rajasthan"),
        ("Kochi", "Kerala"),
        ("Vijayawada", "Andhra Pradesh"),
        ("Visakhapatnam", "Andhra Pradesh")
    ]

    records = []

    facility_types = [
        "ORIGIN",
        "HUB",
        "WAREHOUSE",
        "PORT",
        "DESTINATION"
    ]

    for i in range(1, config.num_facilities + 1):
        city, state = rng.choice(locations)

        records.append({
            "facility_id": f"FAC-{i:03d}",
            "facility_name": f"Logistics Hub {i:03d}",
            "facility_type": rng.choice(facility_types),
            "city": city,
            "state": state,
            "country": "India",
            "timezone": "Asia/Kolkata",
            "capacity_per_hour": rng.randint(20, 200)
        })

    return pd.DataFrame(records)



def generate_routes(facilities, rng):
    records = []
    facility_ids = facilities["facility_id"].tolist()

    # Create a connected cycle so every facility
    # connects to the next facility.
    for i in range(len(facility_ids)):
        origin = facility_ids[i]
        destination = facility_ids[(i + 1) % len(facility_ids)]

        records.append({
            "route_id": f"RTE-{i + 1:03d}",
            "origin_facility_id": origin,
            "destination_facility_id": destination,
            "distance_km": round(rng.uniform(50, 2500), 2),
            "transport_mode": rng.choice(
                ["ROAD", "AIR", "RAIL"]
            )
        })

    return pd.DataFrame(records)



def generate_service_levels():
    records = [
        {
            "service_level_id": "SVC-001",
            "service_name": "STANDARD",
            "target_hours": 120,
            "late_grace_minutes": 60,
            "active": True
        },
        {
            "service_level_id": "SVC-002",
            "service_name": "EXPRESS",
            "target_hours": 72,
            "late_grace_minutes": 30,
            "active": True
        },
        {
            "service_level_id": "SVC-003",
            "service_name": "SAME_DAY",
            "target_hours": 24,
            "late_grace_minutes": 15,
            "active": True
        }
    ]

    return pd.DataFrame(records)


def generate_all_master_data(config=None):
    if config is None:
        config = DEFAULT_CONFIG

    config.validate()

    rng = random.Random(config.seed)

    carriers = generate_carriers(rng)
    facilities = generate_facilities(config, rng)
    routes = generate_routes(facilities, rng)
    service_levels = generate_service_levels()

    return {
        "carriers": carriers,
        "facilities": facilities,
        "routes": routes,
        "service_levels": service_levels
    }


if __name__ == "__main__":
    master_data = generate_all_master_data()

    for name, dataframe in master_data.items():
        print(f"\n{name.upper()}")
        print(dataframe.head())
        print("Total records:", len(dataframe))
        print("Columns:", dataframe.columns.tolist())
