"""从训练集的正常窗口生成 ncnn INT8 校准数据。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="生成 ncnn INT8 校准集")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project_root / "train" / "artifacts" / "skab_windows_w60_s10.npz",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "train" / "artifacts" / "calibration_npy",
    )
    parser.add_argument("--max-samples", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    data = np.load(args.dataset)
    train_windows = data["x_train"].astype(np.float32, copy=False)
    train_labels = data["y_train"]
    normal_indices = np.flatnonzero(train_labels == 0)
    if len(normal_indices) == 0:
        raise SystemExit("训练集中没有正常窗口")

    rng = np.random.default_rng(args.seed)
    if len(normal_indices) > args.max_samples:
        selected_indices = np.sort(
            rng.choice(normal_indices, size=args.max_samples, replace=False)
        )
    else:
        selected_indices = normal_indices

    args.output_dir.mkdir(parents=True, exist_ok=True)
    list_path = args.output_dir / "calibration_list.txt"
    list_lines: list[str] = []
    for output_index, source_index in enumerate(selected_indices):
        filename = f"{output_index:06d}.npy"
        output_path = args.output_dir / filename
        # ncnn2table 的 shape=[60,1,8] 对应 npy 的 [8,1,60] 数据布局。
        calibration_sample = np.ascontiguousarray(
            train_windows[source_index].T.reshape(8, 1, 60),
            dtype=np.float32,
        )
        np.save(output_path, calibration_sample)
        list_lines.append(f"calibration_npy/{filename}")
    list_path.write_text("\n".join(list_lines) + "\n", encoding="utf-8")

    metadata = {
        "source_dataset": str(args.dataset),
        "selection": "training windows with anomaly label 0 only",
        "available_normal_windows": int(len(normal_indices)),
        "selected_samples": int(len(selected_indices)),
        "training_window_shape": list(train_windows.shape[1:]),
        "calibration_npy_shape": [8, 1, 60],
        "ncnn_shape_argument": "[60,1,8]",
        "seed": args.seed,
        "list_path": str(list_path),
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
