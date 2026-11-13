#!/usr/bin/env python3
"""校验并汇总 Orange Pi 3B 板端验收结果。"""

import argparse
import csv
import io
import json
import math
from pathlib import Path
import re
import statistics
import sys
import tarfile
from typing import Dict, List, Optional, Tuple


MAX_TEXT_FILE_BYTES = 10 * 1024 * 1024
BENCHMARK_KEYS = (
    "mean_ms",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "min_ms",
    "max_ms",
    "peak_rss_kib",
)


class ResultError(RuntimeError):
    pass


class TextSource:
    def __init__(self):
        self._tar = None
        self._root = None
        self._members = {}

    @classmethod
    def from_archive(cls, path: Path):
        source = cls()
        source._tar = tarfile.open(path, "r:*")
        for member in source._tar.getmembers():
            if member.isfile():
                source._members[member.name] = member
        source._find_run_prefix()
        return source

    @classmethod
    def from_directory(cls, path: Path):
        source = cls()
        source._root = path
        source._find_run_prefix()
        return source

    def _find_run_prefix(self):
        names = []
        if self._tar is not None:
            names = list(self._members)
        else:
            names = [
                str(path.relative_to(self._root))
                for path in self._root.rglob("config.txt")
                if path.is_file()
            ]
        candidates = [name for name in names if name.endswith("/config.txt")]
        if len(candidates) != 1:
            raise ResultError(
                "结果中应恰好包含一个 config.txt，实际找到 {} 个".format(
                    len(candidates)
                )
            )
        self.prefix = candidates[0][: -len("config.txt")]

    def read_text(self, relative_path: str) -> str:
        member_name = self.prefix + relative_path
        if self._tar is not None:
            member = self._members.get(member_name)
            if member is None:
                raise ResultError("结果缺少文件：{}".format(relative_path))
            if member.size > MAX_TEXT_FILE_BYTES:
                raise ResultError("结果文本文件异常过大：{}".format(relative_path))
            stream = self._tar.extractfile(member)
            if stream is None:
                raise ResultError("无法读取结果文件：{}".format(relative_path))
            return stream.read().decode("utf-8")

        path = self._root / member_name
        if not path.is_file():
            raise ResultError("结果缺少文件：{}".format(relative_path))
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            raise ResultError("结果文本文件异常过大：{}".format(relative_path))
        return path.read_text(encoding="utf-8")

    def list_benchmark_rounds(self) -> List[str]:
        pattern = re.compile(r"^" + re.escape(self.prefix) +
                             r"benchmark_round_(\d+)\.txt$")
        rounds = []
        names = self._members if self._tar is not None else [
            str(path.relative_to(self._root))
            for path in self._root.rglob("benchmark_round_*.txt")
        ]
        for name in names:
            match = pattern.match(name)
            if match:
                rounds.append(name)
        return sorted(rounds)

    def close(self):
        if self._tar is not None:
            self._tar.close()


def parse_key_values(text: str) -> Dict[str, str]:
    values = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def parse_verification(text: str) -> Dict[str, str]:
    values = parse_key_values(text)
    for key in (
        "expected_precision",
        "expected_recall",
        "expected_f1",
        "actual_precision",
        "actual_recall",
        "actual_f1",
    ):
        match = re.search(r"\b" + re.escape(key) + r"=([0-9.eE+-]+)", text)
        if match:
            values[key] = match.group(1)
    return values


