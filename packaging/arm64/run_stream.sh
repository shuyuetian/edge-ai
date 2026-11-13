#!/bin/sh
set -eu

ROOT=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ] && [ -z "${QEMU_ARM64:-}" ]; then
    echo "错误：当前架构为 $ARCH，需要 aarch64。" >&2
    exit 2
fi

INPUT=${1:-}
STRIDE=${2:-10}
if [ -z "$INPUT" ]; then
    echo "用法：sh run_stream.sh <csv路径|-> [stride]" >&2
    exit 2
fi
case "$STRIDE" in
    ''|*[!0-9]*)
        echo "错误：stride 必须是正整数。" >&2
        exit 2
        ;;
esac
if [ "$STRIDE" -le 0 ]; then
    echo "错误：stride 必须大于 0。" >&2
    exit 2
fi

run_arm64()
{
    if [ -n "${QEMU_ARM64:-}" ]; then
        "$QEMU_ARM64" "$@"
    else
        "$@"
    fi
}

run_arm64 "$ROOT/bin/anomaly_detector_stream" \
    "$ROOT/model/anomaly_cnn_int8.param" \
    "$ROOT/model/anomaly_cnn_int8.bin" \
    "$ROOT/model/model_config.txt" \
    "$INPUT" "$STRIDE"
