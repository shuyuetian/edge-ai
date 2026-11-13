"""导出 ONNX 并验证 PyTorch 与 ONNX Runtime 输出一致性。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from train_model import AnomalyCNN


class ExportAnomalyCNN(torch.nn.Module):
    """部署输入固定为 [batch, channels, 1, time]。"""

    def __init__(self, model: AnomalyCNN) -> None:
        super().__init__()
        self.model = model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model.classifier(self.model.features(x))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_with_compatible_api(
    model: torch.nn.Module,
    dummy_input: torch.Tensor,
    output_path: Path,
    opset_version: int,
) -> None:
    common = {
        "input_names": ["sensor_window"],
        "output_names": ["anomaly_logit"],
        "opset_version": opset_version,
        "do_constant_folding": True,
        "export_params": True,
    }
    try:
        torch.onnx.export(
            model,
            dummy_input,
            output_path,
            dynamo=False,
            **common,
        )
    except TypeError:
        torch.onnx.export(model, dummy_input, output_path, **common)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="导出并验证异常检测 ONNX 模型")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=project_root / "train" / "artifacts" / "anomaly_cnn.pt",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project_root / "train" / "artifacts" / "skab_windows_w60_s10.npz",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "train" / "artifacts" / "anomaly_cnn.onnx",
    )
    parser.add_argument("--opset", type=int, default=13)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--max-error", type=float, default=1e-4)
    args = parser.parse_args()

    checkpoint = torch.load(
        args.checkpoint,
        map_location="cpu",
        weights_only=True,
    )
    model = AnomalyCNN(channels=int(checkpoint["channels"]))
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    export_model = ExportAnomalyCNN(model)
    export_model.eval()

    data = np.load(args.dataset)
    test_windows = data["x_test"]
    sample_count = min(args.samples, len(test_windows))
    indices = np.linspace(0, len(test_windows) - 1, sample_count, dtype=np.int64)
    selected = test_windows[indices].astype(np.float32, copy=False)

    export_inputs = np.transpose(selected, (0, 2, 1))[:, :, None, :]
    export_inputs = np.ascontiguousarray(export_inputs, dtype=np.float32)
    dummy_input = torch.from_numpy(export_inputs[0:1])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    export_with_compatible_api(export_model, dummy_input, args.output, args.opset)

    exported = onnx.load(args.output)
    onnx.checker.check_model(exported)

    torch_outputs: list[np.ndarray] = []
    with torch.inference_mode():
        for sample in export_inputs:
            tensor = torch.from_numpy(sample[None, ...])
            torch_outputs.append(export_model(tensor).numpy().reshape(-1)[0])
    torch_output = np.asarray(torch_outputs, dtype=np.float32)

    session = ort.InferenceSession(
        str(args.output),
        providers=["CPUExecutionProvider"],
    )
    onnx_outputs: list[np.ndarray] = []
    for sample in export_inputs:
        output = session.run(
            None,
            {"sensor_window": sample[None, ...].astype(np.float32, copy=False)},
        )[0]
        onnx_outputs.append(np.asarray(output).reshape(-1)[0])
    onnx_output = np.asarray(onnx_outputs, dtype=np.float32)

    differences = np.abs(torch_output - onnx_output)
    max_error = float(differences.max())
    mean_error = float(differences.mean())
    if max_error > args.max_error:
        raise SystemExit(
            f"ONNX 一致性验证失败：最大误差 {max_error:.9g} > {args.max_error}"
        )

    model_io = exported.graph.input[0]
    input_shape = [
        dimension.dim_value for dimension in model_io.type.tensor_type.shape.dim
    ]
    model_output = exported.graph.output[0]
    output_shape = [
        dimension.dim_value
        for dimension in model_output.type.tensor_type.shape.dim
    ]
    report = {
        "onnx_path": str(args.output),
        "onnx_sha256": sha256_file(args.output),
        "onnx_size_bytes": args.output.stat().st_size,
        "opset": args.opset,
        "input_name": "sensor_window",
        "input_shape": input_shape,
        "output_name": "anomaly_logit",
        "output_shape": output_shape,
        "comparison_samples": sample_count,
        "max_abs_error": max_error,
        "mean_abs_error": mean_error,
        "error_limit": args.max_error,
        "torch_version": torch.__version__,
        "onnx_version": onnx.__version__,
        "onnxruntime_version": ort.__version__,
        "threshold_probability": float(checkpoint["threshold"]),
        "threshold_logit": math.log(
            float(checkpoint["threshold"])
            / (1.0 - float(checkpoint["threshold"]))
        ),
    }
    report_path = args.output.with_name("onnx_export_report.json")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
