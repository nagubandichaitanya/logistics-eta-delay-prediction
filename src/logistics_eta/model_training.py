
from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    r2_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODEL_DIR = PROJECT_ROOT / "models"
REPORT_DIR = PROJECT_ROOT / "reports"

RANDOM_STATE = 20261022


NUMERIC_FEATURES = [
    "snapshot_hours",
    "weight_kg",
    "shipment_age_minutes",
    "promised_remaining_minutes",
    "carrier_count",
    "total_distance_km",
    "total_legs",
    "completed_legs",
    "remaining_distance_km",
    "tracking_event_count",
    "minutes_since_last_event",
    "queue_length",
    "estimated_wait_minutes",
    "capacity_utilization",
    "active_weather_count",
    "max_weather_delay_factor",
    "prediction_hour",
    "prediction_day_of_week",
    "prediction_month",
]

CATEGORICAL_FEATURES = [
    "service_level",
    "priority",
    "carrier_id",
    "last_event_type",
    "current_facility_id",
]

FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def load_datasets():
    features = pd.read_csv(
        PROCESSED_DIR / "eta_features_multi_snapshot.csv"
    )

    labels = pd.read_csv(
        PROCESSED_DIR / "ground_truth_multi_snapshot.csv"
    )

    features["prediction_at"] = pd.to_datetime(
        features["prediction_at"],
        utc=True,
    )

    labels["prediction_at"] = pd.to_datetime(
        labels["prediction_at"],
        utc=True,
    )

    labels["label_available"] = (
        labels["label_available"]
        .astype(str)
        .str.lower()
        .eq("true")
    )

    labels["is_sla_late"] = (
        labels["is_sla_late"]
        .astype(str)
        .str.lower()
        .map({"true": True, "false": False})
    )

    return features, labels


def add_time_features(features):
    features = features.copy()

    features["prediction_hour"] = (
        features["prediction_at"].dt.hour
    )

    features["prediction_day_of_week"] = (
        features["prediction_at"].dt.dayofweek
    )

    features["prediction_month"] = (
        features["prediction_at"].dt.month
    )

    return features


def chronological_shipment_split(features):
    """
    Split complete shipments chronologically.

    Every snapshot belonging to one shipment stays
    in the same train or test partition.
    """

    base = features[
        features["snapshot_hours"] == 0
    ][["shipment_id", "prediction_at"]].copy()

    base = base.sort_values(
        ["prediction_at", "shipment_id"]
    ).reset_index(drop=True)

    split_index = int(len(base) * 0.80)

    train_ids = set(
        base.iloc[:split_index]["shipment_id"]
    )

    test_ids = set(
        base.iloc[split_index:]["shipment_id"]
    )

    if train_ids.intersection(test_ids):
        raise ValueError("Shipment leakage detected.")

    return train_ids, test_ids


def build_preprocessor():
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="most_frequent"),
            ),
            (
                "encoder",
                OneHotEncoder(handle_unknown="ignore"),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "numeric",
                numeric_pipeline,
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                categorical_pipeline,
                CATEGORICAL_FEATURES,
            ),
        ]
    )

    return preprocessor


