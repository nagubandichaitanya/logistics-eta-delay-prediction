from pathlib import Path
import hashlib
import json
import subprocess
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = PROJECT_ROOT / "reports"

MANIFEST_PATH = REPORTS_DIR / "source_manifest.json"
FEATURE_PATH = PROJECT_ROOT / "data" / "processed" / "eta_features_multi_snapshot.csv"
LABEL_PATH = PROJECT_ROOT / "data" / "processed" / "ground_truth_multi_snapshot.csv"


def calculate_checksum(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def check_manifest(manifest):
    results = []

    for dataset in manifest["datasets"]:
        folder = "raw" if dataset["dataset_type"] == "raw" else "processed"

        file_path = (
            PROJECT_ROOT / "data" / folder / dataset["file_name"]
        )

        exists = file_path.exists()

        if exists:
            dataframe = pd.read_csv(file_path)

            row_count_valid = len(dataframe) == dataset["record_count"]
            column_count_valid = len(dataframe.columns) == dataset["column_count"]
            checksum_valid = calculate_checksum(file_path) == dataset["sha256"]
        else:
            row_count_valid = False
            column_count_valid = False
            checksum_valid = False

        results.append({
            "dataset": dataset["dataset_name"],
            "file_exists": exists,
            "row_count_valid": row_count_valid,
            "column_count_valid": column_count_valid,
            "checksum_valid": checksum_valid,
        })

    return results


def check_features_and_labels():
    features = pd.read_csv(FEATURE_PATH)
    labels = pd.read_csv(LABEL_PATH)

    keys = ["shipment_id", "prediction_at"]

    feature_keys = features[keys]
    label_keys = labels[keys]

    feature_key_set = set(
        map(tuple, feature_keys.to_numpy())
    )

    label_key_set = set(
        map(tuple, label_keys.to_numpy())
    )

    target_columns = {
        "actual_delivery_at",
        "is_late",
        "delay_minutes",
        "actual_status",
        "delay_reason",
        "is_delayed",
        "late_minutes",
    }

    leakage_columns = sorted(
        set(features.columns).intersection(target_columns)
    )

    return {
        "feature_record_count": len(features),
        "label_record_count": len(labels),
        "duplicate_feature_keys": int(features.duplicated(keys).sum()),
        "duplicate_label_keys": int(labels.duplicated(keys).sum()),
        "feature_label_keys_match": feature_key_set == label_key_set,
        "target_leakage_columns": leakage_columns,
        "snapshot_record_counts": {
            str(key): int(value)
            for key, value in features["snapshot_hours"].value_counts().sort_index().items()
        },
    }


def run_tests():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    return {
        "passed": result.returncode == 0,
        "return_code": result.returncode,
        "output": result.stdout.strip(),
        "errors": result.stderr.strip(),
    }


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as file:
        manifest = json.load(file)

    manifest_results = check_manifest(manifest)
    feature_results = check_features_and_labels()
    test_results = run_tests()

    all_manifest_checks_passed = all(
        item["file_exists"]
        and item["row_count_valid"]
        and item["column_count_valid"]
        and item["checksum_valid"]
        for item in manifest_results
    )

    all_feature_checks_passed = (
        feature_results["duplicate_feature_keys"] == 0
        and feature_results["duplicate_label_keys"] == 0
        and feature_results["feature_label_keys_match"]
        and len(feature_results["target_leakage_columns"]) == 0
    )

    report = {
        "project": manifest["project"],
        "random_seed": manifest["random_seed"],
        "total_datasets": len(manifest["datasets"]),
        "manifest_validation": {
            "passed": all_manifest_checks_passed,
            "datasets": manifest_results,
        },
        "feature_validation": {
            "passed": all_feature_checks_passed,
            "details": feature_results,
        },
        "automated_tests": test_results,
        "overall_status": (
            "PASSED"
            if all_manifest_checks_passed
            and all_feature_checks_passed
            and test_results["passed"]
            else "FAILED"
        ),
    }

    output_path = REPORTS_DIR / "validation_summary.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    print("\nVALIDATION SUMMARY GENERATED")
    print("----------------------------")
    print("Manifest checks:", "PASSED" if all_manifest_checks_passed else "FAILED")
    print("Feature checks:", "PASSED" if all_feature_checks_passed else "FAILED")
    print("Automated tests:", "PASSED" if test_results["passed"] else "FAILED")
    print("Overall status:", report["overall_status"])
    print("Output:", output_path)


if __name__ == "__main__":
    main()