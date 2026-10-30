# Logistics ETA Prediction and Delay Detection System

An end-to-end logistics analytics and machine learning project that generates shipment data, engineers time-aware features, predicts estimated delivery time (ETA), and identifies shipments at risk of SLA delay.

## 1. Project Overview

The system combines logistics information from:

- Shipments and shipment legs
- Carrier and route information
- Tracking events
- Facility queues
- Weather disruptions
- Service-level agreements (SLAs)

It produces ETA predictions and delay probabilities using machine learning models.

The project uses synthetic logistics data and is designed to demonstrate data engineering, temporal feature engineering, machine learning, PostgreSQL integration, REST API development, and automated testing.

## 2. Technology Stack

| Area | Technologies |
|---|---|
| Programming | Python 3.11 |
| Database | PostgreSQL |
| Data processing | Pandas, NumPy |
| Machine learning | Scikit-learn, Random Forest |
| API | FastAPI, Uvicorn |
| Model persistence | Joblib |
| Testing | Pytest, HTTPX2 |
| Version control | Git, GitHub |

## 3. Project Structure

```text
logistics-eta-delay-prediction/
│
├── data/
│   ├── raw/
│   └── processed/
│
├── docs/
├── models/
├── reports/
├── sql/
│   └── schema.sql
│
├── src/
│   └── logistics_eta/
│       ├── api.py
│       ├── config.py
│       ├── database_loader.py
│       ├── dataset_pipeline.py
│       ├── derived_data.py
│       ├── derived_data_loader.py
│       ├── disruption_data.py
│       ├── feature_engineering.py
│       ├── master_data.py
│       ├── shipment_data.py
│       ├── tracking_events.py
│       ├── multi_snapshot_features.py
│       └── model_training.py
│
├── tests/
│   └── test_api.py
│
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

Generated datasets, trained models, local environment files, and reports are not necessarily committed to GitHub. Follow the generation steps below to recreate them.

## 4. Setup and Installation

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Git

### Clone the repository

```powershell
git clone https://github.com/nagubandichaitanya/logistics-eta-delay-prediction.git
cd logistics-eta-delay-prediction
```

### Create a virtual environment

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

### Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Configure environment variables

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Update the `DATABASE_URL` in `.env` with your local PostgreSQL password:

```text
APP_ENV=development
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/logistics_eta_db
RANDOM_SEED=20261022
SHIPMENT_COUNT=1000
EVENTS_PER_SHIPMENT=6
FACILITY_COUNT=100
DISRUPTION_COUNT=1000
DATA_DIR=data
```

Do not commit `.env` or expose database credentials.

## 5. Database Setup

Create the PostgreSQL database:

```powershell
psql -U postgres -h localhost -c "CREATE DATABASE logistics_eta_db;"
```

Execute the database schema:

```powershell
psql -U postgres -d logistics_eta_db -h localhost -f sql/schema.sql
```

The schema defines normalized tables for shipments, shipment legs, carriers, routes, facilities, tracking events, weather events, facility queues, SLA definitions, ETA estimates, and historical records.

## 6. Data Generation Pipeline

The default starter configuration is:

| Dataset | Target volume |
|---|---:|
| Shipments | 1,000 |
| Tracking events | Approximately 6,000 |
| Facilities | 100 |
| Disruption windows | 1,000 |

The random seed is `20261022`.

### Step 1: Generate raw datasets

```powershell
python -m src.logistics_eta.dataset_pipeline
```

This generates and validates the source datasets in `data/raw/`.

### Step 2: Load raw datasets into PostgreSQL

```powershell
python -m src.logistics_eta.database_loader
```

### Step 3: Generate derived datasets

```powershell
python -m src.logistics_eta.derived_data
```

This generates:

- `shipment_status_history.csv`
- `shipment_route_history.csv`
- `shipment_weather_exposure.csv`
- `delay_reason.csv`

### Step 4: Load derived datasets into PostgreSQL

```powershell
python -m src.logistics_eta.derived_data_loader
```

The loaders expect an appropriately initialized database. The derived-data loader deliberately stops if its destination tables are already populated, to prevent duplicate inserts. For a clean end-to-end rebuild, use a fresh database and follow the setup steps again.

## 7. Feature Engineering

Generate time-aware shipment features at multiple prediction snapshots:

```powershell
python -m src.logistics_eta.multi_snapshot_features
```

The pipeline creates snapshots at:

- Shipment pickup (0 hours)
- 12 hours after pickup
- 24 hours after pickup

It excludes delivered shipments from snapshots after their delivery time.

Features include:

- Shipment weight, priority, and service level
- Shipment age and remaining promised time
- Planned route distance and number of legs
- Completed and remaining route distance
- Tracking event count and last known event
- Time since the last tracking event
- Facility queue length and estimated wait
- Active weather exposure
- Prediction time information

Outputs:

- `data/processed/eta_features_multi_snapshot.csv`
- `data/processed/ground_truth_multi_snapshot.csv`

Ground-truth labels are kept separate from model features to prevent target leakage.

## 8. Machine Learning Models

Train both models:

```powershell
python -m src.logistics_eta.model_training
```

### ETA prediction — Regression

A Random Forest Regressor predicts the remaining delivery time in minutes.

Evaluation metrics:

- Mean Absolute Error (MAE)
- Root Mean Squared Error (RMSE)
- R-squared (R²)

### Delay detection — Classification

A Random Forest Classifier predicts whether a shipment will exceed its SLA deadline.

Evaluation metrics:

- Accuracy
- Precision
- Recall
- F1-score
- ROC-AUC
- Confusion matrix

The evaluation uses a chronological shipment-level train/test split. All snapshots belonging to the same shipment remain in the same partition.

### Current experimental results

| Metric | Result |
|---|---:|
| ETA regression MAE | 835.09 minutes |
| ETA regression RMSE | 1,045.84 minutes |
| ETA regression R² | 0.7935 |
| Delay classification accuracy | 88.59% |
| Delay classification precision | 87.83% |
| Delay classification recall | 89.78% |
| Delay classification F1-score | 88.79% |
| Delay classification ROC-AUC | 0.9656 |

These are preliminary results on a synthetic dataset. They should not be interpreted as expected production performance.

The training pipeline saves:

- `models/eta_regression_model.joblib`
- `models/delay_classification_model.joblib`
- `reports/model_metrics.json`

## 9. FastAPI Application

Start the API:

```powershell
python -m uvicorn src.logistics_eta.api:app --reload
```

Open the interactive API documentation:

http://127.0.0.1:8000/docs

### Available endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Check API and model availability |
| POST | `/predict/eta` | Predict estimated delivery time |
| POST | `/predict/delay` | Predict delay risk |

Example ETA request:

```json
{
  "shipment_id": "SHP-2026-000001"
}
```

Example delay request:

```json
{
  "shipment_id": "SHP-2026-000001"
}
```

The prediction response includes the shipment ID, prediction timestamp, estimated delivery timestamp, remaining delivery minutes, predicted delay minutes, delay probability, and model version.

Successful predictions are persisted in the PostgreSQL `eta_estimate` table.

**Current API limitation:** The API retrieves the latest available precomputed feature snapshot for the requested shipment. It does not yet calculate features from live tracking events or real-time weather and facility feeds. Predictions therefore demonstrate the model and API workflow using historical synthetic data, not a production live-ETA service.

## 10. Automated Testing

Run the test suite:

```powershell
pytest -q
```

The API tests cover:

- Health endpoint
- ETA prediction
- Delay prediction
- Invalid shipment ID
- Missing shipment ID

## 11. Data Quality and Temporal Leakage Controls

The data pipeline validates:

- Primary-key uniqueness
- Foreign-key integrity
- Allowed enum values
- Timestamp ordering
- Shipment lifecycle consistency
- Duplicate tracking records
- Non-negative delay values
- SLA label consistency

For a prediction timestamp, tracking events are only eligible when both their event time and ingestion time are at or before the prediction cutoff.

This prevents late-arriving tracking events from leaking future information into historical predictions.

## 12. Assumptions and Limitations

- The current dataset is synthetic and uses a fixed random seed.
- Weather exposure represents a time and facility overlap; it does not prove that weather caused a delay.
- Facility queue overlap is a potential contributing signal, not confirmed causation.
- Weather records do not currently have a separate ingestion timestamp. The feature pipeline uses the documented weather-window assumption.
- The API uses precomputed historical features rather than live operational feeds.
- Model performance must be evaluated on real operational data before production use.
- The current starter configuration is smaller than the full-scale challenge target.

## 13. Future Improvements

- Integrate live carrier tracking APIs.
- Add real-time weather data.
- Build dynamic feature calculation for incoming events.
- Add historical carrier and facility performance features.
- Improve model calibration and explainability.
- Add monitoring for prediction drift and data quality.
- Build a dashboard for shipment monitoring and delay analysis.

## 14. Reproducibility

The default random seed is `20261022`.

To reproduce the experiment, use the same generator version, configuration, dependencies, and seed. Regenerate source datasets instead of manually editing generated CSV files.

## 15. Repository

GitHub:

https://github.com/nagubandichaitanya/logistics-eta-delay-prediction

