#!/bin/sh
set -eu

ROOT=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ] && [ -z "${QEMU_ARM64:-}" ]; then
    echo "错误：当前架构为 $ARCH，需要 aarch64。" >&2
    exit 2
fi

run_arm64() {
    if [ -n "${QEMU_ARM64:-}" ]; then
        "$QEMU_ARM64" "$@"
    else
        "$@"
    fi
}

echo "架构=$ARCH，开始 481 窗口验收。"
run_arm64 "$ROOT/bin/anomaly_detector_test" \
    "$ROOT/model/anomaly_cnn_int8.param" \
    "$ROOT/model/anomaly_cnn_int8.bin" \
    "$ROOT/model/model_config.txt" \
    "$ROOT/data/raw_input.f32" \
    "$ROOT/data/expected_probability.f32" \
    "$ROOT/data/labels.i8" \
    481
