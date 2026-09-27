"""
CLI Data Validation Script for ISAAC datasets.

Usage:
    python scripts/validate_data.py --file data/processed/ai4i2020_cleaned.csv
    python scripts/validate_data.py --file data/sample/sample_ai4i2020.csv
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.validation import validate_dataset_file


def main():
    parser = argparse.ArgumentParser(description="Validate predictive maintenance dataset integrity.")
    parser.add_argument(
        "--file",
        type=str,
        default="data/processed/ai4i2020_cleaned.csv",
        help="Path to CSV dataset to validate.",
    )
    args = parser.parse_args()

    target_file = (PROJECT_ROOT / args.file).resolve() if not Path(args.file).is_absolute() else Path(args.file)
    if not target_file.exists():
        print(f"ERROR: Target dataset file '{target_file}' does not exist.", file=sys.stderr)
        sys.exit(1)

    print(f"Validating dataset: {target_file.relative_to(PROJECT_ROOT)}...")
    report = validate_dataset_file(target_file)

    print("\n" + "=" * 60)
    print("DATA VALIDATION REPORT")
    print("=" * 60)
    print(f"File:            {target_file.name}")
    print(f"Total Records:   {report.total_records}")
    print(f"Valid Records:   {report.valid_records}")
    print(f"Invalid Records: {report.invalid_records}")
    print(f"Total Issues:    {len(report.issues)}")
    print(f"Status:          {'PASSED (VALID)' if report.is_valid else 'FAILED (ISSUES FOUND)'}")
    print("\nDataset Statistics:")
    print(json.dumps(report.stats, indent=2))

    if report.issues:
        print("\nFirst 10 Validation Issues:")
        for issue in report.issues[:10]:
            print(f"  - [Row {issue.row_number}] [{issue.issue_type}] {issue.field_name}: {issue.message} (value={issue.value})")
        if len(report.issues) > 10:
            print(f"  ... and {len(report.issues) - 10} more issues.")
        sys.exit(1)
    else:
        print("\nAll validation checks passed with 0 errors!")
        sys.exit(0)


if __name__ == "__main__":
    main()
