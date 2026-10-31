# Logistics ETA Prediction and Delay Detection System

An end-to-end logistics analytics and machine learning system that estimates shipment delivery times, identifies potential delays, and evaluates shipment performance using time-aware tracking, route, carrier, facility, and weather information.

**GitHub Repository:**  
https://github.com/nagubandichaitanya/logistics-eta-delay-prediction

---

## 1. Project Overview

The Logistics ETA Prediction and Delay Detection System combines multiple logistics data sources to estimate shipment arrival times and identify shipments at risk of delay.

The system works with:

- Shipment and shipment-leg information
- Carrier and route details
- Tracking events
- Facility queues and operating calendars
- Weather disruptions
- Service-level agreements (SLAs)
- Shipment status and route history

The project demonstrates data engineering, synthetic data generation, PostgreSQL database integration, temporal feature engineering, machine learning, REST API development, and automated testing.

It uses reproducible synthetic logistics data and is designed as a prototype for logistics ETA prediction and delay detection.

## 2. Objectives

1. Generate realistic synthetic logistics datasets.
2. Design and maintain relational logistics data in PostgreSQL.
3. Validate shipment, route, tracking, and disruption records.
4. Generate time-aware ETA prediction features.
5. Prevent future-event and late-arriving-event data leakage.
6. Predict remaining shipment delivery time using regression.
7. Detect potential shipment delays using classification.
8. Expose prediction functionality through FastAPI.
9. Maintain reproducible datasets and validation reports.

## 3. Technology Stack

| Area | Technologies |
|---|---|
| Programming language | Python 3.11 |
| Database | PostgreSQL |
| Data processing | Pandas, NumPy |
| Machine learning | Scikit-learn, Random Forest |
| API development | FastAPI, Uvicorn |
| Model persistence | Joblib |
| Testing | Pytest, HTTPX2 |
| Version control | Git, GitHub |

## 4. Project Structure

```text
logistics-eta-delay-prediction/
│
├── data/
│   ├── raw/
│   └── processed/
│
├── docs/
│   ├── AI_USAGE.md
│   └── ASSUMPTIONS_AND_LIMITATIONS.md
│
├── models/
│
├── reports/
│   ├── source_manifest.json
│   └── validation_summary.json
│
├── sql/
│   └── schema.sql
│
├── src/
│   └── logistics_eta/
│       ├── __init__.py
│       ├── api.py
│       ├── config.py
│       ├── database_loader.py
│       ├── dataset_pipeline.py
│       ├── derived_data.py
│       ├── derived_data_loader.py
│       ├── disruption_data.py
│       ├── feature_engineering.py
│       ├── master_data.py
│       ├── model_training.py
│       ├── multi_snapshot_features.py
│       ├── scenario_validation.py
│       ├── shipment_data.py
│       ├── source_manifest.py
│       ├── tracking_events.py
│       ├── validate_features.py
│       └── validation_report.py
│
├── tests/
│   ├── __init__.py
│   ├── test_api.py
│   └── test_negative_scenarios.py
│
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

Generated datasets, local environment files, and trained model artifacts are not necessarily committed to GitHub. They can be regenerated using the instructions below.

## 5. Prerequisites

Install the following:

- Python 3.11 or later
- PostgreSQL 15 or later
- Git
- pip

## 6. Installation and Setup

### Step 1: Clone the repository

```powershell
git clone https://github.com/nagubandichaitanya/logistics-eta-delay-prediction.git

cd logistics-eta-delay-prediction
```

### Step 2: Create a virtual environment

```powershell
py -3.11 -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\Activate.ps1
```

### Step 3: Install dependencies

```powershell
python -m pip install --upgrade pip

