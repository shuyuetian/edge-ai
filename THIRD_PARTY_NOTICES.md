# 第三方软件与数据声明

本项目代码采用 Apache License 2.0。以下第三方组件和数据仍受各自许可证约束。

## ncnn

- 项目：Tencent ncnn
- 版本：`20261020`
- 提交：`7e36d25cb153092ba87a60530455c7376fedf452`
- 上游：`https://github.com/Tencent/ncnn`
- 许可证：BSD 3-Clause，并包含若干 zlib、BSD 2-Clause 等第三方组件。

本项目不提交 ncnn 源码。构建时按固定版本重新获取：

```bash
mkdir -p third_party
git clone --depth 1 --branch 20261020 \
  https://github.com/Tencent/ncnn.git third_party/ncnn
```

如果分发包含 ncnn 的 ARM64 可执行文件或静态库，必须同时满足 ncnn 的
BSD 3-Clause 条款，并保留上游完整许可证和第三方组件声明。完整文本可从固定
版本源码的 `LICENSE.txt` 获取。

## SKAB

- 项目：Skoltech Anomaly Benchmark
- 上游：`https://github.com/waico/SKAB`
- 固定提交：`b2c0d46c2971dcbfe71e26087b6d231998bb91c2`
- DOI：`10.34740/KAGGLE/DSV/1693952`
- 许可证：GPLv3

固定提交的 `LICENSE` 与本地下载副本 SHA-256 一致：

```text
3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986
```

原始数据、窗口数据、校准集、ncnn 测试夹具和 C++ 固定夹具均视为数据或派生
数据，不进入 Git。C++ 固定夹具可在完整流水线后重新生成：

```bash
python train/export_inference_assets.py
```

交付包包含本地测试夹具，仅定位为个人开发和板端验收产物。若对外分发该包，
必须附带 GPLv3 许可证、来源、修改说明、生成源码位置，并确认模型和配置的
再分发边界。更简单的做法是不公开分发包含夹具的 tar 包。

## 编译工具链与运行时

交付二进制由 GCC 13.3、glibc、libstdc++ 和 libgomp 静态链接。GNU 工具链和
运行时组件带有各自的许可证及运行时例外条款。对外分发二进制前，应核对所使用
工具链版本的完整许可证说明。

## 项目代码

项目代码采用 Apache License 2.0，许可证全文见根目录 `LICENSE`，归属声明见
`NOTICE`。
