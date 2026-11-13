#!/bin/sh
set -eu

ROOT=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ] && [ -z "${QEMU_ARM64:-}" ]; then
    echo "错误：当前架构为 $ARCH，需要 aarch64。" >&2
    exit 2
fi

ITERATIONS=${1:-1000}
WARMUP=${2:-30}
case "$ITERATIONS" in
    ''|*[!0-9]*)
        echo "错误：迭代数必须是正整数。" >&2
        exit 2
        ;;
esac
case "$WARMUP" in
    ''|*[!0-9]*)
        echo "错误：预热次数必须是非负整数。" >&2
        exit 2
        ;;
esac
if [ "$ITERATIONS" -le 0 ]; then
    echo "错误：迭代数必须大于 0。" >&2
    exit 2
fi

run_arm64() {
    if [ -n "${QEMU_ARM64:-}" ]; then
        "$QEMU_ARM64" "$@"
    else
        "$@"
    fi
}

echo "架构=$ARCH iterations=$ITERATIONS warmup=$WARMUP"
run_arm64 "$ROOT/bin/anomaly_detector_benchmark" \
    "$ROOT/model/anomaly_cnn_int8.param" \
    "$ROOT/model/anomaly_cnn_int8.bin" \
    "$ROOT/model/model_config.txt" \
    "$ROOT/data/raw_input.f32" \
    481 "$WARMUP" "$ITERATIONS"
