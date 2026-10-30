# Logistics ETA Prediction and Delay Detection

A reproducible synthetic logistics data platform and ETA/delay analytics project.

## Stage 1: environment

1. Install Python 3.11+ and PostgreSQL 15+.
2. Create a database named `logistics_eta`.
3. Create and activate a virtual environment.
4. Install dependencies with `pip install -r requirements.txt`.
5. Copy `.env.example` to `.env` and update `DATABASE_URL`.

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Stage 2: database

Run the schema from the repository root:

```powershell
psql -U postgres -d logistics_eta -f sql/schema.sql
```

The schema uses immutable event records and effective-dated relationship/history tables.
It intentionally keeps anomaly ground truth outside operational input tables.

## Project layout

- `sql/schema.sql`: normalized PostgreSQL schema and integrity constraints.
- `docs/data_dictionary.md`: field definitions, units, allowed values and rules.
- `src/logistics_eta/`: generator, validation, business rules, model and API modules (implemented in subsequent stages).
- `data/raw/`: generated source CSV/JSON.
- `data/processed/`: model-ready snapshots, excluding ground truth.
- `reports/`: validation and evaluation reports.
- `tests/`: automated tests.

## Reproducibility contract

The default seed is `20261022`. The same generator version, configuration and seed must yield identical row counts and file checksums. Record the generator version and configuration in the source manifest. Do not edit generated source files manually.

## Temporal leakage contract

For a prediction made at timestamp `prediction_at`, only tracking events with
`ingested_at <= prediction_at` may be used. Event-time ordering alone is not enough:
a scan that occurred earlier but arrived after the prediction cutoff is unavailable
to the model at that cutoff. The separate `ground_truth` output must never be joined
to model features.

## Anomaly policy

The four required negative cases are represented as labelled cases in a separate
ground-truth file. Operational records remain structurally valid wherever possible;
deliberate business anomalies are not silently mixed into unrelated rows.
