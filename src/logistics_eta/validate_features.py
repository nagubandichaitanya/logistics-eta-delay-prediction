
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def main():
    features = pd.read_csv(
        PROCESSED_DIR / "eta_features_multi_snapshot.csv"
    )

    labels = pd.read_csv(
        PROCESSED_DIR / "ground_truth_multi_snapshot.csv"
    )

    print("\nFEATURE DATA VALIDATION")
    print("-----------------------")

    print("Feature shape:", features.shape)
    print("Label shape:", labels.shape)

    # Check duplicate records
    feature_duplicates = features.duplicated(
        subset=["shipment_id", "snapshot_hours"]
    ).sum()

    label_duplicates = labels.duplicated(
        subset=["shipment_id", "snapshot_hours"]
    ).sum()

    print("Duplicate feature records:", feature_duplicates)
    print("Duplicate label records:", label_duplicates)

    # Check matching shipment-snapshot keys
    feature_keys = set(
        zip(features["shipment_id"], features["snapshot_hours"])
    )

    label_keys = set(
        zip(labels["shipment_id"], labels["snapshot_hours"])
    )

    print("Feature and label keys match:", feature_keys == label_keys)

    # Check for target leakage
    forbidden_columns = [
        "actual_delivery_at",
        "remaining_delivery_minutes",
        "is_sla_late",
        "label_available",
    ]

    leakage_columns = [
        column
        for column in forbidden_columns
        if column in features.columns
    ]

    print("Target leakage columns:", leakage_columns)

    # Check label availability
    print("\nLabel availability:")
    print(labels.groupby("snapshot_hours")["label_available"].value_counts())

    if (
        feature_duplicates == 0
        and label_duplicates == 0
        and feature_keys == label_keys
        and not leakage_columns
    ):
        print("\nALL FEATURE VALIDATION CHECKS PASSED")
    else:
        raise ValueError("Feature validation failed!")


if __name__ == "__main__":
    main()