def parse_section(text: str, section_name: str) -> str:
    pattern = re.compile(
        r"===== " + re.escape(section_name) +
        r" =====\n(.*?)(?=\n===== |\Z)",
        re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def parse_environment(text: str) -> Dict[str, object]:
    model = parse_section(text, "开发板型号")
    os_section = parse_section(text, "操作系统")
    cpu_section = parse_section(text, "CPU")
    memory_section = parse_section(text, "内存")
    frequency_section = parse_section(text, "CPU 频率策略")

    os_values = {}
    for line in os_section.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            os_values[key] = value.strip('"')

    cpu_model = ""
    for line in cpu_section.splitlines():
        if line.startswith("Model name:") or line.startswith("Hardware:"):
            cpu_model = line.split(":", 1)[1].strip()
            break

    memory_total = ""
    for line in memory_section.splitlines():
        if line.startswith("Mem:"):
            fields = line.split()
            if len(fields) > 1:
                memory_total = fields[1]
            break

    governors = sorted(set(
        re.findall(r"(?:^|\s)scaling_governor=([^\s]+)", frequency_section)
    ))
    current_frequencies = [
        int(value)
        for value in re.findall(r"\bscaling_cur_freq=(\d+)", frequency_section)
    ]
    temperatures = [
        int(value) / 1000.0
        for value in re.findall(r"\btemp_millidegree_c=(\d+)", text)
    ]

    return {
        "board_model": model or "unavailable",
        "os": os_values.get("PRETTY_NAME", "unavailable"),
        "uname": parse_section(text, "时间与主机").splitlines()[2]
        if len(parse_section(text, "时间与主机").splitlines()) >= 3
        else "unavailable",
        "cpu_model": cpu_model or "unavailable",
        "memory_total": memory_total or "unavailable",
        "governors": governors,
        "current_frequency_mhz": {
            "min": min(current_frequencies) / 1000.0
            if current_frequencies
            else None,
            "max": max(current_frequencies) / 1000.0
            if current_frequencies
            else None,
        },
        "max_temperature_c": max(temperatures) if temperatures else None,
    }


def parse_benchmark(text: str) -> Dict[str, float]:
    values = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in BENCHMARK_KEYS:
            try:
                number = float(value)
            except ValueError as error:
                raise ResultError("基准字段不是数字：{}={}".format(key, value)) from error
            if not math.isfinite(number):
                raise ResultError("基准字段不是有限数字：{}".format(key))
            values[key] = number
    missing = [key for key in BENCHMARK_KEYS if key not in values]
    if missing:
        raise ResultError("基准日志缺少字段：{}".format(", ".join(missing)))
    if not (
        values["min_ms"]
        <= values["p50_ms"]
        <= values["p95_ms"]
        <= values["p99_ms"]
        <= values["max_ms"]
    ):
        raise ResultError("基准分位数顺序异常")
    if values["peak_rss_kib"] <= 0:
        raise ResultError("峰值 RSS 必须大于 0")
    return values


def median(values: List[float]) -> float:
    return float(statistics.median(values))


def verify_config(config: Dict[str, str], expected_rounds: int,
                  allow_qemu: bool) -> None:
    if config.get("host_arch") != "aarch64" and not allow_qemu:
        raise ResultError(
            "结果不是 aarch64 原生运行；如为 QEMU 回归请加 --allow-qemu"
        )
    if config.get("qemu", "not_used") != "not_used" and not allow_qemu:
        raise ResultError(
            "结果使用了 QEMU；真机报告不允许导入模拟数据"
        )
    try:
        actual_rounds = int(config["rounds"])
    except (KeyError, ValueError) as error:
        raise ResultError("config.txt 缺少有效 rounds") from error
    if actual_rounds != expected_rounds:
        raise ResultError(
            "配置要求 {} 轮，结果实际为 {} 轮".format(
                expected_rounds, actual_rounds
            )
        )


def analyze(source: TextSource, expected_rounds: int,
            allow_qemu: bool) -> Tuple[Dict[str, object], List[Dict[str, float]]]:
    config = parse_key_values(source.read_text("config.txt"))
    verify_config(config, expected_rounds, allow_qemu)

    verification = source.read_text("verification.txt")
    required_verification = (
        "decision_agreement=1.000000",
        "invalid_shape_rejected=true",
    )
    for expected in required_verification:
        if expected not in verification:
            raise ResultError("精度验收缺少：{}".format(expected))

    round_files = source.list_benchmark_rounds()
    if len(round_files) != expected_rounds:
        raise ResultError(
            "预期 {} 个基准日志，实际找到 {} 个".format(
                expected_rounds, len(round_files)
            )
        )

    rounds = []
    checksums = []
    for round_file in round_files:
        content = source.read_text(
            round_file[len(source.prefix):]
        )
        metrics = parse_benchmark(content)
        values = parse_key_values(content)
        checksum = values.get("checksum")
        if checksum is None:
            raise ResultError("{} 缺少 checksum".format(round_file))
        checksums.append(float(checksum))
        rounds.append(metrics)

    if max(checksums) - min(checksums) > 1e-5:
        raise ResultError("不同轮次的 checksum 不一致")

    before = parse_environment(source.read_text("environment_before.txt"))
    after = parse_environment(source.read_text("environment_after.txt"))
    summary = {
        "run_id": config.get("run_id", "unknown"),
        "host_arch": config.get("host_arch", "unknown"),
        "qemu": config.get("qemu", "unknown"),
        "iterations": int(config.get("iterations", "0")),
        "warmup": int(config.get("warmup", "0")),
        "rounds": expected_rounds,
        "verification": parse_verification(verification),
        "environment_before": before,
        "environment_after": after,
        "checksum": checksums[0],
        "median_metrics": {
            key: median([round_values[key] for round_values in rounds])
            for key in BENCHMARK_KEYS
        },
    }
    return summary, rounds


def render_markdown(summary: Dict[str, object],
                    rounds: List[Dict[str, float]],
                    archive_name: str) -> str:
    environment = summary["environment_before"]
    median_metrics = summary["median_metrics"]
    temperature_candidates = [
        value
        for value in (
            summary["environment_before"].get("max_temperature_c"),
            summary["environment_after"].get("max_temperature_c"),
        )
        if value is not None
    ]
    max_temperature = max(temperature_candidates) if temperature_candidates else None

    lines = [
        "# 板端验收结果",
        "",
        "- 结果包：`{}`".format(archive_name),
        "- 运行 ID：`{}`".format(summary["run_id"]),
        "- 开发板：`{}`".format(environment["board_model"]),
        "- 系统：`{}`".format(environment["os"]),
        "- CPU：`{}`".format(environment["cpu_model"]),
        "- 内存：`{}`".format(environment["memory_total"]),
        "- 调频策略：`{}`".format(
            ", ".join(environment["governors"]) or "unavailable"
        ),
        "- 最高记录温度：`{}`".format(
            "{} °C".format(max_temperature)
            if max_temperature is not None
            else "unavailable"
        ),
        "",
        "## {} 轮中位数".format(summary["rounds"]),
        "",
        "| 均值 | P50 | P95 | P99 | 最小值 | 最大值 | 峰值 RSS |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        "| {mean_ms:.6f} ms | {p50_ms:.6f} ms | {p95_ms:.6f} ms | "
        "{p99_ms:.6f} ms | {min_ms:.6f} ms | {max_ms:.6f} ms | "
        "{peak_rss_kib:.0f} KiB |".format(**median_metrics),
        "",
        "## 每轮结果",
        "",
        "| 轮次 | 均值 | P95 | RSS |",
        "|---:|---:|---:|---:|",
    ]
    for index, round_values in enumerate(rounds, 1):
        lines.append(
            "| {} | {:.6f} ms | {:.6f} ms | {:.0f} KiB |".format(
                index,
                round_values["mean_ms"],
                round_values["p95_ms"],
                round_values["peak_rss_kib"],
            )
        )

    verification = summary["verification"]
    lines.extend([
        "",
        "## 精度验收",
        "",
        "- 决策一致率：`{}`".format(
            verification.get("decision_agreement", "unavailable")
        ),
        "- 实际 F1：`{}`".format(verification.get("actual_f1", "unavailable")),
        "- checksum：`{:.9f}`".format(summary["checksum"]),
    ])
    if summary["qemu"] != "not_used":
        lines.extend([
            "",
            "> 警告：该结果来自 QEMU，只能用于流程验证，不能写入真机性能结果。",
        ])
    return "\n".join(lines) + "\n"


def write_outputs(output_dir: Path, summary: Dict[str, object],
                  rounds: List[Dict[str, float]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "analysis.json").open("w", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    with (output_dir / "median_metrics.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["metric", "median"]
        )
        writer.writeheader()
        for key, value in summary["median_metrics"].items():
            writer.writerow({"metric": key, "median": value})


def parse_args():
    parser = argparse.ArgumentParser(
        description="校验并汇总 Orange Pi 3B 板端验收结果"
    )
    parser.add_argument("result", type=Path, help="结果 tar.gz 或解压目录")
    parser.add_argument(
        "--expected-rounds",
        type=int,
        default=5,
        help="每份结果应包含的基准轮数，默认 5",
    )
    parser.add_argument(
        "--allow-qemu",
        action="store_true",
        help="允许 QEMU 回归结果，仅用于流程验证",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="分析输出目录，默认放在结果文件旁边",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result_path = args.result.resolve()
    if not result_path.exists():
        raise ResultError("结果路径不存在：{}".format(result_path))

    if result_path.is_dir():
        source = TextSource.from_directory(result_path)
        stem = result_path.name
    else:
        source = TextSource.from_archive(result_path)
        stem = result_path.name
        if stem.endswith(".tar.gz"):
            stem = stem[:-7]

    try:
        summary, rounds = analyze(
            source, args.expected_rounds, args.allow_qemu
        )
    finally:
        source.close()

    output_dir = args.output_dir or result_path.parent / (stem + "_analysis")
    write_outputs(output_dir, summary, rounds)
    markdown = render_markdown(summary, rounds, result_path.name)
    (output_dir / "summary.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print("分析结果已写入：{}".format(output_dir))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ResultError as error:
        print("分析失败：{}".format(error), file=sys.stderr)
        sys.exit(1)
