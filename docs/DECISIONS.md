# 技术与数据决策

## DEC-001：项目边界

- 目标平台为 ARM64 Linux。
- 已自购 Orange Pi 3B（RK3566），当前先使用 QEMU 用户态完成功能验证。
- 推理引擎固定为 ncnn，C++ 标准固定为 C++11。
- 不使用公司开发板或公司数据。

## DEC-002：主数据集使用 SKAB

选择理由：

- 包含 `Current`、`Voltage`、`Temperature` 等与目标场景一致的传感器。
- 同时提供逐点异常标签和 changepoint 标签。
- 数据量小，适合轻量模型和快速迭代。
- 公开下载，可记录来源并进行可复现实验。

来源：

- 仓库：https://github.com/waico/SKAB
- 提交：`b2c0d46c2971dcbfe71e26087b6d231998bb91c2`
- 本地目录：`data/skab`

数据审计结果：

- 35 个 CSV，4,392,581 字节。
- 46,806 行传感器数据。
- 34 个实验文件带异常标签，共 37,401 行。
- 13,067 个异常点，129 个 changepoint 标记。
- `anomaly-free/anomaly-free.csv` 有 9,405 行，文件本身不包含标签列，按正常数据使用。
- 8 个传感器字段无缺失，异常和 changepoint 标签均为合法 0/1。

使用约束：

- 按实验文件划分训练、验证和测试，禁止随机拆分同一文件的窗口。
- 数据存在少量 2 秒采样抖动和更长采集停顿；允许对 1 秒内的缺失采样插值，
  间隔超过 2 秒时必须断开，不能跨停顿组成窗口。
- 报告中写明数据来自公开水泵实验台，不写成真实工业现场。
- 固定提交的 `LICENSE` 正文和 README 徽章均确认 GPLv3；个人作品集使用需
  保留来源和 DOI，不在公开 Git 中重新分发原始或派生数据。详见 DEC-014。

## DEC-003：模型结构优先级

优先使用 MLP、1D-CNN、TCN 或卷积自编码器。暂不优先使用 LSTM、GRU
和注意力结构，以降低 ONNX 到 ncnn 的算子转换风险。

## DEC-004：WSL2 运行环境

- WSL 版本：3.0.3.0
- 发行版：Ubuntu 24.04.5 LTS
- Linux 磁盘：`D:\workspace\edge-ai\.wsl\Ubuntu-24.04\ext4.vhdx`
- 资源配置：4 CPU、4 GB 内存、2 GB swap
- swap 文件：`D:\workspace\edge-ai\.wsl\swap.vhdx`
- 日常用户：`ubuntu`

## DEC-005：窗口与标签

- 输入为 8 路传感器，窗口长度 60 秒，步长 10 秒。
- 窗口标签采用窗口末端采样点对应的 `anomaly` 值，用于模拟在线检测。
- 标准化均值和标准差只使用训练集中的 `anomaly-free` 数据计算。
- 按实验文件隔离后，训练 3,631 个窗口、验证 542 个、测试 481 个。

## DEC-006：ncnn 固定版本

- 使用 ncnn `20261020`，提交
  `7e36d25cb153092ba87a60530455c7376fedf452`。
- 源码保存在 `third_party/ncnn`，不纳入项目 Git，按版本标签可重新获取。
- 已安装 OpenCV 4.6.0、Protobuf 3.21.12 和 `protoc`，用于构建
  `onnx2ncnn`、`ncnn2table`、`ncnn2int8` 等转换工具。
- pnnx 作为备用路线，仅在 ONNX 到 ncnn 转换出现无法绕过的算子问题时再下载。

## DEC-007：首个异常检测模型

- 模型为 8 路输入、60 秒窗口的轻量 1D-CNN。
- 参数量为 8,609，使用二分类交叉熵和训练集类别权重。
- 标准化参数仅来自正常基线训练文件。
- 验证集选择 F1 最优阈值，测试集只使用该固定阈值评估。
- 60 秒输入经过两次池化后固定为 15 个时间点，因此使用固定长度平均池化，
  不使用 `AdaptiveAvgPool1d`，避免新版 ncnn 将其转换为错误的全局池化语义。
