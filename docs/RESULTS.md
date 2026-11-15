# 实测结果

本文件只记录实际运行得到的数字。每条记录必须包含测量命令、运行环境和日期。

## 环境验收

| 项目 | 实测结果 | 测量命令 | 运行环境 | 日期 |
|---|---|---|---|---|
| SKAB CSV 文件数 | 35 | `python train/audit_data.py` | WSL2 Ubuntu 24.04.5, Python 3.12.3 | 2026-11-01 |
| SKAB 总行数 | 46,806 | `python train/audit_data.py` | WSL2 Ubuntu 24.04.5, Python 3.12.3 | 2026-11-01 |
| 正常基线行数 | 9,405 | `python train/audit_data.py` | WSL2 Ubuntu 24.04.5, Python 3.12.3 | 2026-11-01 |
| 带标签实验行数 | 37,401 | `python train/audit_data.py` | WSL2 Ubuntu 24.04.5, Python 3.12.3 | 2026-11-01 |
| 异常点数量 | 13,067 | `python train/audit_data.py` | WSL2 Ubuntu 24.04.5, Python 3.12.3 | 2026-11-01 |
| changepoint 数量 | 129 | `python train/audit_data.py` | WSL2 Ubuntu 24.04.5, Python 3.12.3 | 2026-11-01 |
| 缺失传感器单元格 | 0 | `python train/audit_data.py` | WSL2 Ubuntu 24.04.5, Python 3.12.3 | 2026-11-01 |

## 窗口数据集

| 数据集 | 文件数 | 窗口形状 | 异常窗口数 | 异常比例 | 生成命令 | 日期 |
|---|---:|---|---:|---:|---|---|
| 训练集 | 25 | `[3631, 60, 8]` | 955 | 0.2630 | `python train/skab_dataset.py --window-size 60 --stride 10` | 2026-11-01 |
| 验证集 | 5 | `[542, 60, 8]` | 181 | 0.3339 | `python train/skab_dataset.py --window-size 60 --stride 10` | 2026-11-01 |
| 测试集 | 5 | `[481, 60, 8]` | 177 | 0.3680 | `python train/skab_dataset.py --window-size 60 --stride 10` | 2026-11-01 |

## 模型精度

| 模型 | Precision | Recall | F1 | 测量命令 | 运行环境 | 日期 |
|---|---:|---:|---:|---|---|---|
| 1D-CNN / 验证集 | 0.603053 | 0.872928 | 0.713318 | `python train/train_model.py --epochs 40 --batch-size 128 --threads 4 --seed 42` | WSL2 Ubuntu 24.04.5, PyTorch 2.15.0+cpu | 2026-11-02 |
| 1D-CNN / 测试集 | 0.970149 | 0.734463 | 0.836013 | `python train/train_model.py --epochs 40 --batch-size 128 --threads 4 --seed 42` | WSL2 Ubuntu 24.04.5, PyTorch 2.15.0+cpu | 2026-11-02 |

补充实测值：

- 参数量：8,609
- 验证集 ROC-AUC：0.841325
- 测试集 ROC-AUC：0.870818
- 验证集选定概率阈值：0.3870759606361389
- 对应 logit 阈值：-0.45962005756614777
- 测试集混淆矩阵：TN=300、FP=4、FN=47、TP=130

## 模型体积

| 格式 | 文件大小 | 测量命令 | 日期 |
|---|---:|---|---|
| PyTorch 检查点 | 42,703 字节 | `Get-Item train/artifacts/anomaly_cnn.pt` | 2026-11-01 |
| ONNX 模型 | 36,355 字节 | `python train/export_onnx.py --opset 13 --samples 32` | 2026-11-02 |
| ncnn FP32 param | 1,309 字节 | `Get-Item train/artifacts/anomaly_cnn_opt.param` | 2026-11-02 |
| ncnn FP32 bin | 34,004 字节 | `Get-Item train/artifacts/anomaly_cnn_opt.bin` | 2026-11-02 |
| ncnn INT8 param | 1,325 字节 | `Get-Item train/artifacts/anomaly_cnn_int8.param` | 2026-11-02 |
| ncnn INT8 bin | 9,320 字节 | `Get-Item train/artifacts/anomaly_cnn_int8.bin` | 2026-11-02 |

## PyTorch 与 ONNX 数值一致性