pip install -r requirements.txt
```

### Step 4: Configure environment variables

Create a local `.env` file from the example:

```powershell
Copy-Item .env.example .env
```

Update the database connection details in `.env`:

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

Replace `YOUR_PASSWORD` with your local PostgreSQL password.

**Security:** Never upload `.env` or expose database credentials in GitHub.

## 7. PostgreSQL Database Setup

### Step 1: Create the database

```powershell
psql -U postgres -h localhost -c "CREATE DATABASE logistics_eta_db;"
```

Run this only if the database does not already exist.

### Step 2: Execute the schema

```powershell
psql -U postgres -d logistics_eta_db -h localhost -f sql/schema.sql
```

The database schema contains 16 relational tables covering:

- Carrier
- Carrier calendar
- Facility
- Facility calendar
- Route
- Service level
- Shipment
- Shipment leg
- Tracking event
- Weather event
- Facility queue
- ETA estimate
- Delay reason
- Shipment status history
- Shipment route history
- Shipment weather exposure

The schema uses primary keys and foreign keys to maintain data relationships and integrity.

## 8. Synthetic Data Generation

The project uses a configurable synthetic data generator.

### Starter dataset configuration

| Dataset | Configuration |
|---|---:|
| Shipments | 1,000 |
| Tracking events per shipment | 6 |
| Facilities | 100 |
| Disruption windows | 1,000 |
| Random seed | 20261022 |

The generator supports parameterized configuration for larger datasets.

### Step 1: Generate raw datasets

```powershell
python -m src.logistics_eta.dataset_pipeline
```

This generates and validates the source datasets in `data/raw/`.

Generated datasets include:

- carrier.csv
- carrier_calendar.csv
- facility.csv
- facility_calendar.csv
- facility_queue.csv
- route.csv
- service_level.csv
- shipment.csv
- shipment_leg.csv
- tracking_event.csv
- weather_event.csv

### Step 2: Load raw datasets into PostgreSQL

```powershell
python -m src.logistics_eta.database_loader
```

### Step 3: Generate derived datasets

```powershell
python -m src.logistics_eta.derived_data
```

This generates:

- shipment_status_history.csv
- shipment_route_history.csv
- shipment_weather_exposure.csv
- delay_reason.csv

### Step 4: Load derived datasets into PostgreSQL

```powershell
python -m src.logistics_eta.derived_data_loader
```

The database must be initialized before loading. The derived-data loader prevents duplicate inserts when its destination tables are already populated.

For a complete rebuild, use a fresh database and follow the database setup and loading steps in order.

## 9. Temporal Feature Engineering

The project generates multiple ETA prediction snapshots for each shipment.

Run:

```powershell
python -m src.logistics_eta.multi_snapshot_features
```

### Prediction snapshots

| Snapshot | Prediction time |
|---|---|
| 0 hours | At planned pickup |
| 12 hours | 12 hours after planned pickup |
| 24 hours | 24 hours after planned pickup |

Shipments already delivered before a prediction timestamp are excluded from that snapshot.

### Features generated

- Shipment weight and priority
- Service level
- Shipment age
- Remaining promised delivery time
- Planned route distance
- Number of route legs
- Completed and remaining route distance
- Tracking event count
- Last known tracking event
- Time since the last tracking event
- Facility queue information
- Weather exposure
- Prediction timestamp information

### Feature and ground-truth separation

The feature pipeline creates two separate datasets:

```text
data/processed/
    eta_features_multi_snapshot.csv
    ground_truth_multi_snapshot.csv
