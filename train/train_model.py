"""训练 SKAB 窗口异常检测模型。"""

from __future__ import annotations

import argparse
import copy
import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import (
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


@dataclass(frozen=True)
class Evaluation:
    threshold: float
    precision: float
    recall: float
    f1: float
    roc_auc: float
    true_negative: int
    false_positive: int
    false_negative: int
    true_positive: int


class AnomalyCNN(nn.Module):
    def __init__(self, channels: int = 8) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(channels, 16, kernel_size=(1, 5), padding=(0, 2), bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=(1, 2)),
            nn.Conv2d(16, 32, kernel_size=(1, 3), padding=(0, 1), bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=(1, 2)),
            nn.Conv2d(32, 64, kernel_size=(1, 3), padding=(0, 1), bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            # 时间轴经过两次减半后固定为 15。
            nn.AvgPool2d(kernel_size=(1, 15), stride=(1, 15)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(p=0.2),
            nn.Linear(64, 1),
        )

    def forward_raw(self, x: torch.Tensor) -> torch.Tensor:
        # 输入为 [batch, time, channels]，转成 [batch, channels, 1, time]。
        # 使用高为 1 的二维卷积，保持一维时序语义并兼容 ncnn INT8 量化器。
        x = x.transpose(1, 2).unsqueeze(2)
        return self.classifier(self.features(x))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.forward_raw(x).squeeze(1)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def score_batches(
    model: nn.Module,
    loader: DataLoader,
) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    scores: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    with torch.inference_mode():
        for features, targets in loader:
            logits = model(features)
            scores.append(torch.sigmoid(logits).cpu().numpy())
            labels.append(targets.numpy())
    return np.concatenate(scores), np.concatenate(labels)


def evaluate_at_threshold(
    labels: np.ndarray,
    scores: np.ndarray,
    threshold: float,
) -> Evaluation:
    predictions = scores >= threshold
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels,
        predictions,
        average="binary",
        zero_division=0,
    )
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    auc = roc_auc_score(labels, scores)
    return Evaluation(
        threshold=float(threshold),
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
        roc_auc=float(auc),
        true_negative=int(tn),
        false_positive=int(fp),
        false_negative=int(fn),
        true_positive=int(tp),
    )


def choose_threshold(labels: np.ndarray, scores: np.ndarray) -> Evaluation:
    candidates = np.unique(
        np.concatenate(
            [
                np.linspace(0.0, 1.0, 1001, dtype=np.float64),
                scores.astype(np.float64),
            ]
        )
    )
    evaluations = [evaluate_at_threshold(labels, scores, threshold) for threshold in candidates]
    # F1 优先；相同时选择阈值更高的结果，以减少误报。
    return max(evaluations, key=lambda item: (item.f1, item.precision, item.threshold))


def evaluation_dict(result: Evaluation) -> dict[str, float | int]:
    return {
        "threshold": result.threshold,
        "precision": round(result.precision, 6),
        "recall": round(result.recall, 6),
        "f1": round(result.f1, 6),
        "roc_auc": round(result.roc_auc, 6),
        "true_negative": result.true_negative,
        "false_positive": result.false_positive,
        "false_negative": result.false_negative,
        "true_positive": result.true_positive,
    }


def make_loader(
    x: np.ndarray,
    y: np.ndarray,
    batch_size: int,
    shuffle: bool,
) -> DataLoader:
    features = torch.from_numpy(x.astype(np.float32, copy=False))
    targets = torch.from_numpy(y.astype(np.float32, copy=False))
    return DataLoader(
        TensorDataset(features, targets),
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=0,
    )


def train(args: argparse.Namespace) -> dict[str, object]:
    set_seed(args.seed)
    torch.set_num_threads(args.threads)

    data = np.load(args.dataset)
    x_train = data["x_train"]
    y_train = data["y_train"]
    x_validation = data["x_validation"]
    y_validation = data["y_validation"]
    x_test = data["x_test"]
    y_test = data["y_test"]

    if x_train.ndim != 3 or x_validation.ndim != 3 or x_test.ndim != 3:
        raise ValueError("窗口数组必须是三维 [样本, 时间, 通道]")
    channel_count = x_train.shape[2]

    train_loader = make_loader(x_train, y_train, args.batch_size, shuffle=True)
    validation_loader = make_loader(
        x_validation, y_validation, args.batch_size, shuffle=False
    )
    test_loader = make_loader(x_test, y_test, args.batch_size, shuffle=False)

    model = AnomalyCNN(channels=channel_count)
    positive_count = int(y_train.sum())
    negative_count = len(y_train) - positive_count
    positive_weight = torch.tensor(
        [negative_count / max(positive_count, 1)], dtype=torch.float32
    )
    criterion = nn.BCEWithLogitsLoss(pos_weight=positive_weight)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.learning_rate, weight_decay=1e-4
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=3
    )

    best_state = copy.deepcopy(model.state_dict())
    best_validation_loss = float("inf")
    best_epoch = 0
    epochs_without_improvement = 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        loss_sum = 0.0
        sample_count = 0
        for features, targets in train_loader:
            optimizer.zero_grad(set_to_none=True)
            logits = model(features)
            loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.item()) * len(features)
            sample_count += len(features)

        train_loss = loss_sum / sample_count
        validation_scores, validation_labels = score_batches(
            model, validation_loader
        )
        validation_targets = torch.from_numpy(
            validation_labels.astype(np.float32, copy=False)
        )
        with torch.inference_mode():
            validation_logits = model(
                torch.from_numpy(x_validation.astype(np.float32, copy=False))
            )
            validation_loss = float(
                criterion(validation_logits, validation_targets).item()
            )
        scheduler.step(validation_loss)
        validation_result = choose_threshold(
            validation_labels, validation_scores
        )
        print(
            f"epoch={epoch:02d} train_loss={train_loss:.6f} "
            f"val_loss={validation_loss:.6f} val_f1={validation_result.f1:.4f}"
        )

        if validation_loss < best_validation_loss - 1e-6:
            best_validation_loss = validation_loss
            best_state = copy.deepcopy(model.state_dict())
            best_epoch = epoch
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(f"early_stop epoch={epoch} best_epoch={best_epoch}")
                break

    model.load_state_dict(best_state)
    validation_scores, validation_labels = score_batches(
        model, validation_loader
    )
    selected = choose_threshold(validation_labels, validation_scores)
    test_scores, test_labels = score_batches(model, test_loader)
    test_result = evaluate_at_threshold(test_labels, test_scores, selected.threshold)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = args.output_dir / "anomaly_cnn.pt"
    metrics_path = args.output_dir / "metrics.json"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "channels": channel_count,
            "window_size": int(x_train.shape[1]),
            "threshold": selected.threshold,
        },
        checkpoint_path,
    )

    metrics: dict[str, object] = {
        "seed": args.seed,
        "best_epoch": best_epoch,
        "best_validation_loss": best_validation_loss,
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "dataset_shapes": {
            "train": list(x_train.shape),
            "validation": list(x_validation.shape),
            "test": list(x_test.shape),
        },
        "validation": evaluation_dict(selected),
        "test": evaluation_dict(test_result),
        "checkpoint": str(checkpoint_path),
    }
    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return metrics


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="训练 SKAB 1D-CNN 异常检测模型")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project_root / "train" / "artifacts" / "skab_windows_w60_s10.npz",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "train" / "artifacts",
    )
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--patience", type=int, default=7)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    train(parser.parse_args())


if __name__ == "__main__":
    main()
