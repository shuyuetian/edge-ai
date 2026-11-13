# 性能回归基线

本目录只保存经过审核的真实硬件基线。当前包含 Orange Pi 3B 4GB
（RK3566）的 INT8 实机基线，不包含 QEMU 或估算数据。

- `orangepi3b-rk3566-int8-baseline.json`：2026-11-13 实测，CPU 调频策略为
  `performance`，每轮预热 30 次、计时 1,000 次，共 5 轮。

板卡首次验收完成后：

1. 运行交付包中的 `sh run_acceptance.sh`。
2. 在开发机运行 `scripts/analyze_board_results.py` 分析结果包。
3. 检查板型、CPU、系统、调频策略、温度和五轮数据。
4. 将分析输出中的 `analysis.json` 审核后复制到本目录，例如：

   `benchmarks/orangepi3b-rk3566-int8-baseline.json`

5. 再提交基线文件。

后续使用同一板型、镜像、调频策略和测试参数时，可运行：

```bash
python scripts/compare_performance.py \
  benchmarks/orangepi3b-rk3566-int8-baseline.json \
  build/new_analysis/analysis.json
```

不同镜像、调频策略、CPU 型号或测试轮数默认不能直接比较。确认环境变化是
有意为之后，才使用 `--allow-environment-change`，并在结果中记录原因。