```

Ground-truth labels are kept separate from model features to reduce the risk of target leakage.

The generated multi-snapshot dataset contains:

| Snapshot | Feature records |
|---|---:|
| 0 hours | 1,000 |
| 12 hours | 899 |
| 24 hours | 819 |
| **Total** | **2,718** |

## 10. Machine Learning Models

Run the training pipeline:

```powershell
python -m src.logistics_eta.model_training
```

The project implements two machine learning tasks.

### A. ETA Prediction — Regression

A Random Forest Regressor estimates the remaining delivery time in minutes.

Evaluation metrics:

- Mean Absolute Error (MAE)
- Root Mean Squared Error (RMSE)
- R-squared (R²)

### B. Delay Detection — Classification

A Random Forest Classifier predicts whether a shipment is likely to exceed its SLA deadline.

Evaluation metrics:

- Accuracy
- Precision
- Recall
- F1-score
- ROC-AUC
- Confusion matrix

The training pipeline uses a chronological shipment-level train/test split. Snapshots belonging to the same shipment are kept in the same partition.

### Experimental results

The current README records the following preliminary results from the synthetic-data experiment:

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

These are experimental results on synthetic data, not validated real-world performance.

The training pipeline saves:

```text
models/
    eta_regression_model.joblib
    delay_classification_model.joblib

reports/
    model_metrics.json
```

## 11. FastAPI Application

Start the API:

```powershell
uvicorn logistics_eta.api:app --reload --app-dir src
```

Open the interactive API documentation:

http://127.0.0.1:8000/docs

### Available endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Check API and model availability |
| POST | `/predict/eta` | Predict estimated delivery time |
| POST | `/predict/delay` | Predict shipment delay risk |

### Example ETA request

```json
{
    "shipment_id": "SHP-2026-000001"
}
```

### Example delay request

```json
{
    "shipment_id": "SHP-2026-000001"
}
```

The prediction response includes shipment identification, prediction timestamp, estimated delivery time, remaining delivery minutes, delay information, and model version, according to the endpoint response schema.

Successful predictions are persisted in the PostgreSQL `eta_estimate` table.

**API limitation:** The current API retrieves the latest available precomputed feature snapshot. It does not yet calculate features from live tracking events, real-time weather feeds, or live facility data. It demonstrates the model and API workflow rather than a production live-ETA service.


## 12. Streamlit Dashboard

The project includes a Streamlit dashboard for shipment monitoring, SLA analytics, tracking event visualization, ETA prediction, and delay detection.

### Start the FastAPI Backend

Open the first terminal from the project root and run:

```powershell
uvicorn logistics_eta.api:app --reload --app-dir src
```

The API will be available at:

http://127.0.0.1:8000

API documentation:

http://127.0.0.1:8000/docs

### Start the Streamlit Dashboard

Keep the FastAPI backend running.

Open a second terminal from the project root and activate the virtual environment. Run:

```powershell
streamlit run app.py
```

The dashboard will be available at:

http://localhost:8501

### Dashboard Features

- Shipment overview and operational KPIs.
- Delivered, in-transit, and SLA performance metrics.
- Shipment status and priority filters.
- Shipment tracking event timeline.
- ETA prediction using the trained regression model.
- Delay probability using the trained classification model.
- FastAPI health monitoring.
- Prediction details and model version.

**Note:** Predictions use the latest available historical feature snapshot. The dashboard does not currently integrate live GPS or real-time carrier tracking.

## 13. Data Validation and Negative Scenario Testing

The project includes validation for data integrity and temporal correctness.

### Data validation checks

- Primary-key uniqueness
- Foreign-key integrity
- Allowed enumeration values
- Timestamp ordering
- Shipment lifecycle consistency
- Duplicate tracking records
- Route sequence connectivity
- Event and ingestion timestamp consistency
- Shipment status and delivery event consistency

### Temporal leakage prevention

For a prediction timestamp, a tracking event is eligible only when:

```text
event_at <= prediction_at
AND
ingested_at <= prediction_at
```

This prevents future events and late-arriving events from leaking into historical predictions.

### Negative scenarios tested

The test suite includes:

1. Late-arriving tracking event exclusion.
2. Disconnected shipment route detection.
3. Future tracking event exclusion.
4. In-transit shipment with an inconsistent delivered event.

### Run automated tests

```powershell
pytest -q
```

The latest verified test result during development was:

```text
9 passed
```

## 14. Feature Validation

Run:

```powershell
python -m src.logistics_eta.validate_features
```

This checks:

- Duplicate feature records
- Duplicate ground-truth records
- Feature and label key alignment
- Target leakage columns
- Snapshot-level label counts

The latest verified feature-validation result was:

```text
Feature shape: (2718, 23)
Labels shape: (2718, 7)
Duplicate feature records: 0
Duplicate label records: 0
Feature-label keys match: True
Target leakage columns: []