- ncnn INT8 工具仅支持二维 `Convolution`，不支持 `Convolution1D`。模型改用
  高为 1 的 `1×K` 二维卷积表达一维时序卷积，语义和参数量不变，但可被
  `ncnn2table` 和 `ncnn2int8` 正确量化。

## DEC-008：ONNX 导出格式

- 使用 ONNX opset 13。
- 部署输入固定为 `[1, 60, 8]`，不启用动态 batch，降低端侧 C++ 封装和
  ncnn 转换复杂度。
- 输入名为 `sensor_window`，输出名为 `anomaly_logit`。
- PyTorch 与 ONNX Runtime 的数值一致性上限固定为 `1e-4`。

## DEC-009：ncnn 转换验证

- ncnn x86 转换工具按通用 CPU 配置构建，未启用运行时 SIMD 分派；这些工具
  只负责模型转换，正式 ARM64 库在阶段 3 单独构建。
- 当前 ncnn `20261020` 顶层工具构建不再默认包含 `onnx2ncnn`，本项目使用
  同一源码中的官方转换器单独编译。
- CMake 曾误用旧 vcpkg 的 Windows Protobuf；构建时通过
  `CMAKE_DISABLE_FIND_PACKAGE_protobuf=TRUE` 强制回退到 Ubuntu 系统 Protobuf。
- `ncnnoptimize` 融合 Conv+ReLU 后，模型从 13 层降为 9 层。

## DEC-010：INT8 校准与阈值口径

- 校准数据只使用训练集中的 2,676 个正常窗口，按固定随机种子选择其中 512 个。
- 校准输入使用与部署一致的通道优先布局 `[8, 1, 60]`，ncnn shape 参数为
  `[60, 1, 8]`。
- 量化采用 KL 方法，线程数为 4。
- 模型输出的 `anomaly_logit` 尚未经过 Sigmoid。训练得到的
  `0.3870759606361389` 是概率阈值，部署比较时必须使用
  `-0.45962005756614777` 的 logit 阈值。
- FP32 与 INT8 在 481 个测试窗口上的分类决策一致率为 1.0，F1 均为
  0.836013。

## DEC-011：性能与内存测量口径

- 阶段 5 的性能入口为 `AnomalyDetector::score()`，覆盖预处理、ncnn 推理
  和 Sigmoid，不把模型加载或测试数据文件读取混入单窗口延迟。
- 基准固定使用 481 个真实测试窗口和 `model_config.txt` 的 4 线程配置。
  各环境/模型组合重复 5 轮，报告 5 轮中位数；每轮 P95/P99 使用
  nearest-rank。
- native 使用 `/usr/bin/time -v` 的进程最大 RSS；QEMU 使用宿主
  `qemu-aarch64` 进程最大 RSS，并明确标注包含模拟器开销。
- QEMU 数据只用于功能一致性和相对趋势参考。真机性能必须在实际 ARM64
  板卡上重新测量后才能写入结果或简历。
- 当前 x86_64 小模型上 INT8 平均延迟高于 FP32；不为了得到“量化必加速”
  的结论更换指标或筛除数据。

## DEC-012：ARM64 交付包静态链接

- 阶段 6A 交付包采用完整静态链接，避免开发机 Ubuntu 24.04 的 glibc
  版本限制目标板运行。
- OpenMP 不走 CMake imported target，而是由交叉编译器定位并显式链接
  `libgomp.a`；否则 `-static` 仍会引用 `libgomp.so`。
- 静态 `libgomp` 包含可选加速器插件加载路径，链接器会给出 `dlopen`
  警告；当前使用 CPU OpenMP，已通过 QEMU 功能与短基准。阶段 6B 上真机时
  仍需确认 OpenMP 线程正常工作。
- 交付归档由 `scripts/create_arm64_archive.py` 生成，显式设置 Unix 权限，
  不依赖 Windows 挂载目录的权限映射。
- 阶段 6A 当时只证明包可在 QEMU 中独立运行；阶段 6B 已进一步在真实
  Orange Pi 3B 上完成验证，见 DEC-017。

## DEC-013：真机目标调整为 Orange Pi 3B

