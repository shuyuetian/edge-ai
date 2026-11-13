"""生成 C++ AnomalyDetector 的配置和端到端测试夹具。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="生成 C++ 推理配置和夹具")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project_root / "train" / "artifacts" / "skab_windows_w60_s10.npz",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=project_root / "train" / "artifacts" / "skab_windows_w60_s10.json",
    )
    parser.add_argument(
        "--onnx-report",
        type=Path,
        default=project_root / "train" / "artifacts" / "onnx_export_report.json",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=project_root / "train" / "artifacts" / "ncnn_fixture",
    )
    parser.add_argument(
        "--config-output",
        type=Path,
        default=project_root / "inference" / "model_config.txt",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "train" / "artifacts" / "detector_fixture",
    )
    args = parser.parse_args()

    dataset = np.load(args.dataset)
    normalized = dataset["x_test"].astype(np.float32, copy=False)
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    mean = np.asarray(metadata["normalization"]["mean"], dtype=np.float32)
    std = np.asarray(metadata["normalization"]["std"], dtype=np.float32)
    if mean.shape != (8,) or std.shape != (8,):
        raise SystemExit("标准化参数必须包含 8 个通道")

    raw = np.ascontiguousarray(normalized * std + mean, dtype=np.float32)
    onnx_report = json.loads(args.onnx_report.read_text(encoding="utf-8"))
    threshold_probability = float(
        onnx_report.get(
            "threshold_probability",
            onnx_report["threshold"],
        )
    )
    threshold_logit = float(
        onnx_report.get(
            "threshold_logit",
            math.log(threshold_probability / (1.0 - threshold_probability)),
        )
    )

    expected_logits = np.fromfile(
        args.fixture_dir / "expected.f32", dtype=np.float32
    )
    if len(expected_logits) != len(raw):
        raise SystemExit(
            f"夹具数量不一致：窗口={len(raw)}，期望输出={len(expected_logits)}"
        )
    labels = np.load(args.fixture_dir / "labels.npy").astype(np.int8, copy=False)
    if len(labels) != len(raw):
        raise SystemExit("标签数量和测试窗口数量不一致")
    expected_probability = (
        1.0 / (1.0 + np.exp(-expected_logits))
    ).astype(np.float32)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = args.output_dir / "raw_input.f32"
    expected_path = args.output_dir / "expected_probability.f32"
    labels_path = args.output_dir / "labels.i8"
    raw.tofile(raw_path)
    expected_probability.tofile(expected_path)
    labels.tofile(labels_path)

    mean_text = ",".join(f"{value:.17g}" for value in mean)
    std_text = ",".join(f"{value:.17g}" for value in std)
    args.config_output.parent.mkdir(parents=True, exist_ok=True)
    args.config_output.write_text(
        "\n".join(
            [
                "window_size=60",
                "channels=8",
                "threads=4",
                f"threshold_probability={threshold_probability:.17g}",
                f"threshold_logit={threshold_logit:.17g}",
                f"mean={mean_text}",
                f"std={std_text}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    summary = {
        "samples": int(len(raw)),
        "window_size": 60,
        "channels": 8,
        "raw_input": str(raw_path),
        "expected_probability": str(expected_path),
        "labels": str(labels_path),
        "config": str(args.config_output),
        "threshold_probability": threshold_probability,
        "threshold_logit": threshold_logit,
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
