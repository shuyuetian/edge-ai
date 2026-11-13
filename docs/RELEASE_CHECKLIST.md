# 公开发布检查清单

检查日期：2026-11-13。

## 已完成

- [x] 当前 HEAD 不包含 SKAB 原始数据、派生夹具、模型和构建产物。
- [x] `AGENTS.md` 仅保留为本地 Codex 指令，不进入公开 Git。
- [x] `.gitignore` 排除 `data/`、模型、量化中间文件、构建和交付包。
- [x] SKAB 固定提交许可证确认为 GPLv3。
- [x] 未发现常见 API Key、私钥或密码模式。
- [x] ncnn 固定版本和 BSD 3-Clause 义务已记录。
- [x] Apache-2.0 `LICENSE`、`NOTICE` 和 ncnn/SKAB 许可证副本已加入交付包。
- [x] 静态检查、单元测试、CTest 和 ASan/UBSan 通过。
- [x] 顶层 README、架构图、板端手册和复现命令已存在。
- [x] Orange Pi 3B 4GB 已完成真实硬件精度验收和 5 轮性能基线采集。

## 发布前必须处理

- [x] 项目代码采用 Apache-2.0，根目录 `LICENSE` 和 `NOTICE` 已添加。
- [ ] 决定公开仓库是否保留现有 Git 历史。
- [ ] 配置 Git 远程仓库并推送。

## 公开上传前敏感信息门禁

以下检查全部通过并得到用户明确确认前，禁止配置 GitHub remote、执行
`git push`、上传 Release 附件或公开任何截图。扫描结果只向用户报告文件路径
和风险类型，首次输出必须遮盖实际敏感值。

- [ ] 检查所有已跟踪文件：禁止出现密码、口令、私钥、公钥授权记录、API
  Key、Token、Cookie、云服务凭据、数据库连接串和浏览器会话数据。
- [ ] 检查个人身份信息：真实姓名、个人邮箱、手机号、住址、学校/公司信息、
  账户 ID 和其他可识别个人的信息。
- [ ] 检查本机路径：`C:\Users\<用户名>`、`/home/<用户名>`、桌面路径、
  SSH 目录、下载目录及其他暴露账户名称的绝对路径。
- [ ] 检查网络与设备标识：内网 IP、公网 IP、MAC 地址、Wi-Fi SSID、板卡
  序列号、设备序列号和 USB 设备实例 ID。
- [ ] 检查提交元数据：`git log --format=fuller` 中的作者姓名和邮箱是否符合
  公开要求；如不允许公开个人邮箱，首提交前改用 GitHub noreply 地址。
- [ ] 检查截图、日志和文档：遮盖浏览器账户、终端用户名、桌面文件名、
  二维码、令牌、串口设备信息和不必要的局域网地址。
- [ ] 检查 Git 历史：不直接推送包含 SKAB 派生数据或当前工作区敏感文件的
  旧历史；优先从审核后的干净目录创建单次初始提交。
- [ ] 检查发布产物：`dist/`、`build/`、`.ssh`、`.env`、日志、模型和派生
  夹具不会因 `git add -A` 误入版本控制。
- [ ] 运行 `git ls-files`、`git grep`、`git status` 和 `git remote -v`，
  确认候选公开仓库内容与远程配置。
- [ ] 向用户展示脱敏后的扫描结论，并取得“可以上传”的明确授权。

## Git 历史中的派生数据

SKAB 派生夹具已经在提交 `08bd2f9` 从当前树删除，但旧提交 `f6be944` 仍包含：

- `train/artifacts/detector_fixture/raw_input.f32`
- `train/artifacts/detector_fixture/expected_probability.f32`
- `train/artifacts/detector_fixture/labels.i8`
- `train/artifacts/detector_fixture/metadata.json`

如果公开推送完整历史，这些对象仍会进入远程仓库。发布前可选择：

1. 从当前 HEAD 创建新的干净仓库/单次初始提交，保留原仓库为本地备份。
2. 在完整备份后使用 Git 历史清理工具移除旧对象。

不应在未备份时改写 Git 历史。

## 二进制交付包

`dist/edge-ai-arm64-stage6.tar.gz` 包含 SKAB 派生夹具和静态链接的 ncnn，
并已携带 Apache、ncnn 和 SKAB 许可证副本。当前仍定位为个人验收包；若要作为
公开 release 附件，还需确认模型和数据派生作品的再分发边界。

若未来公开发布该包，至少需要：

- 附带 SKAB GPLv3 许可证、来源、修改说明和生成源码位置。
- 附带 ncnn BSD 3-Clause 及完整第三方组件许可证。
- 核对 glibc/libstdc++/libgomp 静态分发条款。
- 提供固定源码提交和可复现构建说明。

## 路径与平台说明

脚本包含当前开发环境的固定路径：

- `D:\workspace\edge-ai`
- `/mnt/d/workspace/edge-ai`
- `/home/ubuntu/.venvs/edge-ai/bin/python`

这不会泄露凭据，但其他机器需要调整路径。README 已注明当前环境和 WSL2
依赖，不应声称这些脚本可以直接跨任意平台运行。