| 比较样本数 | 最大绝对误差 | 平均绝对误差 | 验收上限 | 测量命令 | 运行环境 | 日期 |
|---:|---:|---:|---:|---|---|---|
| 32 | 5.9604644775390625e-06 | 1.8849968910217285e-06 | 1e-4 | `python train/export_onnx.py --opset 13 --samples 32` | WSL2 Ubuntu 24.04.5, PyTorch 2.15.0+cpu, ONNX Runtime 1.31.1 | 2026-11-02 |

## ONNX 与 ncnn 数值一致性

| 比较样本数 | 最大绝对误差 | 平均绝对误差 | 验收上限 | 测量命令 | 运行环境 | 日期 |
|---:|---:|---:|---:|---|---|---|
| 32 | 2.86102294921875e-06 | 8.288770914077759e-07 | 1e-4 | `build/ncnn-host/ncnn_infer_fixture ...; python train/ncnn_fixture.py --actual ...` | WSL2 Ubuntu 24.04.5, ncnn 20261020, C++11 | 2026-11-01 |

## INT8 量化结果

| 模型 | 样本数 | Precision | Recall | F1 | 预测异常数 |
|---|---:|---:|---:|---:|---:|
| FP32 / ONNX Runtime | 481 | 0.970149 | 0.734463 | 0.836013 | 134 |
| INT8 / ncnn C++ | 481 | 0.970149 | 0.734463 | 0.836013 | 134 |

补充实测值：

- FP32 与 INT8 分类决策一致率：1.0
- F1 变化：0.0
- 最大概率误差：0.045446574687957764
- 平均概率误差：0.008290179073810577
- 最大 logit 误差：4.492511749267578；该误差发生在概率接近 0.9999 的饱和区域
- INT8 权重文件相对 FP32 减少约 72.6%
- param 与 bin 合计体积从 35,313 字节降至 10,645 字节，减少约 69.9%

## 推理性能

QEMU ARM64 数据必须注明为模拟环境，不能作为真机 ARM64 性能。

### 测量口径

- 计时范围：`AnomalyDetector::score()` 单窗口端到端调用，包含输入标准化、
  `ncnn::Mat` 构造、Extractor 输入、INT8/FP32 推理和 Sigmoid；不包含模型
  文件加载、夹具文件读取和进程启动。
- 夹具：481 个真实测试窗口，按顺序循环使用；输入为 `[60, 8]`，4 线程。
- 统计：每个环境/模型组合顺序执行 5 轮。`mean`、P95、P99 和峰值 RSS
  均取 5 轮结果的中位数。每轮 P95/P99 使用 nearest-rank；
  native 每轮预热 100 次、计时 2,000 次，QEMU 每轮预热 30 次、
  计时 1,000 次。
- RSS：native 为进程最大 RSS，包含静态链接的 ncnn、已加载模型、夹具和
  C++ 运行时；QEMU 行为宿主 `qemu-aarch64` 进程最大 RSS，包含模拟器开销，
  不是目标板或 ARM64 应用独立内存。
- 模型文件 SHA-256：
  INT8 param `6e000ff99dd04cb8668c5c1f1cade4aef40b5194bb1483e1b693d59df07716cb`，
  INT8 bin `5d5f067c9dd962b7dc602b6ea7918bf4d5715cbfaad629e0b4fe540cacf73f2e`。

### 实测结果

| 环境 | 模型 | 每轮预热/计时 | 轮数 | 延迟均值 | P95 | P99 | 峰值 RSS | 测量命令 | 日期 |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| x86_64 native | FP32 | 100 / 2,000 | 5 | 0.058912 ms | 0.082400 ms | 0.113900 ms | 6,456 KiB | `pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\benchmark_stage5.ps1` | 2026-11-02 |
| x86_64 native | INT8 | 100 / 2,000 | 5 | 0.072774 ms | 0.097700 ms | 0.141500 ms | 6,524 KiB | `pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\benchmark_stage5.ps1` | 2026-11-02 |
| QEMU ARM64（模拟） | FP32 | 30 / 1,000 | 5 | 6.258285 ms | 8.325100 ms | 8.830900 ms | 18,856 KiB | `pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\benchmark_stage5.ps1` | 2026-11-02 |
| QEMU ARM64（模拟） | INT8 | 30 / 1,000 | 5 | 4.386066 ms | 6.478800 ms | 6.979200 ms | 18,856 KiB | `pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\benchmark_stage5.ps1` | 2026-11-02 |

