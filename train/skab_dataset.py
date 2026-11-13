"""SKAB 多变量时间序列窗口构建工具。"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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


@dataclass(frozen=True)
class WindowSet:
    x: np.ndarray
    anomaly: np.ndarray
    changepoint: np.ndarray
    file_ids: np.ndarray
    end_times: np.ndarray


def load_skab_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep=";")
    missing = [column for column in ["datetime", *SENSOR_COLUMNS] if column not in frame]
    if missing:
        raise ValueError(f"{path} 缺少字段：{missing}")

    frame = frame.copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="raise")
    frame = frame.sort_values("datetime").reset_index(drop=True)
    if frame["datetime"].duplicated().any():
        raise ValueError(f"{path} 存在重复时间戳")
    for column in SENSOR_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    for column in LABEL_COLUMNS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="raise").astype("int8")
    return frame


def split_contiguous_segments(
    frame: pd.DataFrame,
    max_gap_seconds: float = 2.0,
) -> list[pd.DataFrame]:
    """按时间间隔切段，绝不跨采集停顿组成窗口。"""
    gaps = frame["datetime"].diff().dt.total_seconds()
    segment_ids = (gaps.gt(max_gap_seconds) | gaps.isna()).cumsum()
    return [
        segment.reset_index(drop=True)
        for _, segment in frame.groupby(segment_ids, sort=False)
    ]


def resample_segment(segment: pd.DataFrame) -> pd.DataFrame:
    """补齐允许范围内的 1 秒间隔，并保留原始标签。"""
    indexed = segment.set_index("datetime")
    full_index = pd.date_range(
        start=indexed.index.min(),
        end=indexed.index.max(),
        freq="1s",
    )
    result = indexed.reindex(full_index)
    result[SENSOR_COLUMNS] = (
        result[SENSOR_COLUMNS]
        .astype("float32")
        .interpolate(method="linear", limit=1, limit_direction="both")
    )
    for column in LABEL_COLUMNS:
        if column in result:
            result[column] = result[column].ffill().bfill().fillna(0).astype("int8")
    return result


def prepare_segments(
    frame: pd.DataFrame,
    max_gap_seconds: float = 2.0,
) -> list[pd.DataFrame]:
    segments = split_contiguous_segments(frame, max_gap_seconds=max_gap_seconds)
    return [resample_segment(segment) for segment in segments]


def build_windows(
    segments: Iterable[pd.DataFrame],
    window_size: int = 60,
    stride: int = 10,
    file_id: int = 0,
) -> WindowSet:
    if window_size < 2:
        raise ValueError("window_size 必须至少为 2")
    if stride < 1:
        raise ValueError("stride 必须至少为 1")

    x_values: list[np.ndarray] = []
    anomaly_values: list[int] = []
    changepoint_values: list[int] = []
    end_times: list[str] = []

    for segment in segments:
        if len(segment) < window_size:
            continue
        sensor_values = segment[SENSOR_COLUMNS].to_numpy(dtype=np.float32)
        if not np.isfinite(sensor_values).all():
            raise ValueError("切段后仍存在缺失或无穷传感器值")

        anomaly = (
            segment["anomaly"].to_numpy(dtype=np.int8)
            if "anomaly" in segment
            else np.zeros(len(segment), dtype=np.int8)
        )
        changepoint = (
            segment["changepoint"].to_numpy(dtype=np.int8)
            if "changepoint" in segment
            else np.zeros(len(segment), dtype=np.int8)
        )

        for end in range(window_size, len(segment) + 1, stride):
            start = end - window_size
            x_values.append(sensor_values[start:end])
            anomaly_values.append(int(anomaly[end - 1]))
            changepoint_values.append(int(changepoint[end - 1]))
            end_times.append(segment.index[end - 1].isoformat())

    if not x_values:
        return WindowSet(
            x=np.empty((0, window_size, len(SENSOR_COLUMNS)), dtype=np.float32),
            anomaly=np.empty((0,), dtype=np.int8),
            changepoint=np.empty((0,), dtype=np.int8),
            file_ids=np.empty((0,), dtype=np.int16),
            end_times=np.empty((0,), dtype=str),
        )

    return WindowSet(
        x=np.stack(x_values).astype(np.float32, copy=False),
        anomaly=np.asarray(anomaly_values, dtype=np.int8),
        changepoint=np.asarray(changepoint_values, dtype=np.int8),
        file_ids=np.full(len(x_values), file_id, dtype=np.int16),
        end_times=np.asarray(end_times, dtype=str),
    )


def concatenate_window_sets(window_sets: list[WindowSet], window_size: int) -> WindowSet:
    if not window_sets:
        raise ValueError("没有可合并的窗口")
    return WindowSet(
        x=np.concatenate([item.x for item in window_sets], axis=0),
        anomaly=np.concatenate([item.anomaly for item in window_sets], axis=0),
        changepoint=np.concatenate([item.changepoint for item in window_sets], axis=0),
        file_ids=np.concatenate([item.file_ids for item in window_sets], axis=0),
        end_times=np.concatenate([item.end_times for item in window_sets], axis=0),
    )


def compute_normalization(
    baseline_segments: Iterable[pd.DataFrame],
) -> tuple[np.ndarray, np.ndarray]:
    values = np.concatenate(
        [segment[SENSOR_COLUMNS].to_numpy(dtype=np.float64) for segment in baseline_segments],
        axis=0,
    )
    mean = values.mean(axis=0)
    std = values.std(axis=0)
    std[std < 1e-8] = 1.0
    return mean.astype(np.float32), std.astype(np.float32)


def normalize_windows(
    windows: WindowSet,
    mean: np.ndarray,
    std: np.ndarray,
) -> WindowSet:
    return WindowSet(
        x=((windows.x - mean[None, None, :]) / std[None, None, :]).astype(
            np.float32, copy=False
        ),
        anomaly=windows.anomaly,
        changepoint=windows.changepoint,
        file_ids=windows.file_ids,
        end_times=windows.end_times,
    )


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="生成 SKAB 固定长度窗口")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=project_root / "data" / "skab" / "data",
    )
    parser.add_argument(
        "--split-file",
        type=Path,
        default=project_root / "train" / "artifacts" / "skab_file_split.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "train" / "artifacts" / "skab_windows_w60_s10.npz",
    )
    parser.add_argument("--window-size", type=int, default=60)
    parser.add_argument("--stride", type=int, default=10)
    parser.add_argument("--max-gap-seconds", type=float, default=2.0)
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    split_config = json.loads(args.split_file.read_text(encoding="utf-8"))
    split_files: dict[str, list[str]] = split_config["files"]

    frames: dict[str, pd.DataFrame] = {}
    segments: dict[str, list[pd.DataFrame]] = {}
    all_files = sorted({name for names in split_files.values() for name in names})
    for file_id, relative_name in enumerate(all_files):
        frame = load_skab_csv(data_root / relative_name)
        frames[relative_name] = frame
        segments[relative_name] = prepare_segments(
            frame, max_gap_seconds=args.max_gap_seconds
        )

    normal_name = "anomaly-free/anomaly-free.csv"
    if normal_name not in split_files["train"]:
        raise ValueError("正常基线文件必须位于训练集")
    mean, std = compute_normalization(segments[normal_name])

    split_windows: dict[str, WindowSet] = {}
    for split_name, names in split_files.items():
        window_sets = [
            build_windows(
                segments[relative_name],
                window_size=args.window_size,
                stride=args.stride,
                file_id=all_files.index(relative_name),
            )
            for relative_name in names
        ]
        window_sets = [item for item in window_sets if len(item.x)]
        combined = concatenate_window_sets(window_sets, args.window_size)
        split_windows[split_name] = normalize_windows(combined, mean, std)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        x_train=split_windows["train"].x,
        y_train=split_windows["train"].anomaly,
        cp_train=split_windows["train"].changepoint,
        file_ids_train=split_windows["train"].file_ids,
        end_times_train=split_windows["train"].end_times,
        x_validation=split_windows["validation"].x,
        y_validation=split_windows["validation"].anomaly,
        cp_validation=split_windows["validation"].changepoint,
        file_ids_validation=split_windows["validation"].file_ids,
        end_times_validation=split_windows["validation"].end_times,
        x_test=split_windows["test"].x,
        y_test=split_windows["test"].anomaly,
        cp_test=split_windows["test"].changepoint,
        file_ids_test=split_windows["test"].file_ids,
        end_times_test=split_windows["test"].end_times,
    )

    metadata = {
        "window_size": args.window_size,
        "stride": args.stride,
        "max_gap_seconds": args.max_gap_seconds,
        "sensor_columns": SENSOR_COLUMNS,
        "files": all_files,
        "normalization": {
            "source_file": normal_name,
            "mean": mean.tolist(),
            "std": std.tolist(),
        },
    }
    metadata_path = args.output.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = {
        split_name: {
            "shape": list(windows.x.shape),
            "anomaly_count": int(windows.anomaly.sum()),
            "anomaly_ratio": round(float(windows.anomaly.mean()), 4),
            "files_used": len(split_files[split_name]),
        }
        for split_name, windows in split_windows.items()
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"output={args.output}")
    print(f"metadata={metadata_path}")


if __name__ == "__main__":
    main()
