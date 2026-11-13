# v1.0.0 发布说明

发布日期：2026-11-13

这是端侧 AI 异常检测项目的首个封版版本。版本范围覆盖从 SKAB 数据处理、
PyTorch 训练、ONNX 导出、ncnn INT8 量化，到 AArch64 静态交付包和
Orange Pi 3B 真机验收的完整链路。

## 真机结果

- 开发板：Orange Pi 3B 4GB，Rockchip RK3566
- 系统：Orange Pi 1.0.8 Bookworm，Linux 5.10.160-rockchip-rk356x
- CPU：4 × Cortex-A55，1.8 GHz，测试时使用 `performance` 调频策略
- 精度验收：481 个测试窗口，决策一致率 `1.000000`，F1 `0.836013`
- 单窗口平均延迟中位数：`0.222374 ms`
- P95：`0.240042 ms`
- P99：`0.278541 ms`
- 峰值 RSS：`4,568 KiB`
- 测试前后 SoC 温度：`39.444°C` 到 `40.625°C`

正式基线为 5 轮，每轮预热 30 次、计时 1,000 次，模型配置为 4 线程。
测试结束后已将 CPU 调频策略恢复为 `ondemand`。

## 交付产物

- ARM64 交付包：`dist/edge-ai-arm64-stage6.tar.gz`
- ARM64 交付包 SHA-256：
  `a90a2a339d1cbdc35b136c55c54085331da240b0e53a2e6373c1f926ec8483ad`
- 真机原始结果包：`dist/board_results_20261113_222845.tar.gz`
- 真机原始结果包 SHA-256：
  `9a8c9b7958258368789b42514be8edad8c909065f27f207c80281330f644edd5`
- 回归基线：`benchmarks/orangepi3b-rk3566-int8-baseline.json`

交付包内的 AArch64 二进制已与板端实际验收版本逐项核对 SHA-256，二进制和模型
完全一致。交付包的 `BUILD_INFO.txt` 标记 `board_validation=passed`。

## 验证范围

- Python 脚本单元测试通过。
- C++ CTest 通过。
- ShellCheck 和 PowerShell 语法检查通过。
- 交付包内全部 SHA-256 校验通过。
- 解压后的 ARM64 交付包通过 QEMU 精度与短基准冒烟验收。
- Orange Pi 3B 真机完成 481 窗口精度验收和 5 轮性能采集。

完整数据、测量命令、环境和五轮明细见 `docs/RESULTS.md`。

## 已知限制

- 当前推理仅使用 RK3566 CPU 和 ncnn，没有启用或验证 NPU。不得将本版本
  数据描述为 NPU 加速结果。
- 板端镜像仍使用发行版默认密码，首次使用前必须执行 `passwd` 修改。
- ARM64 包包含 SKAB 派生夹具，只定位为本地验收产物。公开发布或再分发前，
  必须重新审核 GPLv3、来源、修改说明和对应生成源码。
- 仓库旧 Git 历史曾包含已从当前树删除的派生数据。在清理历史或创建干净新
  仓库前，不应推送完整历史。
- 本版本按照用户要求只保存在本地，不推送 GitHub，也不创建远程 Release。

## 复现

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_static.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_stage6_package.ps1 -BoardValidation passed
```

板端：

```sh
sha256sum -c SHA256SUMS
sh run_acceptance.sh
```