ALL FEATURE VALIDATION CHECKS PASSED
```

## 15. Reproducibility and Validation Reports

The project records dataset metadata and validation results.

### Generate the source manifest

```powershell
python -m src.logistics_eta.source_manifest
```

The manifest is saved to:

```text
reports/source_manifest.json
```

It contains:

- Dataset names
- Dataset types
- File names
- Record counts
- Column names
- Generation methods
- SHA-256 checksums

The latest generated manifest contains 19 datasets:

| Dataset type | Number of datasets |
|---|---:|
| Raw | 11 |
| Processed | 8 |
| **Total** | **19** |

### Generate the validation summary

Run this after generating the manifest and multi-snapshot features:

```powershell
python -m src.logistics_eta.validation_report
```

The report is saved to:

```text
reports/validation_summary.json
```

It checks:

- Dataset file existence
- Dataset row counts
- Dataset column counts
- SHA-256 checksum consistency
- Feature and label alignment
- Duplicate feature and label keys
- Target leakage columns
- Automated test results

The latest verified validation result was:

```text
Manifest checks: PASSED
Feature checks: PASSED
Automated tests: PASSED
Overall status: PASSED
```

## 16. Assumptions and Limitations

- The current datasets are synthetic and use a fixed random seed.
- Weather exposure indicates a possible disruption overlap; it does not prove that weather caused a delay.
- Facility queue information is a simplified representation of warehouse congestion.
- Weather records do not currently contain a separate ingestion timestamp. The feature pipeline uses a documented weather-availability assumption.
- The prediction snapshots are generated at fixed 0-hour, 12-hour, and 24-hour intervals.
- The current API uses precomputed features rather than live operational feeds.
- The model results must be evaluated against real historical logistics data before production use.
- The starter dataset is smaller than the full-scale challenge target.
- Full-scale performance and memory usage require additional benchmarking.

More details are available in:

- `docs/ASSUMPTIONS_AND_LIMITATIONS.md`
- `docs/AI_USAGE.md`

## 17. Future Improvements

- Integrate live carrier tracking APIs.
- Add real-time weather data and ingestion timestamps.
- Implement event-triggered ETA updates.
- Add historical carrier reliability and facility performance features.
- Improve model calibration and explainability.
- Add monitoring for prediction drift and data quality.
- Benchmark performance with the full-scale dataset.
- Build a dashboard for shipment monitoring and delay analysis.
- Add production authentication, logging, and deployment support.

## 18. AI Assistance Disclosure

AI tools were used as development assistance for project planning, understanding technical concepts, debugging, code review, test design, and documentation.

Generated suggestions were reviewed and tested during development. The developer remains responsible for understanding the implementation, verifying results, and explaining the technical decisions.

Refer to `docs/AI_USAGE.md` for further details.

## 19. Reproducibility

The default random seed is:

```text
20261022
```

To reproduce the experiment:

1. Use the documented Python and dependency versions.
2. Configure the environment variables.
3. Initialize PostgreSQL.
4. Generate raw and derived datasets.
5. Generate multi-snapshot features.
6. Generate the source manifest and validation report.
7. Run automated tests.

Regenerate source datasets using the project pipeline rather than manually editing generated CSV files.

---

## Repository

**GitHub:**  
https://github.com/nagubandichaitanya/logistics-eta-delay-prediction

**Project:** Logistics ETA Prediction and Delay Detection System

**Primary technologies:** Python, PostgreSQL, Pandas, NumPy, Scikit-learn, FastAPI, and Pytest.
