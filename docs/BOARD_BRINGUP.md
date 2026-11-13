# Orange Pi 3B 首次启动与板端验收

本文用于 Orange Pi 3B 4GB 首次上电、系统烧录、串口登录、SSH 部署和本项目的
板端验收。官方资源链接于 2026-11-03 核对；本文流程已于 2026-11-13 在
Orange Pi 3B 4GB（RK3566）上完成实际验证。

本次结果：Debian 12 Server 正常启动，SSH 可用，481 窗口验收通过；
CPU 固定 `performance` 调频时，五轮中位数均值 `0.222374 ms`、
P95 `0.240042 ms`、峰值 RSS `4,568 KiB`。完整数据见
[RESULTS.md](RESULTS.md)，回归基线见
[`benchmarks/orangepi3b-rk3566-int8-baseline.json`](../benchmarks/orangepi3b-rk3566-int8-baseline.json)。

## 官方入口

Orange Pi 官网的 HTTPS 端口从当前网络连接会被拒绝，但 HTTP 页面可访问。
不要从网盘页面输入项目账号或密码。

- [中文产品页](http://www.orangepi.cn/html/hardWare/computerAndMicrocontrollers/details/Orange-Pi-3B.html)
- [中文下载页](http://www.orangepi.cn/html/hardWare/computerAndMicrocontrollers/service-and-support/Orange-Pi-3B.html)
- [英文产品页](http://www.orangepi.org/html/hardWare/computerAndMicrocontrollers/details/Orange-Pi-3B.html)
- [英文下载页](http://www.orangepi.org/html/hardWare/computerAndMicrocontrollers/service-and-support/Orange-Pi-3B.html)
- [官方 Wiki](http://wiki.orangepi.cn)

官方 3B 下载页提供用户手册、Ubuntu 镜像和 Debian 镜像的网盘入口。公开文档
不复制网盘提取码，请从官方下载页获取最新链接。

英文站备用入口：

- [用户手册（Google Drive）](https://drive.google.com/drive/folders/18YyPnq_f0gbdNlbsNmzouFPxin08C_gf?usp=sharing)
- [Ubuntu 镜像（Google Drive）](https://drive.google.com/drive/folders/1hWsiaEmjiRFjGMrOw6Z3UoyxGz97Tgve?usp=sharing)
- [Debian 镜像（Google Drive）](https://drive.google.com/drive/folders/1-mcXPDx1QpE9ZI8oTivmJ1Nd5HfU5nFv?usp=sharing)

当前网络可打开官网页面，但连接 Google Drive 超时。优先使用中文官网的百度
网盘镜像；若网盘链接失效，再向 Orange Pi 官方店客服索取当前镜像。

## 已验证镜像与手册

2026-11-04 已下载并解压：

- 原始归档：`<下载目录>\Debian\Orangepi3b_1.0.8_debian_bookworm_server_linux5.10.160.7z`
- 归档大小：`785,466,658` 字节
- 归档 SHA-256：
  `fe0d6a80bc629b8cc628f3882c3480913f4911172185efaf47eb2a76226df3e3`
- 解压镜像：`<仓库>\dist\orangepi3b-image\Orangepi3b_1.0.8_debian_bookworm_server_linux5.10.160.img`
- 解压镜像大小：`5,049,942,016` 字节
- 解压镜像 SHA-256：
  `005cf48d72c5343479e945671e1929e5b86a302d90bc6098551dd254531eed35`

归档中的 `.img.sha` 与重新计算的镜像 SHA-256 一致。选择 Debian 12 Server
和 Linux 5.10 BSP，是因为它比 Linux 6.6.0-rc5 更适合稳定性能基线。

2026-11-13 已使用 USBImager 1.0.10 写入 64GB microSD，工具报告用时
`00:11:21` 并显示“镜像已成功写入”。写后 Windows 识别结果为：

- 物理磁盘：USB Mass Storage Device
- 分区表：GPT
- 分区 1：偏移 `31,457,280` 字节，大小 `1,073,741,824` 字节
- 分区 2：偏移 `1,105,199,104` 字节，大小 `3,944,726,016` 字节

分区结束位置与镜像大小一致；Windows 不再识别原来的单分区 exFAT，符合
Linux 镜像写入结果。

- 用户手册：`OrangePi_3B_RK3566_用户手册_v1.9.pdf`
- 已复制到：`<仓库>\dist\orangepi3b-image\OrangePi_3B_RK3566_用户手册_v1.9.pdf`
- 手册大小：`27,486,633` 字节
- 手册 SHA-256：
  `8cb559d711ec53a80aae51f90cabe125ae7b6f2213747653f843b5a479dadba3`

## 镜像选择依据

官方产品页声明 Orange Pi 3B 支持 Ubuntu 22.04、Ubuntu 20.04、Debian 11
和 Debian 12。本项目已选用 Debian 12 Server + Linux 5.10 BSP，避免桌面
环境占用内存，也避免把 6.6-rc5 预发布内核作为性能基线。

其他镜像只有在需要对照实验时才使用，并必须记录镜像名称、内核和 SHA-256。
镜像必须明确对应 Orange Pi 3B、64 位/aarch64，且优先使用 Server、CLI 或
Minimal 版本。


## 烧录 microSD

1. 使用 32GB 或 64GB 品牌 microSD，优先 A1/A2、U3。
2. 使用 Balena Etcher 等工具直接写入 `.img`、`.img.xz` 或 `.img.gz`，
   不需要手工格式化或解压。
3. 烧录完成后按操作系统要求安全弹出读卡器。
4. 板卡断电后再插入 microSD，不能带电插拔系统卡。

不要使用来历不明的“优化镜像”或第三方整合包。需要第三方系统时，先用
独立卡片验证，不要把第三方镜像结果混入本项目基线。

## 组装与供电

官方产品页给出的相关规格：

- 电源：Type-C 5V/3A。
- 风扇接口：2Pin、1.25mm、5V。
- 板载千兆网口。

组装前断开电源，并先接触接地金属释放静电。
电源接口不支持 PD 协商，不能接入高于 5V 的电源，也不能用电脑 USB 口给
开发板供电。启动时反复重启通常首先检查电源和线材。

1. 安装兼容 Orange Pi 3B 的散热片或风扇外壳。
2. 核对风扇为 5V，插头和正负极与板端一致，禁止强行反插。
3. 插入已烧录的 microSD。
4. 连接网线；串口或 HDMI 作为首次登录通道。
5. 最后连接官方 5V/3A 电源。

若风扇不转或板子反复重启，立即断电检查电源、风扇接口和短路。

## 串口调试

使用正点原子 MO340P 或等效 USB-TTL 模块：

- 电平开关设为 `3.3V`。
- 官方推荐 CH340，不建议使用 CP2102/PL2303；模块必须支持 `1,500,000` 波特率。
- Orange Pi 3B 调试串口为 UART2，波特率 `1,500,000`，流控关闭。
- USB-TTL `GND` 接板子 `GND`。
- USB-TTL `RXD` 接板子 `TXD`。
- USB-TTL `TXD` 接板子 `RXD`。
- 不连接 `VCC/3.3V`，板子由独立电源供电。

板卡上的调试串口丝印为 `GND`、`RXD`、`TXD`，位于 USB/HDMI 一侧。MO340P
需要确认其芯片和驱动能够稳定支持 1.5 Mbps；不满足时更换为满足要求的 CH340
模块。

Windows 开发机可先短接 USB-TTL 的 TX/RX 做回环验证，再接入开发板：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_serial_loopback.ps1 `
  -PortName COM5 -BaudRate 1500000
```

启动日志可用仓库脚本保存：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\capture_serial.ps1 `
  -PortName COM5 -BaudRate 1500000 `
  -OutputPath build\orangepi_serial_boot.log -TimeoutSeconds 180
```

## 首次启动检查

接通串口或 HDMI 和网线后上电。官方 v1.9 手册给出的默认账号为：

- `root` / `orangepi`
- `orangepi` / `orangepi`

首次登录后应立即修改默认密码。官方镜像默认开启 SSH，并允许 root 登录；
只应在可信本地网络中临时使用，采集完成后关闭不需要的远程登录权限。

登录后记录：

```sh
uname -m
getconf LONG_BIT
free -h
cat /etc/os-release
ip -4 address
df -h
```

预期：

- `uname -m` 输出 `aarch64`。
- `getconf LONG_BIT` 输出 `64`。
- `free -h` 显示约 4GB 内存。
- 有线网口取得 IPv4 地址。

首次性能基线前不要执行完整 `apt upgrade`。内核或驱动升级可能改变功耗和
性能；如需升级，应先记录当前镜像版本，再重新测量并明确标注环境变化。

## SSH 与交付包

从开发机复制交付包：

```powershell
scp .\dist\edge-ai-arm64-stage6.tar.gz <用户名>@<板卡IP>:/home/<用户名>/
```

登录板卡：

```sh
ssh <用户名>@<板卡IP>
```

然后执行：

```sh
tar -xzf edge-ai-arm64-stage6.tar.gz
cd edge-ai-arm64-stage6
sha256sum -c SHA256SUMS
sh run_acceptance.sh
```

脚本默认：

- 运行 481 窗口精度与决策一致性验收。
- 预热 30 次、计时 1,000 次，共运行 5 轮。
- 记录测试前后 CPU 频率、温度和系统信息。
- 生成 `results/board_results_<时间>.tar.gz`。

把结果包复制回电脑：

```powershell
scp <用户名>@<板卡IP>:~/edge-ai-arm64-stage6/results/board_results_*.tar.gz .\dist\
```

在电脑上分析：

```bash
python scripts/analyze_board_results.py dist/board_results_<时间>.tar.gz
```

## 故障排查

### 无串口输出

- 确认串口模块是 3.3V。
- 确认 TX/RX 交叉连接且 GND 相连。
- 确认没有连接 VCC。
- 核对官方手册中的 UART 引脚和串口参数。
- 确认 microSD 烧录成功，镜像对应 Orange Pi 3B。

### 有启动日志但无法 SSH

- 检查网线指示灯和路由器 DHCP 客户端列表。
- 在串口执行 `ip -4 address`。
- 确认镜像安装了 SSH 服务。
- 检查用户名、密码和首次启动配置。
- 直连 Windows 网口时，需要先确认板端和开发机网卡位于同一子网。不要把
  实际内网地址、SSID 或设备序列号写进公开文档。

### U-Boot 报主 GPT 错误

若日志出现：

```text
GUID Partition Table Entry Array CRC is wrong
*** ERROR: Invalid GPT ***
*** Using Backup GPT ***
```

优先重新校验源镜像，然后使用写卡工具的物理磁盘模式重写整张卡并启用写入
校验。本项目首次烧录时曾出现该错误，U-Boot 只能回退到备用 GPT，Linux
未能完成启动；重写主 GPT 后恢复正常。不要先怀疑板卡、电源或串口接线。

### 随机重启或风扇异常

- 使用独立、稳定的 Type-C 5V/3A 电源。
- 检查风扇电压、正负极和接口尺寸。
- 移除短路风险，使用绝缘柱或外壳。
- 记录串口日志，不继续运行性能测试。

### 能推理但性能明显波动

- 在结果中检查 `scaling_governor`、当前频率和温度。
- 确认风扇工作、散热片贴合芯片。
- 不在后台运行软件更新、编译或其他高负载任务。
- 将异常轮次和完整日志保留，不手工删除不利结果。

## 验收完成后的记录

真机结果写入 [RESULTS.md](RESULTS.md) 时必须包含：

- Orange Pi 3B 4GB / RK3566 型号
- 镜像文件名和系统版本
- CPU 调频策略、温度
- 五轮均值、P95、P99 和 RSS
- `run_acceptance.sh` 命令与原始终止时间
- 测量日期

在真实硬件数据产生前，项目仍只能写“通过 QEMU 交叉验证”。