运行环境：

- WSL2 Ubuntu 24.04.5，Linux 6.18.54.1-microsoft-standard-WSL2，4 vCPU，
  3.8 GiB 内存。
- Intel Core i5-10210U，2 物理核 / 4 硬件线程；WSL 仅分配 4 vCPU。
- Release 构建，GCC/G++ 13.3.0，CMake 3.28.3，ncnn `20261020`，
  QEMU `aarch64` 8.2.2 用户态，C++11。
- benchmark 生成的原始 CSV：`build/stage5_benchmarks.csv`（构建产物，
  不纳入版本控制）。

### 结果说明

- x86_64 上 INT8 平均延迟比 FP32 增加约 23.5%，P95 增加约 18.6%。
  量化不保证速度提升；这个结果按原样保留。
- QEMU ARM64 模拟环境 INT8 平均延迟比 FP32 低约 29.9%，
  P95 低约 22.2%。该差异只证明当前 QEMU/ncnn 组合下的模拟行为，
  不能外推为 RK3568 或 NPU 的性能。
- 模型体积方面，param+bin 合计从 35,313 字节降至 10,645 字节，
  减少约 69.9%。481 个测试窗口上 FP32 与 INT8 的 Precision、Recall、
  F1 和分类决策完全一致，详见上文“INT8 量化结果”。

### 简历口径

可以写：

- 完成模型 INT8 量化，模型合计体积从 35,313 字节降至 10,645 字节，
  测试集 F1 保持 0.836013。
- 在 Orange Pi 3B（RK3566，ARM64 Linux）完成 C++/ncnn INT8 推理部署，
  481 个测试窗口决策一致率为 1.0；单窗口延迟中位数均值 0.222374 ms、
  P95 0.240042 ms，进程峰值 RSS 4,568 KiB。

不可写：

- 将 QEMU 的 4.386066 ms 写成 Orange Pi 3B 或其他硬件的实测延迟。
- 写成使用了 NPU 加速或获得了真实硬件加速倍数。

## ARM64 交付包（阶段 6A）

| 项目 | 实测结果 | 测量命令 | 运行环境 | 日期 |
|---|---:|---|---|---|
| 压缩包大小 | 10,702,845 字节 | `Get-Item dist/edge-ai-arm64-stage6.tar.gz` | Windows PowerShell 7 | 2026-11-13 |
| 压缩包 SHA-256 | `a90a2a339d1cbdc35b136c55c54085331da240b0e53a2e6373c1f926ec8483ad` | `sha256sum dist/edge-ai-arm64-stage6.tar.gz` | WSL2 Ubuntu 24.04.5 | 2026-11-13 |
| benchmark 可执行文件 | 7,611,352 字节 | `stat -c %s dist/edge-ai-arm64-stage6/bin/anomaly_detector_benchmark` | aarch64 静态 ELF，已 strip | 2026-11-02 |
| stream 可执行文件 | 7,611,344 字节 | `stat -c %s dist/edge-ai-arm64-stage6/bin/anomaly_detector_stream` | aarch64 静态 ELF，已 strip | 2026-11-03 |
| 验收可执行文件 | 7,545,816 字节 | `stat -c %s dist/edge-ai-arm64-stage6/bin/anomaly_detector_test` | aarch64 静态 ELF，已 strip | 2026-11-02 |

