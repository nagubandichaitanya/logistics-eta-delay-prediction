
from pathlib import Path
from datetime import datetime, timezone
import os

import joblib
import numpy as np
import pandas as pd

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text


# --------------------------------------------------
# PROJECT PATHS AND CONFIGURATION
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_DIR = PROJECT_ROOT / "models"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

load_dotenv(PROJECT_ROOT / ".env")

MODEL_VERSION = "rf-20261030-v1"

app = FastAPI(
    title="Logistics ETA Prediction API",
    description=(
        "Predict shipment delivery time and "
        "detect potential delivery delays."
    ),
    version="1.0.0",
)


# --------------------------------------------------
# LOAD TRAINED MODELS
# --------------------------------------------------

try:
    eta_model = joblib.load(
        MODEL_DIR / "eta_regression_model.joblib"
    )

    delay_model = joblib.load(
        MODEL_DIR / "delay_classification_model.joblib"
    )

    model_load_error = None

except Exception as error:
    eta_model = None
    delay_model = None
    model_load_error = str(error)


# --------------------------------------------------
# LOAD PRECOMPUTED FEATURE DATA
# --------------------------------------------------

FEATURE_FILE = (
    PROCESSED_DIR / "eta_features_multi_snapshot.csv"
)

try:
    features = pd.read_csv(FEATURE_FILE)

    features["prediction_at"] = pd.to_datetime(
        features["prediction_at"],
        utc=True,
    )

    features["prediction_hour"] = (
        features["prediction_at"].dt.hour
    )

    features["prediction_day_of_week"] = (
        features["prediction_at"].dt.dayofweek
    )

    features["prediction_month"] = (
        features["prediction_at"].dt.month
    )

    feature_load_error = None

except Exception as error:
    features = pd.DataFrame()
    feature_load_error = str(error)


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

def get_database_engine():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise HTTPException(
            status_code=503,
            detail="DATABASE_URL is not configured.",
        )

    return create_engine(
        database_url,
        pool_pre_ping=True,
    )


# --------------------------------------------------
# REQUEST SCHEMA
# --------------------------------------------------

class ShipmentRequest(BaseModel):
    shipment_id: str = Field(
        pattern=r"^SHP-\d{4}-\d{6}$",
        examples=["SHP-2026-000001"],
    )


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health_check():

    return {
        "status": "healthy",
        "eta_model_loaded": eta_model is not None,
        "delay_model_loaded": delay_model is not None,
        "feature_data_loaded": not features.empty,
        "model_version": MODEL_VERSION,
    }


# --------------------------------------------------
# GET SHIPMENT FEATURES
# --------------------------------------------------

def get_shipment_features(shipment_id):

    if features.empty:
        raise HTTPException(
            status_code=503,
            detail="Feature dataset is unavailable.",
        )

    shipment_rows = features[
        features["shipment_id"] == shipment_id
    ].copy()

    if shipment_rows.empty:
        raise HTTPException(
            status_code=404,
            detail="Shipment features not found.",
        )

    # Use the latest available prediction snapshot.
    shipment_rows = shipment_rows.sort_values(
        "prediction_at"
    )

    latest_row = shipment_rows.iloc[-1]

    feature_columns = (
        eta_model.feature_names_in_.tolist()
    )

    missing_columns = [
        column
        for column in feature_columns
        if column not in latest_row.index
    ]

    if missing_columns:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Required model features are missing.",
                "missing_features": missing_columns,
            },
        )

    X = pd.DataFrame(
        [latest_row[feature_columns]],
        columns=feature_columns,
    )

    return latest_row, X


# --------------------------------------------------
# GET SLA INFORMATION
# --------------------------------------------------

def get_sla_information(shipment_id):

    engine = get_database_engine()

    query = text("""
        SELECT
            s.promised_delivery_at,
            sl.late_grace_minutes
        FROM shipment s
        JOIN service_level sl
            ON s.service_level_id = sl.service_level_id
        WHERE s.shipment_id = :shipment_id
    """)

    with engine.connect() as connection:
        result = connection.execute(
            query,
            {"shipment_id": shipment_id},
        ).mappings().first()

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Shipment or service-level information not found.",
        )

    return result


# --------------------------------------------------
# RUN BOTH MODELS AND SAVE ESTIMATE
# --------------------------------------------------

