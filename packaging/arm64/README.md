# 端侧 AI 异常检测 ARM64 交付包

本包用于在 AArch64 Linux 上验证 INT8 异常检测模型并采集性能数据。
当前构建产物已通过 QEMU 回归，并在 Orange Pi 3B 4GB（RK3566）上完成
481 窗口精度验收和 5 轮性能测试。

## 包内容

- `bin/anomaly_detector_benchmark`：端到端单窗口延迟与 RSS 基准程序。
- `bin/anomaly_detector_test`：481 个测试窗口的精度与决策一致性验收。
- `bin/anomaly_detector_stream`：从 CSV 持续读取传感器并输出异常结果。
- `model/anomaly_cnn_int8.param`、`model/anomaly_cnn_int8.bin`：INT8 模型。
- `model/model_config.txt`：窗口大小、线程数和标准化参数。
- `data/`：固定测试输入、期望概率和标签。
- `collect_board_info.sh`：采集开发板、系统、CPU、频率、温度和内存信息。
- `run_acceptance.sh`：执行精度验收和默认 5 轮性能测试，并生成结果压缩包。
- `run_stream.sh`：调用 CSV 流式异常检测程序。
- `BOARD_BRINGUP.md`：Orange Pi 3B 烧录、串口、SSH 和故障排查手册。
- `LICENSE`、`NOTICE`：项目代码的 Apache-2.0 许可证和归属声明。
- `THIRD_PARTY_NOTICES.md`：第三方软件与数据许可证说明。
- `licenses/`：ncnn 与 SKAB 的完整许可证副本。
- `SHA256SUMS`：包内文件完整性校验。
- `BUILD_INFO.txt`：构建时间、源码版本和工具链信息。

二进制为静态链接，不依赖目标板的 ncnn、C++ 运行时或 OpenMP 动态库。

## 快速开始

在 ARM64 Linux 上执行：

```sh
tar -xzf edge-ai-arm64-stage6.tar.gz
cd edge-ai-arm64-stage6
sha256sum -c SHA256SUMS
uname -m
sh run_acceptance.sh
```

`uname -m` 应输出 `aarch64`。`run_acceptance.sh` 默认每轮预热 30 次、
计时 1,000 次，共运行 5 轮；结果写入 `results/`，并生成
`board_results_<时间>.tar.gz`。

临时调整轮数或迭代数：

```sh
ITERATIONS=500 WARMUP=20 ROUNDS=3 sh run_acceptance.sh
```

## CSV 流式检测

输入 CSV 必须包含 `datetime`（或 `timestamp`）以及以下 8 个字段：

```text
Accelerometer1RMS
Accelerometer2RMS
Current
Pressure
Temperature
Thermocouple
Voltage
Volume Flow RateRMS
```

支持逗号和分号分隔，字段顺序不限。默认每 10 个采样执行一次推理：

```sh
sh run_stream.sh sensor.csv 10 > predictions.csv
cat sensor.csv | sh run_stream.sh - 10 > predictions.csv
```

输出列为：

```text
timestamp,unix_seconds,probability,is_anomaly
```

## 输出说明

验收脚本应输出：

- `decision_agreement=1.000000`
- `actual_f1=0.836013`
- `invalid_shape_rejected=true`
- `C++ AnomalyDetector 验收通过`

基准脚本输出：

- `mean_ms`：单窗口平均延迟。
- `p95_ms`、`p99_ms`：nearest-rank 延迟分位数。
- `peak_rss_kib`：基准进程最大 RSS。
- `checksum`：所有输出概率的累加值，用于确认推理确实执行。

计时范围包含标准化、ncnn 推理和 Sigmoid，不包含模型加载与文件读取。

## Orange Pi 3B 首次启动

烧录、供电、串口接线、SSH 和故障排查统一参见包内 `BOARD_BRINGUP.md`。
真机性能结果必须注明开发板型号、CPU 频率策略、运行日期和完整命令，QEMU
数据不能与真机数据混写。

2026-11-13 的正式基线使用 `performance` 调频策略，五轮中位数均值
`0.222374 ms`、P95 `0.240042 ms`、P99 `0.278541 ms`、峰值 RSS
`4,568 KiB`。测试后已将 CPU 调频恢复为 `ondemand`。

## 本地 QEMU 验证

开发机可临时指定 QEMU 启动器：

```sh
QEMU_ARM64=qemu-aarch64 sh run_verification.sh
QEMU_ARM64=qemu-aarch64 sh run_benchmark.sh 100 10
QEMU_ARM64=qemu-aarch64 ITERATIONS=20 WARMUP=5 ROUNDS=1 \
    SETTLE_SECONDS=0 ROUND_COOLDOWN_SECONDS=0 sh run_acceptance.sh
```

该方式会正确加载静态 ARM64 二进制，但仍属于模拟环境。

## 数据说明

`data/` 中的夹具由公开 SKAB 数据整理而来，仅用于本项目本地功能与性能验证。
SKAB 固定提交采用 GPLv3；对外分发本包前，必须附带许可证和来源说明，并提供
对应生成源码及可获取数据的位置。更稳妥的做法是不公开分发包含夹具的 tar 包。
