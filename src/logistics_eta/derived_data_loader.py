from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

TABLE_FILES = {
    "shipment_status_history":
        "data/processed/shipment_status_history.csv",

    "shipment_route_history":
        "data/processed/shipment_route_history.csv",

    "shipment_weather_exposure":
        "data/processed/shipment_weather_exposure.csv",

    "delay_reason":
        "data/processed/delay_reason.csv",
}


def prepare_dataframe(df):
    """Convert pandas values into PostgreSQL-compatible values."""

    df = df.astype(object).where(pd.notna(df), None)

    return df


def load_derived_datasets():

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is missing from .env")

    engine = create_engine(DATABASE_URL)

    try:
        with engine.begin() as connection:

            print("Checking derived PostgreSQL tables...")

            for table in TABLE_FILES:

                count = connection.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                ).scalar_one()

                if count > 0:
                    raise RuntimeError(
                        f"Table {table} is not empty. "
                        "Loading stopped to prevent duplicates."
                    )

            print("All derived tables are empty.")
            print("Loading derived datasets...")

            for table, relative_path in TABLE_FILES.items():

                file_path = PROJECT_ROOT / relative_path

                if not file_path.exists():
                    raise FileNotFoundError(file_path)

                df = pd.read_csv(file_path)
                df = prepare_dataframe(df)

                if df.empty:
                    print(f"{table}: 0 records")
                    continue

                columns = list(df.columns)

                column_names = ", ".join(
                    f'"{column}"' for column in columns
                )

                parameters = ", ".join(
                    f":{column}" for column in columns
                )

                query = text(
                    f'INSERT INTO "{table}" '
                    f"({column_names}) VALUES ({parameters})"
                )

                connection.execute(
                    query,
                    df.to_dict(orient="records")
                )

                print(
                    f"{table}: {len(df)} records inserted"
                )

        print("\nDERIVED DATA LOADING COMPLETED SUCCESSFULLY")

    finally:
        engine.dispose()


if __name__ == "__main__":
    load_derived_datasets()