def prepare_training_data(features, labels):
    features = add_time_features(features)

    model_data = features.merge(
        labels,
        on=[
            "shipment_id",
            "snapshot_hours",
            "prediction_at",
        ],
        how="inner",
        validate="one_to_one",
    )

    if len(model_data) != len(features):
        raise ValueError(
            "Some feature records do not have matching labels."
        )

    train_ids, test_ids = chronological_shipment_split(
        features
    )

    # Only shipments with known final outcomes can train
    # the delivery-time and SLA models.
    delivered = model_data[
        model_data["label_available"] == True
    ].copy()

    train = delivered[
        delivered["shipment_id"].isin(train_ids)
    ].copy()

    test = delivered[
        delivered["shipment_id"].isin(test_ids)
    ].copy()

    if train.empty or test.empty:
        raise ValueError(
            "Training or testing dataset is empty."
        )

    if train["shipment_id"].isin(
        test["shipment_id"]
    ).any():
        raise ValueError(
            "A shipment appears in both train and test."
        )

    if train["remaining_delivery_minutes"].isna().any():
        raise ValueError(
            "Missing regression targets in training data."
        )

    if test["remaining_delivery_minutes"].isna().any():
        raise ValueError(
            "Missing regression targets in testing data."
        )

    if train["is_sla_late"].isna().any():
        raise ValueError(
            "Missing classification targets in training data."
        )

    if test["is_sla_late"].isna().any():
        raise ValueError(
            "Missing classification targets in testing data."
        )

    X_train = train[FEATURE_COLUMNS]
    X_test = test[FEATURE_COLUMNS]

    y_train_reg = train["remaining_delivery_minutes"]
    y_test_reg = test["remaining_delivery_minutes"]

    y_train_cls = train["is_sla_late"].astype(int)
    y_test_cls = test["is_sla_late"].astype(int)

    print("\nDATASET SPLIT")
    print("-------------")
    print("Training shipments:", len(train_ids))
    print("Testing shipments:", len(test_ids))
    print("Training labelled records:", len(train))
    print("Testing labelled records:", len(test))

    print("\nTraining records by snapshot:")
    print(train["snapshot_hours"].value_counts().sort_index())

    print("\nTesting records by snapshot:")
    print(test["snapshot_hours"].value_counts().sort_index())

    return (
        train,
        test,
        X_train,
        X_test,
        y_train_reg,
        y_test_reg,
        y_train_cls,
        y_test_cls,
    )


def train_regression_model(
    X_train,
    X_test,
    y_train,
    y_test,
):
    print("\nTRAINING ETA REGRESSION MODEL")
    print("-----------------------------")

    model = Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=300,
                    min_samples_leaf=2,
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                ),
            ),
        ]
    )

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    metrics = {
        "mae_minutes": float(
            mean_absolute_error(y_test, predictions)
        ),
        "rmse_minutes": float(
            np.sqrt(mean_squared_error(y_test, predictions))
        ),
        "r2": float(
            r2_score(y_test, predictions)
        ),
    }

    print("MAE (minutes):", round(metrics["mae_minutes"], 2))
    print("RMSE (minutes):", round(metrics["rmse_minutes"], 2))
    print("R2 score:", round(metrics["r2"], 4))

    return model, predictions, metrics


def train_classification_model(
    X_train,
    X_test,
    y_train,
    y_test,
):
    print("\nTRAINING DELAY CLASSIFICATION MODEL")
    print("-----------------------------------")

    model = Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=300,
                    min_samples_leaf=2,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                ),
            ),
        ]
    )

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    probabilities = model.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy": float(
            accuracy_score(y_test, predictions)
        ),
        "precision": float(
            precision_score(
                y_test,
                predictions,
                zero_division=0,
            )
        ),
        "recall": float(
            recall_score(
                y_test,
                predictions,
                zero_division=0,
            )
        ),
        "f1_score": float(
            f1_score(
                y_test,
                predictions,
                zero_division=0,
            )
        ),
    }

    if y_test.nunique() == 2:
        metrics["roc_auc"] = float(
            roc_auc_score(y_test, probabilities)
        )
    else:
        metrics["roc_auc"] = None

    print("Accuracy:", round(metrics["accuracy"], 4))
    print("Precision:", round(metrics["precision"], 4))
    print("Recall:", round(metrics["recall"], 4))
    print("F1 score:", round(metrics["f1_score"], 4))
    print("ROC-AUC:", metrics["roc_auc"])

    print("\nClassification report:")
    print(
        classification_report(
            y_test,
            predictions,
            zero_division=0,
        )
    )

    print("Confusion matrix:")
    print(confusion_matrix(y_test, predictions))

    return model, predictions, probabilities, metrics


def evaluate_by_snapshot(test, regression_predictions):
    results = test[
        [
            "shipment_id",
            "snapshot_hours",
            "remaining_delivery_minutes",
        ]
    ].copy()

    results["predicted_minutes"] = regression_predictions

    results["absolute_error_minutes"] = (
        results["remaining_delivery_minutes"]
        - results["predicted_minutes"]
    ).abs()

    print("\nREGRESSION PERFORMANCE BY SNAPSHOT")
    print("-----------------------------------")

    print(
        results.groupby("snapshot_hours")[
            "absolute_error_minutes"
        ].mean().round(2)
    )