- 原计划自购 RK3568；结合当前预算和购买渠道，用户已选择自购
  Orange Pi 3B 4GB（RK3566）。
- 调整原因是降低真机验证成本，同时继续满足项目的核心约束：AArch64
  Linux、可运行现有静态 C++/ncnn 交付包。
- 模型、ONNX 和 ncnn 技术路线不变；静态 AArch64 二进制原则上不需要改代码。
- Orange Pi 3B/RK3566 不能沿用任何 RK3568 的名义或性能结论。后续结果必须
  明确写运行板型，QEMU 数据仍只标为模拟环境。
- 真机到货后先验证 OpenMP 线程、散热、网络和串口登录，再采集正式数据。

## DEC-014：SKAB 数据与派生夹具发布边界

- 固定提交 `b2c0d46c2971dcbfe71e26087b6d231998bb91c2` 的许可证正文为
  GPLv3，本地副本与远端原文 SHA-256 一致。
- 原始 SKAB 数据、窗口数据、校准集、ncnn 测试夹具和 C++ 固定夹具均视为
  数据或派生数据，不进入公开 Git。
- C++ 固定夹具由 `train/export_inference_assets.py` 在本地流水线中生成。
- 包含测试夹具的 ARM64 tar 包定位为个人本地验收产物；公开分发前必须附带
  GPLv3、来源、修改说明和对应生成源码。
- 项目代码许可证尚未选择，不能默认使用 MIT 或 Apache-2.0。
- 许可证细节统一记录在根目录 `THIRD_PARTY_NOTICES.md`。

## DEC-015：CSV 流式窗口语义

- 流式工具按 `datetime` 或 `timestamp` 加 8 个固定传感器字段读取 CSV，支持
  逗号和分号，字段顺序根据表头映射。
- 采样间隔为 1 秒时直接追加；间隔为 2 秒时用前后值线性插值补齐一个采样；
  间隔大于 2 秒时强制开启新段，禁止跨采集停顿形成窗口。
- 与训练脚本一致，每段累计满 60 个采样后，在 60、70、80……位置触发推理。
- 流式工具输出 `timestamp,unix_seconds,probability,is_anomaly`。
- 时间戳只用于排序和间隔判断，按无时区的 UTC 秒解释；输出保留输入时间文本。

## DEC-016：代码许可证与文档单一来源

- 项目代码采用 Apache License 2.0，根目录提供 `LICENSE` 和 `NOTICE`。
- 选择 Apache-2.0 的原因不是项目具有明显专利价值，而是它更适合作为可被
  公司审阅和试用的个人工程作品集，并提供明确的专利授权条款。
- SKAB 数据仍使用独立 GPLv3；Apache-2.0 不会改变数据许可证。
- 第三方组件、数据和运行时许可证统一记录在 `THIRD_PARTY_NOTICES.md`。
- 交付包同时携带 Apache、ncnn 和 SKAB 许可证副本。
- 已删除过期的 AGENTS 模板、重复数据许可证页和 third_party 小 README。

## DEC-017：Orange Pi 3B 真机性能基线

- 真实硬件为 Orange Pi 3B 4GB、Rockchip RK3566、4 × Cortex-A55，
  系统为 Orange Pi 1.0.8 Bookworm、Linux 5.10.160-rockchip-rk356x。
- 默认 `ondemand` 策略下试跑的 P95 波动较大，因此正式回归基线临时将
  CPU0～CPU3 固定为 `performance`（1.8 GHz），测试后恢复 `ondemand`。
  两种策略的结果均在 `docs/RESULTS.md` 中如实记录，不混用。
- 正式基线为 5 轮、每轮预热 30 次、计时 1,000 次、4 线程。审核后的
  `analysis.json` 保存为 `benchmarks/orangepi3b-rk3566-int8-baseline.json`。
- 当前推理完全运行在 CPU 上，没有启用或验证 RK3566 NPU；不得根据 CPU
  实测数据推导 NPU 加速倍数。
- 首次写卡造成主 GPT CRC 错误，U-Boot 回退备用 GPT 后 Linux 未能启动。
  使用物理磁盘模式和写入校验重写后恢复正常，因此后续版本继续要求保留
  `Verify` 结果。
