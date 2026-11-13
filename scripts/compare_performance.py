#!/usr/bin/env python3
"""比较两份板端性能分析结果并执行回归阈值检查。"""

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Dict, List, Optional


REPORT_METRICS = (
    ("mean_ms", "均值"),
    ("p50_ms", "P50"),
    ("p95_ms", "P95"),
    ("p99_ms", "P99"),
    ("peak_rss_kib", "峰值 RSS"),
)
FAIL_METRICS = {
    "mean_ms": "max_mean_regression_pct",
    "p95_ms": "max_p95_regression_pct",
    "peak_rss_kib": "max_rss_regression_pct",
}


class ComparisonError(RuntimeError):
    pass


def load_analysis(path: Path) -> Dict[str, object]:
    if not path.is_file():
        raise ComparisonError("分析文件不存在：{}".format(path))
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ComparisonError("无法读取分析文件 {}：{}".format(path, error)) from error
    if not isinstance(data, dict):
        raise ComparisonError("分析 JSON 顶层必须是对象：{}".format(path))
    return data


def require_mapping(data: Dict[str, object], key: str, source: str):
    value = data.get(key)
    if not isinstance(value, dict):
        raise ComparisonError("{} 缺少对象字段 {}".format(source, key))
    return value


def require_metric(data: Dict[str, object], metric: str, source: str) -> float:
    metrics = require_mapping(data, "median_metrics", source)
    value = metrics.get(metric)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ComparisonError("{} 的 {} 不是有限数字".format(source, metric))
    if float(value) <= 0.0:
        raise ComparisonError("{} 的 {} 必须大于 0".format(source, metric))
    return float(value)


def environment_identity(data: Dict[str, object], source: str) -> Dict[str, object]:
    environment = require_mapping(data, "environment_before", source)
    return {
        "board_model": environment.get("board_model", "unavailable"),
        "cpu_model": environment.get("cpu_model", "unavailable"),
        "os": environment.get("os", "unavailable"),
        "governors": environment.get("governors", []),
    }


def validate_comparison(
    baseline: Dict[str, object],
    candidate: Dict[str, object],
    allow_qemu: bool,
    allow_environment_change: bool,
) -> List[str]:
    warnings = []
    for label, data in (("基线", baseline), ("候选", candidate)):
        if not allow_qemu and (
            data.get("qemu", "unknown") != "not_used"
            or data.get("host_arch") != "aarch64"
        ):
            raise ComparisonError(
                "{}不是 aarch64 原生结果；QEMU 比较必须显式使用 "
                "--allow-qemu".format(label)
            )
    if allow_qemu and any(
        data.get("qemu", "unknown") != "not_used"
        or data.get("host_arch") != "aarch64"
        for data in (baseline, candidate)
    ):
        warnings.append("比较包含 QEMU 结果，只能用于流程验证，不能作为真机结论。")

    for field in ("rounds", "iterations", "warmup"):
        if baseline.get(field) != candidate.get(field):
            raise ComparisonError(
                "{}不一致：baseline={} candidate={}".format(
                    field, baseline.get(field), candidate.get(field)
                )
            )

    baseline_environment = environment_identity(baseline, "基线")
    candidate_environment = environment_identity(candidate, "候选")
    changed = []
    for field in ("board_model", "cpu_model", "os", "governors"):
        if baseline_environment[field] != candidate_environment[field]:
            changed.append(
                "{}: {!r} -> {!r}".format(
                    field,
                    baseline_environment[field],
                    candidate_environment[field],
                )
            )
    if changed and not allow_environment_change:
        raise ComparisonError(
            "运行环境不一致；如确认是有意换环境，请加 "
            "--allow-environment-change：\n  " + "\n  ".join(changed)
        )
    if changed:
        warnings.append("运行环境发生变化：" + "; ".join(changed))
    return warnings


def compare_metrics(
    baseline: Dict[str, object],
    candidate: Dict[str, object],
    thresholds: Dict[str, float],
) -> List[Dict[str, object]]:
    comparisons = []
    for metric, label in REPORT_METRICS:
        baseline_value = require_metric(baseline, metric, "基线")
        candidate_value = require_metric(candidate, metric, "候选")
        change_pct = (candidate_value - baseline_value) / baseline_value * 100.0
        threshold_key = FAIL_METRICS.get(metric)
        threshold = thresholds[threshold_key] if threshold_key else None
        regressed = threshold is not None and change_pct > threshold
        comparisons.append(
            {
                "metric": metric,
                "label": label,
                "baseline": baseline_value,
                "candidate": candidate_value,
                "change_pct": change_pct,
                "threshold_pct": threshold,
                "regressed": regressed,
            }
        )
    return comparisons