def generate_prediction(shipment_id):

    if eta_model is None or delay_model is None:
        raise HTTPException(
            status_code=503,
            detail="One or more trained models are unavailable.",
        )

    latest_row, X = get_shipment_features(shipment_id)

    sla = get_sla_information(shipment_id)

    prediction_at = latest_row["prediction_at"]

    # ETA regression prediction.
    remaining_minutes = float(
        eta_model.predict(X)[0]
    )

    # Do not return an ETA earlier than prediction time.
    remaining_minutes = max(0.0, remaining_minutes)

    predicted_delivery_at = (
        prediction_at
        + pd.to_timedelta(remaining_minutes, unit="m")
    )
    predicted_delivery_at = predicted_delivery_at.floor("us")

    # Delay classification probability.
    probabilities = delay_model.predict_proba(X)[0]

    classes = delay_model.named_steps["model"].classes_

    late_class_index = list(classes).index(1)

    delay_probability = float(
        probabilities[late_class_index]
    )

    # Calculate predicted delay against the SLA deadline.
    promised_delivery_at = pd.Timestamp(
        sla["promised_delivery_at"]
    )

    if promised_delivery_at.tzinfo is None:
        promised_delivery_at = promised_delivery_at.tz_localize(
            "UTC"
        )
    else:
        promised_delivery_at = promised_delivery_at.tz_convert(
            "UTC"
        )

    sla_deadline = (
        promised_delivery_at
        + pd.to_timedelta(
            int(sla["late_grace_minutes"]),
            unit="m",
        )
    )

    predicted_delay_minutes = max(
        0,
        int(
            round(
                (
                    predicted_delivery_at
                    - sla_deadline
                ).total_seconds() / 60
            )
        ),
    )

    # Stable ID for this shipment and prediction snapshot.
    timestamp_part = prediction_at.strftime(
        "%Y%m%dT%H%M%S%f"
    )

    eta_id = (
        f"ETA-{shipment_id}-{timestamp_part}"
    )

    # Save prediction without overwriting an existing estimate.
    engine = get_database_engine()

    insert_query = text("""
        INSERT INTO eta_estimate (
            eta_id,
            shipment_id,
            prediction_at,
            predicted_delivery_at,
            predicted_delay_minutes,
            delay_probability,
            model_version,
            feature_cutoff_at
        )
        VALUES (
            :eta_id,
            :shipment_id,
            :prediction_at,
            :predicted_delivery_at,
            :predicted_delay_minutes,
            :delay_probability,
            :model_version,
            :feature_cutoff_at
        )
        ON CONFLICT (
            shipment_id,
            prediction_at,
            model_version
        )
        DO NOTHING
    """)

    with engine.begin() as connection:
        connection.execute(
            insert_query,
            {
                "eta_id": eta_id,
                "shipment_id": shipment_id,
                "prediction_at": prediction_at.to_pydatetime(),
                "predicted_delivery_at": (
                    predicted_delivery_at.to_pydatetime()
                ),
                "predicted_delay_minutes": (
                    predicted_delay_minutes
                ),
                "delay_probability": delay_probability,
                "model_version": MODEL_VERSION,
                "feature_cutoff_at": prediction_at.to_pydatetime(),
            },
        )

        # Return the stored estimate, including if it already existed.
        saved = connection.execute(
            text("""
                SELECT
                    eta_id,
                    shipment_id,
                    prediction_at,
                    predicted_delivery_at,
                    predicted_delay_minutes,
                    delay_probability,
                    model_version
                FROM eta_estimate
                WHERE shipment_id = :shipment_id
                  AND prediction_at = :prediction_at
                  AND model_version = :model_version
            """),
            {
                "shipment_id": shipment_id,
                "prediction_at": prediction_at.to_pydatetime(),
                "model_version": MODEL_VERSION,
            },
        ).mappings().first()

    if saved is None:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve the saved ETA estimate.",
        )

    return {
        "eta_id": saved["eta_id"],
        "shipment_id": saved["shipment_id"],
        "prediction_at": saved["prediction_at"].isoformat(),
        "estimated_delivery_at": (
            saved["predicted_delivery_at"].isoformat()
        ),
        "remaining_delivery_minutes": round(
            remaining_minutes, 2
        ),
        "predicted_delay_minutes": (
            saved["predicted_delay_minutes"]
        ),
        "delay_probability": float(
            saved["delay_probability"]
        ),
        "model_version": saved["model_version"],
    }


# --------------------------------------------------
# ETA PREDICTION ENDPOINT
# --------------------------------------------------

@app.post("/predict/eta")
def predict_eta(request: ShipmentRequest):

    result = generate_prediction(
        request.shipment_id
    )

    return {
        "prediction_type": "ETA",
        **result,
    }


# --------------------------------------------------
# DELAY PREDICTION ENDPOINT
# --------------------------------------------------

@app.post("/predict/delay")
def predict_delay(request: ShipmentRequest):

    result = generate_prediction(
        request.shipment_id
    )

    return {
        "prediction_type": "DELAY",
        "is_delay_likely": (
            result["delay_probability"] >= 0.5
        ),
        **result,
    }