交付包构建与独立解压验收命令：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_stage6_package.ps1
```

独立解压后的 QEMU 验收结果：

- `SHA256SUMS` 中全部 23 个文件校验通过。
- 481 个测试窗口通过，`decision_agreement=1.000000`、
  `actual_f1=0.836013`、`invalid_shape_rejected=true`。
- 短基准成功输出延迟分位数、RSS 和 checksum；完整日志位于
  `build/stage6_package_smoke.txt`。
- 压缩包内目录和可执行程序权限为 `755`，数据、模型和文档为 `644`。
- 两个可执行文件均为 `ELF64 AArch64`、`statically linked`、`stripped`；
  `ldd` 输出 `not a dynamic executable`。
- `BUILD_INFO.txt` 记录源码提交
  `73f5deb512a092548210c969be51d93f2c558a3a`、`source_tree_dirty=no`，
  且在真机验收完成后标记 `board_validation=passed`。

## Orange Pi 3B 真机验证（阶段 6B）

状态：Orange Pi 3B 4GB（RK3566）已完成首次启动、481 窗口精度验收和
5 轮 INT8 性能采集。

| 待测项目 | 实测结果 | 测量命令 | 运行环境 | 日期 |
|---|---|---|---|---|
| 481 窗口决策一致率 / F1 | 1.000000 / 0.836013 | `sh run_acceptance.sh` | Orange Pi 3B 4GB / RK3566 | 2026-11-13 |
| 五轮延迟均值 / P95 / P99 | 0.222374 / 0.240042 / 0.278541 ms | `sh run_acceptance.sh` | Orange Pi 3B 4GB / RK3566 | 2026-11-13 |
| 进程峰值 RSS | 4,568 KiB | `sh run_acceptance.sh` | Orange Pi 3B 4GB / RK3566 | 2026-11-13 |
| CPU 频率策略与温度 | `performance` / 1.8 GHz / 39.444～40.625°C | `cat results/*/environment_*.txt` | Orange Pi 3B 4GB / RK3566 | 2026-11-13 |

正式基线运行信息：

- 运行 ID：`20261113_222845`
- 镜像：`Orangepi3b_1.0.8_debian_bookworm_server_linux5.10.160.img`
- 系统：Orange Pi 1.0.8 Bookworm，Linux 5.10.160-rockchip-rk356x
- CPU：4 × Cortex-A55，最高 1.8 GHz；测试前临时将 CPU0～CPU3 调为
  `performance`，测试后恢复 `ondemand`
- 内存：3.8 GiB；模型配置为 4 线程
- 每轮预热 30 次、计时 1,000 次，共 5 轮
- 原始结果包：`board_results_20261113_222845.tar.gz`
- 原始结果包 SHA-256：
  `9a8c9b7958258368789b42514be8edad8c909065f27f207c80281330f644edd5`
- 审核后回归基线：`benchmarks/orangepi3b-rk3566-int8-baseline.json`

五轮明细：

| 轮次 | 均值 | P95 | P99 | 峰值 RSS |
|---:|---:|---:|---:|---:|
| 1 | 0.226640 ms | 0.259584 ms | 0.299833 ms | 4,568 KiB |
| 2 | 0.221420 ms | 0.240625 ms | 0.275041 ms | 4,568 KiB |
| 3 | 0.222374 ms | 0.239750 ms | 0.278541 ms | 4,568 KiB |
| 4 | 0.221628 ms | 0.238292 ms | 0.282625 ms | 4,568 KiB |
| 5 | 0.222509 ms | 0.240042 ms | 0.265709 ms | 4,568 KiB |

正式基线前使用默认 `ondemand` 策略试跑过一次。该次结果为五轮中位数
均值 `0.288450 ms`、P95 `0.586542 ms`、P99 `0.978833 ms`、峰值 RSS
`4,572 KiB`，但各轮 P95 在 `0.239166～1.076541 ms` 之间波动。为获得
可比较的稳定基线，正式运行固定 `performance` 策略；默认策略试跑结果保留在
本机 `dist/board_results_20241118_084335.tar.gz`（板子当时时钟未校准），
不与正式基线混用。

首次烧录曾出现主 GPT 校验错误：

```text
GUID Partition Table Entry Array CRC is wrong
*** ERROR: Invalid GPT ***
*** Using Backup GPT ***
```

源镜像 SHA-256 校验正常；使用完整版 USBImager 选择物理磁盘 `Disk 1`
重写并启用校验后，GPT 错误消失，U-Boot、内核和用户态完整启动。该问题归类
为写卡问题，不是板卡、电源或串口故障。

## CSV 流式检测补充验证

| 项目 | 实测结果 | 测量命令 | 运行环境 | 日期 |
|---|---:|---|---|---|
| 90 行 SKAB CSV 输入 | 输出 4 个滑窗预测 | `head -n 91 .../anomaly-free.csv \| QEMU_ARM64=qemu-aarch64 sh run_stream.sh - 10` | QEMU ARM64 | 2026-11-03 |
| 输出首尾时间 | `2020-02-08 13:31:46` 至 `2020-02-08 13:32:16` | 同上 | QEMU ARM64 | 2026-11-03 |
| 输出概率范围 | 0.031631146 至 0.032351505 | 同上 | QEMU ARM64 | 2026-11-03 |

该段输入来自 SKAB normal 文件的前 90 个采样，仅用于验证流式窗口和时间推进，
不作为真机延迟或精度指标。
