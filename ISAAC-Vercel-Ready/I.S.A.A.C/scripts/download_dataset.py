"""
Download, process, and sample the AI4I 2020 Predictive Maintenance Dataset from UCI Repository.

Source: UCI Machine Learning Repository
URL: https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset
Citation: Matzka, S. (2020). AI4I 2020 Predictive Maintenance Dataset. UCI Machine Learning Repository.
License: Creative Commons Attribution 4.0 International (CC BY 4.0)
"""

import csv
import io
import os
import urllib.request
import zipfile
from pathlib import Path

UCI_DATASET_ZIP_URL = "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLE_DIR = DATA_DIR / "sample"

COLUMN_MAPPING = {
    "UDI": "udi",
    "Product ID": "product_id",
    "Type": "machine_type",
    "Air temperature [K]": "air_temperature_k",
    "Process temperature [K]": "process_temperature_k",
    "Rotational speed [rpm]": "rotational_speed_rpm",
    "Torque [Nm]": "torque_nm",
    "Tool wear [min]": "tool_wear_min",
    "Machine failure": "machine_failure",
    "TWF": "twf",
    "HDF": "hdf",
    "PWF": "pwf",
    "OSF": "osf",
    "RNF": "rnf",
}


def download_and_extract_raw() -> Path:
    """Download the official UCI dataset zip and extract the raw CSV."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_csv_path = RAW_DIR / "ai4i2020.csv"

    print(f"Fetching dataset from {UCI_DATASET_ZIP_URL}...")
    req = urllib.request.Request(UCI_DATASET_ZIP_URL, headers={"User-Agent": "ISAAC-Data-Pipeline/1.0"})
    with urllib.request.urlopen(req) as resp:
        zip_bytes = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # ai4i2020.csv is the data file within the zip archive
        with zf.open("ai4i2020.csv") as source_file:
            raw_content = source_file.read()

    with open(raw_csv_path, "wb") as f:
        f.write(raw_content)

    print(f"Saved raw dataset to {raw_csv_path} ({len(raw_content)} bytes)")
    return raw_csv_path


def process_dataset(raw_csv_path: Path) -> Path:
    """Clean, standardize column headers, and parse records into processed CSV."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    processed_csv_path = PROCESSED_DIR / "ai4i2020_cleaned.csv"

    rows = []
    with open(raw_csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Strip potential BOM or whitespace from field names
        fieldnames = [fn.lstrip("\ufeff").strip() for fn in reader.fieldnames]
        reader.fieldnames = fieldnames

        for row in reader:
            cleaned_row = {
                COLUMN_MAPPING[k]: row[k].strip()
                for k in reader.fieldnames
                if k in COLUMN_MAPPING
            }
            rows.append(cleaned_row)

    output_fieldnames = list(COLUMN_MAPPING.values())
    with open(processed_csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved processed dataset to {processed_csv_path} ({len(rows)} rows)")
    return processed_csv_path


def create_sample_dataset(processed_csv_path: Path, sample_size: int = 100) -> Path:
    """
    Create a representative sample dataset.
    Includes all failure cases (TWF, HDF, PWF, OSF, RNF) and normal operational rows up to sample_size.
    """
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    sample_csv_path = SAMPLE_DIR / "sample_ai4i2020.csv"

    failures = []
    normal = []

    with open(processed_csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["machine_failure"] == "1":
                failures.append(row)
            else:
                normal.append(row)

    # Take representative failure modes
    # Failures: pick up to 30 failures spanning all 5 modes
    twf_cases = [r for r in failures if r["twf"] == "1"][:6]
    hdf_cases = [r for r in failures if r["hdf"] == "1"][:6]
    pwf_cases = [r for r in failures if r["pwf"] == "1"][:6]
    osf_cases = [r for r in failures if r["osf"] == "1"][:6]
    rnf_cases = [r for r in failures if r["rnf"] == "1"][:6]

    selected_failures = {r["udi"]: r for r in (twf_cases + hdf_cases + pwf_cases + osf_cases + rnf_cases)}
    for f_row in failures:
        if len(selected_failures) >= 30:
            break
        selected_failures[f_row["udi"]] = f_row

    needed_normal = sample_size - len(selected_failures)
    selected_normal = normal[:needed_normal]

    sample_rows = list(selected_failures.values()) + selected_normal
    sample_rows.sort(key=lambda r: int(r["udi"]))

    with open(sample_csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sample_rows)

    print(f"Saved sample dataset to {sample_csv_path} ({len(sample_rows)} rows)")
    return sample_csv_path


if __name__ == "__main__":
    raw_path = download_and_extract_raw()
    proc_path = process_dataset(raw_path)
    sample_path = create_sample_dataset(proc_path, sample_size=100)
    print("Dataset download, cleaning, and sampling completed successfully.")