def evaluate_baselines(train, test, y_train_cls, y_test_cls):
    """
    Compare trained models with simple baseline predictions.
    """

    print("\nBASELINE MODEL EVALUATION")
    print("-------------------------")

    # 1. ETA regression baseline:
    # Predict delivery exactly at the promised delivery time.
    baseline_reg_predictions = (
        test["promised_remaining_minutes"].astype(float)
    )

    actual_reg = (
        test["remaining_delivery_minutes"].astype(float)
    )

    regression_baseline_metrics = {
        "mae_minutes": float(
            mean_absolute_error(
                actual_reg,
                baseline_reg_predictions,
            )
        ),
        "rmse_minutes": float(
            np.sqrt(
                mean_squared_error(
                    actual_reg,
                    baseline_reg_predictions,
                )
            )
        ),
        "r2": float(
            r2_score(
                actual_reg,
                baseline_reg_predictions,
            )
        ),
    }

    print("\nETA PROMISED-TIME BASELINE")
    print("MAE:", round(
        regression_baseline_metrics["mae_minutes"], 2
    ))
    print("RMSE:", round(
        regression_baseline_metrics["rmse_minutes"], 2
    ))
    print("R2:", round(
        regression_baseline_metrics["r2"], 4
    ))

    # 2. Delay classification baseline:
    # Always predict the most frequent class in training data.
    baseline_classifier = DummyClassifier(
        strategy="most_frequent"
    )

    baseline_classifier.fit(
        np.zeros((len(y_train_cls), 1)),
        y_train_cls,
    )

    baseline_cls_predictions = baseline_classifier.predict(
        np.zeros((len(y_test_cls), 1))
    )

    classification_baseline_metrics = {
        "accuracy": float(
            accuracy_score(
                y_test_cls,
                baseline_cls_predictions,
            )
        ),
        "precision": float(
            precision_score(
                y_test_cls,
                baseline_cls_predictions,
                zero_division=0,
            )
        ),
        "recall": float(
            recall_score(
                y_test_cls,
                baseline_cls_predictions,
                zero_division=0,
            )
        ),
        "f1_score": float(
            f1_score(
                y_test_cls,
                baseline_cls_predictions,
                zero_division=0,
            )
        ),
        "roc_auc": None,
    }

    print("\nMAJORITY-CLASS CLASSIFICATION BASELINE")
    print("Accuracy:", round(
        classification_baseline_metrics["accuracy"], 4
    ))
    print("Precision:", round(
        classification_baseline_metrics["precision"], 4
    ))
    print("Recall:", round(
        classification_baseline_metrics["recall"], 4
    ))
    print("F1:", round(
        classification_baseline_metrics["f1_score"], 4
    ))

    return {
        "regression": regression_baseline_metrics,
        "classification": classification_baseline_metrics,
    }



def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading multi-snapshot datasets...")

    features, labels = load_datasets()

    (
        train,
        test,
        X_train,
        X_test,
        y_train_reg,
        y_test_reg,
        y_train_cls,
        y_test_cls,
    ) = prepare_training_data(features, labels)

    reg_model, reg_predictions, reg_metrics = (
        train_regression_model(
            X_train,
            X_test,
            y_train_reg,
            y_test_reg,
        )
    )

    cls_model, cls_predictions, cls_probabilities, cls_metrics = (
        train_classification_model(
            X_train,
            X_test,
            y_train_cls,
            y_test_cls,
        )
    )

    evaluate_by_snapshot(test, reg_predictions)
    baseline_metrics = evaluate_baselines(
        train,
        test,
        y_train_cls,
        y_test_cls,
    )

    # Save trained pipelines, including preprocessing.
    joblib.dump(
        reg_model,
        MODEL_DIR / "eta_regression_model.joblib",
    )

    joblib.dump(
        cls_model,
        MODEL_DIR / "delay_classification_model.joblib",
    )

    metrics = {
        "regression": reg_metrics,
        "classification": cls_metrics,
        "baselines": baseline_metrics,
        "random_state": RANDOM_STATE,
        "train_shipments": int(
            train["shipment_id"].nunique()
        ),
        "test_shipments": int(
            test["shipment_id"].nunique()
        ),
        "train_records": len(train),
        "test_records": len(test),
    }

    with open(
        REPORT_DIR / "model_metrics.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(metrics, file, indent=4)

    print("\nMODEL TRAINING COMPLETED")
    print("------------------------")
    print("Regression model saved.")
    print("Classification model saved.")
    print("Metrics saved to reports/model_metrics.json")


if __name__ == "__main__":
    main()