def render_markdown(
    baseline_path: Path,
    candidate_path: Path,
    baseline: Dict[str, object],
    candidate: Dict[str, object],
    comparisons: List[Dict[str, object]],
    warnings: List[str],
) -> str:
    lines = [
        "# 性能回归比较",
        "",
        "- 基线：`{}`（run `{}`）".format(
            baseline_path.name, baseline.get("run_id", "unknown")
        ),
        "- 候选：`{}`（run `{}`）".format(
            candidate_path.name, candidate.get("run_id", "unknown")
        ),
        "",
        "| 指标 | 基线 | 候选 | 变化 | 阈值 | 结果 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for item in comparisons:
        if item["metric"].endswith("_ms"):
            baseline_text = "{:.6f} ms".format(item["baseline"])
            candidate_text = "{:.6f} ms".format(item["candidate"])
        else:
            baseline_text = "{:.0f} KiB".format(item["baseline"])
            candidate_text = "{:.0f} KiB".format(item["candidate"])
        threshold = item["threshold_pct"]
        threshold_text = (
            "{:.1f}%".format(threshold) if threshold is not None else "仅报告"
        )
        status = "FAIL" if item["regressed"] else "PASS"
        lines.append(
            "| {} | {} | {} | {:+.2f}% | {} | {} |".format(
                item["label"],
                baseline_text,
                candidate_text,
                item["change_pct"],
                threshold_text,
                status,
            )
        )
    if warnings:
        lines.extend(["", "## 警告", ""])
        lines.extend("- {}".format(warning) for warning in warnings)
    return "\n".join(lines) + "\n"


def parse_args():
    parser = argparse.ArgumentParser(
        description="比较两份 analysis.json 并检查性能回归"
    )
    parser.add_argument("baseline", type=Path, help="基线 analysis.json")
    parser.add_argument("candidate", type=Path, help="候选 analysis.json")
    parser.add_argument(
        "--max-mean-regression-pct",
        type=float,
        default=10.0,
        help="均值最大允许回退百分比，默认 10",
    )
    parser.add_argument(
        "--max-p95-regression-pct",
        type=float,
        default=10.0,
        help="P95 最大允许回退百分比，默认 10",
    )
    parser.add_argument(
        "--max-rss-regression-pct",
        type=float,
        default=10.0,
        help="峰值 RSS 最大允许回退百分比，默认 10",
    )
    parser.add_argument(
        "--allow-qemu",
        action="store_true",
        help="允许 QEMU 结果参与比较，仅用于验证流程",
    )
    parser.add_argument(
        "--allow-environment-change",
        action="store_true",
        help="允许板型、CPU、系统或调频策略不同",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="输出目录，默认放在候选文件旁边",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    thresholds = {
        "max_mean_regression_pct": args.max_mean_regression_pct,
        "max_p95_regression_pct": args.max_p95_regression_pct,
        "max_rss_regression_pct": args.max_rss_regression_pct,
    }
    if any(value < 0.0 for value in thresholds.values()):
        raise ComparisonError("回归阈值不能小于 0")

    baseline_path = args.baseline.resolve()
    candidate_path = args.candidate.resolve()
    baseline = load_analysis(baseline_path)
    candidate = load_analysis(candidate_path)
    warnings = validate_comparison(
        baseline,
        candidate,
        args.allow_qemu,
        args.allow_environment_change,
    )
    comparisons = compare_metrics(baseline, candidate, thresholds)

    output_dir = args.output_dir or candidate_path.parent / (
        candidate_path.stem + "_comparison"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "baseline": str(baseline_path),
        "candidate": str(candidate_path),
        "thresholds": thresholds,
        "warnings": warnings,
        "comparisons": comparisons,
        "failed": any(item["regressed"] for item in comparisons),
    }
    with (output_dir / "comparison.json").open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    markdown = render_markdown(
        baseline_path,
        candidate_path,
        baseline,
        candidate,
        comparisons,
        warnings,
    )
    (output_dir / "comparison.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print("比较结果已写入：{}".format(output_dir))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ComparisonError as error:
        print("比较失败：{}".format(error), file=sys.stderr)
        sys.exit(2)
