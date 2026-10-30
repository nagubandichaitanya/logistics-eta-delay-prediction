
from pathlib import Path
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# Project directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load environment variables from .env
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = __import__("os").getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing from the .env file")


# CSV filename and PostgreSQL table name
TABLE_FILES = {
    "carrier": "carrier.csv",
    "facility": "facility.csv",
    "service_level": "service_level.csv",
    "route": "route.csv",
    "shipment": "shipment.csv",
    "shipment_leg": "shipment_leg.csv",
    "tracking_event": "tracking_event.csv",
    "weather_event": "weather_event.csv",
    "facility_queue": "facility_queue.csv",
    "facility_calendar": "facility_calendar.csv",
    "carrier_calendar": "carrier_calendar.csv"
}


# Database date/time columns
TIME_COLUMNS = {"opens_at", "closes_at"}


def prepare_dataframe(file_path):
    """Read a CSV and convert its date/time values."""

    df = pd.read_csv(file_path)

    for column in df.columns:

        if column in TIME_COLUMNS:
            df[column] = pd.to_datetime(
                df[column], format="mixed"
            ).dt.time

        elif (
            column.endswith("_at")
            or column.endswith("_from")
            or column.endswith("_to")
        ):
            df[column] = pd.to_datetime(
                df[column],
                format="mixed",
                utc=True,
                errors="raise"
        )

    # Convert missing values to Python None
    df = df.astype(object).where(pd.notna(df), None)

    return df


def load_datasets():

    engine = create_engine(DATABASE_URL)

    raw_data_dir = PROJECT_ROOT / "data" / "raw"

    try:
        with engine.begin() as connection:

            print("Checking PostgreSQL tables...")

            # Prevent accidental duplicate loading
            for table_name in TABLE_FILES:

                result = connection.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                )

                row_count = result.scalar()

                if row_count > 0:
                    raise ValueError(
                        f"Table {table_name} is not empty. "
                        "Loading cancelled to prevent duplicates."
                    )

            print("All target tables are empty.")
            print("\nLoading CSV data...\n")

            # Insert in foreign-key dependency order
            for table_name, file_name in TABLE_FILES.items():

                file_path = raw_data_dir / file_name

                if not file_path.exists():
                    raise FileNotFoundError(
                        f"CSV file not found: {file_path}"
                    )

                df = prepare_dataframe(file_path)

                if df.empty:
                    print(f"{table_name}: 0 records")
                    continue

                columns = list(df.columns)

                column_names = ", ".join(
                    f'"{column}"' for column in columns
                )

                placeholders = ", ".join(
                    f":{column}" for column in columns
                )

                insert_query = text(
                    f'INSERT INTO "{table_name}" '
                    f'({column_names}) VALUES ({placeholders})'
                )

                records = df.to_dict(orient="records")

                connection.execute(insert_query, records)

                print(
                    f"{table_name}: {len(records)} records inserted"
                )

        print("\nDATABASE LOADING COMPLETED SUCCESSFULLY")

    finally:
        engine.dispose()


if __name__ == "__main__":
    load_datasets()
