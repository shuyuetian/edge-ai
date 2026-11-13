"""比较 ONNX 中间张量与 ncnn 中间 blob。"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort


def main() -> None:
    parser = argparse.ArgumentParser(description="比较单个中间张量")
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ncnn", type=Path, required=True)
    parser.add_argument("--tensor", required=True)
    parser.add_argument("--window", type=int, default=60)
    parser.add_argument("--channels", type=int, default=8)
    args = parser.parse_args()

    model = onnx.load(args.onnx)
    output_names = {output.name for output in model.graph.output}
    if args.tensor not in output_names:
        value_info = onnx.ValueInfoProto()
        value_info.name = args.tensor
        model.graph.output.append(value_info)

    sample = np.fromfile(args.input, dtype=np.float32)[
        : args.window * args.channels
    ].reshape(1, args.window, args.channels)
    session = ort.InferenceSession(
        model.SerializeToString(),
        providers=["CPUExecutionProvider"],
    )
    expected = np.asarray(
        session.run([args.tensor], {"sensor_window": sample})[0],
        dtype=np.float32,
    ).reshape(-1)
    actual = np.fromfile(args.ncnn, dtype=np.float32)
    if expected.shape != actual.shape:
        raise SystemExit(
            f"张量数量不一致：ONNX={expected.shape}，ncnn={actual.shape}"
        )

    difference = np.abs(expected - actual)
    print(f"tensor={args.tensor}")
    print(f"shape={expected.shape}")
    print(f"onnx_first={expected[:8]}")
    print(f"ncnn_first={actual[:8]}")
    print(f"max_abs_error={difference.max():.9g}")
    print(f"mean_abs_error={difference.mean():.9g}")


if __name__ == "__main__":
    main()
