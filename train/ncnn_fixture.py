"""生成 ncnn 推理夹具并比较 ncnn 与 ONNX Runtime 输出。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


def classification_metrics(labels: np.ndarray, logits: np.ndarray, threshold: float) -> dict:
    predictions = logits >= threshold
    true_positive = int(((predictions == 1) & (labels == 1)).sum())
    false_positive = int(((predictions == 1) & (labels == 0)).sum())
    false_negative = int(((predictions == 0) & (labels == 1)).sum())
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = 2.0 * precision * recall / max(precision + recall, 1e-12)
    return {
        "precision": round(float(precision), 6),
        "recall": round(float(recall), 6),
        "f1": round(float(f1), 6),
        "predicted_anomalies": int(predictions.sum()),
    }


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="ncnn 推理数值夹具")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project_root / "train" / "artifacts" / "skab_windows_w60_s10.npz",
    )
    parser.add_argument(
        "--onnx",
        type=Path,
        default=project_root / "train" / "artifacts" / "anomaly_cnn.onnx",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "train" / "artifacts" / "ncnn_fixture",
    )
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument(
        "--actual",
        type=Path,
        help="C++ ncnn 推理输出的 float32 文件；提供后执行比较",
    )
    parser.add_argument("--max-error", type=float, default=None)
    parser.add_argument("--min-decision-agreement", type=float, default=0.99)
    parser.add_argument("--max-f1-drop", type=float, default=0.01)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    input_path = args.output_dir / "input.f32"
    expected_path = args.output_dir / "expected.f32"

    if not args.actual:
        import onnxruntime as ort

        data = np.load(args.dataset)
        test_windows = data["x_test"]
        count = min(args.samples, len(test_windows))
        indices = np.linspace(0, len(test_windows) - 1, count, dtype=np.int64)
        time_major_samples = test_windows[indices].astype(np.float32, copy=False)
        samples = np.ascontiguousarray(
            np.transpose(time_major_samples, (0, 2, 1))[:, :, None, :],
            dtype=np.float32,
        )
        labels = data["y_test"][indices].astype(np.int8, copy=False)

        session = ort.InferenceSession(
            str(args.onnx),
            providers=["CPUExecutionProvider"],
        )
        expected = np.asarray(
            [
                session.run(
                    None,
                    {"sensor_window": sample[None, ...]},
                )[0].reshape(-1)[0]
                for sample in samples
            ],
            dtype=np.float32,
        )

        samples.tofile(input_path)
        expected.tofile(expected_path)
        np.save(args.output_dir / "labels.npy", labels)
        metadata = {
            "count": count,
            "window_size": int(time_major_samples.shape[1]),
            "channels": int(time_major_samples.shape[2]),
            "deployment_input_shape": list(samples.shape[1:]),
            "anomaly_labels": int(labels.sum()),
            "input_path": str(input_path),
            "expected_path": str(expected_path),
            "indices": indices.tolist(),
        }
        (args.output_dir / "fixture.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        return

    metadata = json.loads(
        (args.output_dir / "fixture.json").read_text(encoding="utf-8")
    )
    expected = np.fromfile(expected_path, dtype=np.float32)
    actual = np.fromfile(args.actual, dtype=np.float32)
    if actual.shape != expected.shape:
        raise SystemExit(
            f"输出数量不一致：ncnn={actual.shape}，预期={expected.shape}"
        )
    differences = np.abs(actual - expected)
    max_error = float(differences.max())
    mean_error = float(differences.mean())
    expected_probabilities = 1.0 / (1.0 + np.exp(-expected))
    actual_probabilities = 1.0 / (1.0 + np.exp(-actual))
    probability_differences = np.abs(
        expected_probabilities - actual_probabilities
    )
    labels = np.load(args.output_dir / "labels.npy").astype(np.int8)
    threshold_report = json.loads(
        args.onnx.with_name("onnx_export_report.json").read_text(encoding="utf-8")
    )
    threshold_probability = float(
        threshold_report.get(
            "threshold_probability",
            threshold_report.get("threshold"),
        )
    )
    threshold_logit = float(
        threshold_report.get(
            "threshold_logit",
            math.log(threshold_probability / (1.0 - threshold_probability)),
        )
    )
    expected_metrics = classification_metrics(labels, expected, threshold_logit)
    actual_metrics = classification_metrics(labels, actual, threshold_logit)
    expected_predictions = expected >= threshold_logit
    actual_predictions = actual >= threshold_logit
    decision_agreement = float((expected_predictions == actual_predictions).mean())
    f1_drop = float(expected_metrics["f1"] - actual_metrics["f1"])
    max_error_passed = args.max_error is None or max_error <= args.max_error
    decision_passed = decision_agreement >= args.min_decision_agreement
    f1_passed = f1_drop <= args.max_f1_drop
    report = {
        "samples": int(len(expected)),
        "max_abs_error": max_error,
        "mean_abs_error": mean_error,
        "error_limit": args.max_error,
        "max_probability_error": float(probability_differences.max()),
        "mean_probability_error": float(probability_differences.mean()),
        "threshold_probability": threshold_probability,
        "threshold_logit": threshold_logit,
        "decision_agreement": decision_agreement,
        "min_decision_agreement": args.min_decision_agreement,
        "f1_drop": f1_drop,
        "max_f1_drop": args.max_f1_drop,
        "acceptance": {
            "max_logit_error": max_error_passed,
            "decision_agreement": decision_passed,
            "f1_drop": f1_passed,
        },
        "expected_metrics": expected_metrics,
        "actual_metrics": actual_metrics,
        "ncnn_output": str(args.actual),
    }
    report_path = args.output_dir / f"comparison_{args.actual.stem}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.max_error is not None and max_error > args.max_error:
        raise SystemExit(f"ncnn 一致性失败：最大误差 {max_error:.9g}")
    if decision_agreement < args.min_decision_agreement:
        raise SystemExit(f"决策一致率过低：{decision_agreement:.6f}")
    if f1_drop > args.max_f1_drop:
        raise SystemExit(f"F1 下降过大：{f1_drop:.6f}")


if __name__ == "__main__":
    main()
