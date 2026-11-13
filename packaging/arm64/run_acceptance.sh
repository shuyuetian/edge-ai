#!/bin/sh
set -eu

ROOT=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ] && [ -z "${QEMU_ARM64:-}" ]; then
    echo "错误：当前架构为 $ARCH，需要 aarch64。" >&2
    exit 2
fi

ITERATIONS=${ITERATIONS:-1000}
WARMUP=${WARMUP:-30}
ROUNDS=${ROUNDS:-5}
SETTLE_SECONDS=${SETTLE_SECONDS:-10}
ROUND_COOLDOWN_SECONDS=${ROUND_COOLDOWN_SECONDS:-10}

validate_integer()
{
    value=$1
    name=$2
    minimum=$3
    case "$value" in
        ''|*[!0-9]*)
            echo "错误：$name 必须是非负整数。" >&2
            exit 2
            ;;
    esac
    if [ "$value" -lt "$minimum" ]; then
        echo "错误：$name 必须大于等于 $minimum。" >&2
        exit 2
    fi
}

validate_integer "$ITERATIONS" "ITERATIONS" 1
validate_integer "$WARMUP" "WARMUP" 0
validate_integer "$ROUNDS" "ROUNDS" 1
validate_integer "$SETTLE_SECONDS" "SETTLE_SECONDS" 0
validate_integer "$ROUND_COOLDOWN_SECONDS" "ROUND_COOLDOWN_SECONDS" 0

RUN_ID=$(date '+%Y%m%d_%H%M%S')
RESULT_ROOT="$ROOT/results"
RESULT_DIR="$RESULT_ROOT/$RUN_ID"
mkdir -p "$RESULT_DIR"

{
    printf 'run_id=%s\n' "$RUN_ID"
    printf 'host_arch=%s\n' "$ARCH"
    printf 'qemu=%s\n' "${QEMU_ARM64:-not_used}"
    printf 'iterations=%s\n' "$ITERATIONS"
    printf 'warmup=%s\n' "$WARMUP"
    printf 'rounds=%s\n' "$ROUNDS"
    printf 'settle_seconds=%s\n' "$SETTLE_SECONDS"
    printf 'round_cooldown_seconds=%s\n' "$ROUND_COOLDOWN_SECONDS"
} > "$RESULT_DIR/config.txt"

echo "开始板端验收：$RUN_ID"
sh "$ROOT/collect_board_info.sh" > "$RESULT_DIR/environment_before.txt"

if [ "$SETTLE_SECONDS" -gt 0 ]; then
    echo "等待 $SETTLE_SECONDS 秒，让系统进入稳定状态。"
    sleep "$SETTLE_SECONDS"
fi

echo "运行 481 窗口精度与决策一致性验收。"
if ! sh "$ROOT/run_verification.sh" > "$RESULT_DIR/verification.txt" 2>&1; then
    cat "$RESULT_DIR/verification.txt"
    echo "精度验收失败，结果保留在 $RESULT_DIR" >&2
    exit 1
fi
cat "$RESULT_DIR/verification.txt"
if ! grep -q 'decision_agreement=1.000000' "$RESULT_DIR/verification.txt"; then
    echo "错误：未得到 1.0 的分类决策一致率。" >&2
    exit 1
fi

round=1
while [ "$round" -le "$ROUNDS" ]; do
    round_name=$(printf '%02d' "$round")
    log_path="$RESULT_DIR/benchmark_round_$round_name.txt"
    echo "运行性能第 $round/$ROUNDS 轮。"
    if ! sh "$ROOT/run_benchmark.sh" "$ITERATIONS" "$WARMUP" > "$log_path" 2>&1; then
        cat "$log_path"
        echo "第 $round 轮基准失败，结果保留在 $RESULT_DIR" >&2
        exit 1
    fi
    cat "$log_path"
    round=$((round + 1))
    if [ "$round" -le "$ROUNDS" ] && [ "$ROUND_COOLDOWN_SECONDS" -gt 0 ]; then
        echo "冷却 $ROUND_COOLDOWN_SECONDS 秒。"
        sleep "$ROUND_COOLDOWN_SECONDS"
    fi
done

sh "$ROOT/collect_board_info.sh" > "$RESULT_DIR/environment_after.txt"

benchmark_summary="$RESULT_DIR/benchmark_summary.csv"
printf 'round,mean_ms,p50_ms,p95_ms,p99_ms,min_ms,max_ms,peak_rss_kib\n' > \
    "$benchmark_summary"
for log_path in "$RESULT_DIR"/benchmark_round_*.txt; do
    round_name=$(basename "$log_path" .txt)
    round_name=${round_name#benchmark_round_}
    mean_ms=$(sed -n 's/^mean_ms=//p' "$log_path")
    p50_ms=$(sed -n 's/^p50_ms=//p' "$log_path")
    p95_ms=$(sed -n 's/^p95_ms=//p' "$log_path")
    p99_ms=$(sed -n 's/^p99_ms=//p' "$log_path")
    min_ms=$(sed -n 's/^min_ms=//p' "$log_path")
    max_ms=$(sed -n 's/^max_ms=//p' "$log_path")
    peak_rss_kib=$(sed -n 's/^peak_rss_kib=//p' "$log_path")
    printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$round_name" "$mean_ms" "$p50_ms" "$p95_ms" "$p99_ms" \
        "$min_ms" "$max_ms" "$peak_rss_kib" >> "$benchmark_summary"
done

ARCHIVE_PATH="$RESULT_ROOT/board_results_$RUN_ID.tar.gz"
tar -czf "$ARCHIVE_PATH" -C "$RESULT_ROOT" "$RUN_ID"

printf '\n验收完成。\n'
printf '结果目录：%s\n' "$RESULT_DIR"
printf '结果压缩包：%s\n' "$ARCHIVE_PATH"
