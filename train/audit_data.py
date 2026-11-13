"""审计 SKAB 数据并生成按实验文件隔离的数据划分。

本脚本只做数据检查，不修改原始 CSV。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SENSOR_COLUMNS = [
    "Accelerometer1RMS",
    "Accelerometer2RMS",
    "Current",
    "Pressure",
    "Temperature",
    "Thermocouple",
    "Voltage",
    "Volume Flow RateRMS",
]
LABEL_COLUMNS = ["anomaly", "changepoint"]
EXPECTED_LABELED_COLUMNS = ["datetime", *SENSOR_COLUMNS, *LABEL_COLUMNS]
EXPECTED_BASELINE_COLUMNS = ["datetime", *SENSOR_COLUMNS]

# 按实验文件隔离，避免同一异常过程同时进入训练集和测试集。
SPLIT_FILES: dict[str, list[str]] = {
    "train": [
        "anomaly-free/anomaly-free.csv",
        "other/1.csv",
        "other/2.csv",
        "other/3.csv",
        "other/4.csv",
        "other/5.csv",
        "other/6.csv",
        "other/7.csv",
        "other/8.csv",
        "other/9.csv",
        "other/10.csv",
        "valve1/0.csv",
        "valve1/1.csv",
        "valve1/2.csv",
        "valve1/3.csv",
        "valve1/4.csv",
        "valve1/5.csv",
        "valve1/6.csv",
        "valve1/7.csv",
        "valve1/8.csv",
        "valve1/9.csv",
        "valve1/10.csv",
        "valve1/11.csv",
        "valve2/0.csv",
        "valve2/1.csv",
    ],
    "validation": [
        "other/11.csv",
        "other/12.csv",
        "valve1/12.csv",
        "valve1/13.csv",
        "valve2/2.csv",
    ],
    "test": [
        "other/13.csv",
        "other/14.csv",
        "valve1/14.csv",
        "valve1/15.csv",
        "valve2/3.csv",
    ],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_file(csv_path: Path, data_root: Path) -> dict[str, Any]:
    relative_path = csv_path.relative_to(data_root).as_posix()
    frame = pd.read_csv(csv_path, sep=";")
    errors: list[str] = []
    warnings: list[str] = []

    is_baseline = relative_path == "anomaly-free/anomaly-free.csv"
    expected_columns = (
        EXPECTED_BASELINE_COLUMNS if is_baseline else EXPECTED_LABELED_COLUMNS
    )
    if list(frame.columns) != expected_columns:
        errors.append(
            "字段不符合预期："
            f"实际={list(frame.columns)}，预期={expected_columns}"
        )

    missing_sensor_cells = int(frame[SENSOR_COLUMNS].isna().sum().sum())
    if missing_sensor_cells:
        errors.append(f"传感器字段存在 {missing_sensor_cells} 个缺失值")

    non_numeric_cells = 0
    for column in SENSOR_COLUMNS:
        converted = pd.to_numeric(frame[column], errors="coerce")
        non_numeric_cells += int(converted.isna().sum() - frame[column].isna().sum())
    if non_numeric_cells:
        errors.append(f"传感器字段存在 {non_numeric_cells} 个无法解析的数值")

    timestamps = pd.to_datetime(frame["datetime"], errors="coerce")
    invalid_timestamps = int(timestamps.isna().sum())
    if invalid_timestamps:
        errors.append(f"存在 {invalid_timestamps} 个无效时间戳")
    monotonic = bool(timestamps.is_monotonic_increasing)
    if not monotonic:
        errors.append("时间戳不是严格递增")
    duplicate_timestamps = int(timestamps.duplicated().sum())
    if duplicate_timestamps:
        errors.append(f"存在 {duplicate_timestamps} 个重复时间戳")

    gaps = timestamps.diff().dropna().dt.total_seconds()
    unexpected_gaps = int((gaps != 1.0).sum())
    if unexpected_gaps:
        warnings.append(f"存在 {unexpected_gaps} 个非 1 秒间隔")

    anomaly_count = 0
    changepoint_count = 0
    if not is_baseline:
        for column in LABEL_COLUMNS:
            values = set(pd.to_numeric(frame[column], errors="coerce").dropna().astype(int))
            if not values.issubset({0, 1}):
                errors.append(f"{column} 含非法标签值：{sorted(values)}")
        anomaly_count = int(frame["anomaly"].sum())
        changepoint_count = int(frame["changepoint"].sum())

    return {
        "file": relative_path,
        "sha256": sha256_file(csv_path),
        "rows": len(frame),
        "columns": list(frame.columns),
        "is_baseline": is_baseline,
        "first_timestamp": timestamps.iloc[0].isoformat() if len(timestamps) else None,
        "last_timestamp": timestamps.iloc[-1].isoformat() if len(timestamps) else None,
        "monotonic": monotonic,
        "duplicate_timestamps": duplicate_timestamps,
        "invalid_timestamps": invalid_timestamps,
        "unexpected_time_gaps": unexpected_gaps,
        "min_gap_seconds": float(gaps.min()) if not gaps.empty else None,
        "max_gap_seconds": float(gaps.max()) if not gaps.empty else None,
        "missing_sensor_cells": missing_sensor_cells,
        "non_numeric_sensor_cells": non_numeric_cells,
        "anomaly_count": anomaly_count,
        "changepoint_count": changepoint_count,
        "errors": errors,
        "warnings": warnings,
    }


def validate_split(files: list[str], data_root: Path) -> None:
    expected = {path.relative_to(data_root).as_posix() for path in data_root.rglob("*.csv")}
    assigned = [item for group in SPLIT_FILES.values() for item in group]
    assigned_set = set(assigned)

    if len(assigned) != len(assigned_set):
        raise ValueError("数据划分中存在重复文件")
    if assigned_set != expected:
        missing = sorted(expected - assigned_set)
        extra = sorted(assigned_set - expected)
        raise ValueError(f"数据划分未覆盖全部文件。缺少={missing}，多余={extra}")
    if len(files) != len(assigned_set):
        raise ValueError(
            f"扫描到 {len(files)} 个 CSV，但划分包含 {len(assigned_set)} 个文件"
        )


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="审计 SKAB 数据")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=project_root / "data" / "skab" / "data",
        help="包含 SKAB CSV 的 data 目录",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "train" / "artifacts",
        help="审计报告和划分文件输出目录",
    )
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    files = sorted(path for path in data_root.rglob("*.csv"))
    if not files:
        raise FileNotFoundError(f"未找到 CSV：{data_root}")

    validate_split(files, data_root)
    reports = [audit_file(path, data_root) for path in files]
    error_files = [report for report in reports if report["errors"]]
    warning_files = [report for report in reports if report["warnings"]]

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_root": str(data_root),
        "file_count": len(reports),
        "total_rows": int(sum(item["rows"] for item in reports)),
        "baseline_rows": int(
            sum(item["rows"] for item in reports if item["is_baseline"])
        ),
        "labeled_rows": int(
            sum(item["rows"] for item in reports if not item["is_baseline"])
        ),
        "anomaly_count": int(sum(item["anomaly_count"] for item in reports)),
        "changepoint_count": int(
            sum(item["changepoint_count"] for item in reports)
        ),
        "missing_sensor_cells": int(
            sum(item["missing_sensor_cells"] for item in reports)
        ),
        "files_with_errors": len(error_files),
        "files_with_warnings": len(warning_files),
        "files": reports,
    }
    split = {
        "strategy": "file-level experiment isolation",
        "seedless": True,
        "files": SPLIT_FILES,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = args.output_dir / "data_audit.json"
    split_path = args.output_dir / "skab_file_split.json"
    audit_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    split_path.write_text(
        json.dumps(split, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps({
        "files": report["file_count"],
        "rows": report["total_rows"],
        "baseline_rows": report["baseline_rows"],
        "labeled_rows": report["labeled_rows"],
        "anomaly_count": report["anomaly_count"],
        "changepoint_count": report["changepoint_count"],
        "missing_sensor_cells": report["missing_sensor_cells"],
        "files_with_errors": report["files_with_errors"],
        "files_with_warnings": report["files_with_warnings"],
        "audit_report": str(audit_path),
        "split_file": str(split_path),
    }, ensure_ascii=False, indent=2))

    if error_files:
        raise SystemExit("数据审计失败，请查看报告中的 errors")


if __name__ == "__main__":
    main()
