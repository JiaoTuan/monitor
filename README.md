# Linux System Performance And Stability Monitor

[![Python Version](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

一个基于 eBPF 和 Python 的 Linux 系统性能与稳定性监控工具，提供深度网络诊断、TCP/UDP 协议栈分析和内核参数优化建议。

## 功能特性

### 🔍 网络诊断

- **接口健康检查** - 监控网卡 RX/TX 错误、丢包、过载
- **Ring Buffer 检测** - 检测网卡缓冲区丢包情况
- **ARP 系统诊断** - ARP 配置检查、表溢出检测
- **连接跟踪诊断** - Conntrack 表和队列状态监测
- **IP 分片重组** - 分片超时和重组失败检测

### 🚀 TCP 协议栈分析

- **TIME-WAIT 诊断** - 监控 TCP TIME-WAIT 状态连接
- **队列诊断** - SYN 队列和全连接队列监测
- **SYN Flood 检测** - 攻击防护状态检查
- **时间戳机制** - 时间戳导致丢包检测
- **乱序丢包** - TCP 乱序包处理问题诊断
- **拥塞控制** - TCP 拥塞控制算法检测
- **低时延优化** - 网络低延迟配置检查

### 📊 UDP 分析

- **丢包检测** - UDP 丢包统计和分析

### ⚙️ 系统资源监控

- **Socket 缓冲区** - 缓冲区配置和使用情况
- **实时网速** - 网卡上传/下载速度监控
- **网络统计** - 累计流量、错误率、丢包率统计

## 项目架构

```
monitor/
├── core/                    # 核心监控模块
│   ├── base/               # 基础接口定义
│   │   ├── network.py      # 网络监控抽象类
│   │   ├── cpu.py
│   │   ├── memory.py
│   │   ├── storage.py
│   │   └── system.py
│   ├── linux/              # Linux 平台实现
│   │   └── network.py      # Linux 网络监控实现
│   └── android/            # Android 平台支持
├── lpm/                     # 命令行工具
│   ├── cli.py              # 主命令行接口
│   └── utils/              # 工具函数
├── tools/                   # 辅助工具
│   ├── bpf/                # eBPF 程序
│   ├── ftrace/             # Ftrace 工具
│   └── perfetto/           # Perfetto 分析工具
└── libbpf-bootstrap/       # eBPF 开发框架
    ├── libbpf/             # libbpf 库
    ├── bpftool/            # BPF 工具
    └── examples/           # eBPF 示例
```

## 快速开始

### 环境要求

- Ubuntu 20.04+ / Debian 11+ / 其他 Linux 发行版
- Python 3.6+
- LLVM/Clang 10+
- Linux 内核 5.8+（支持 eBPF）

### 安装依赖

```bash
# 系统依赖
apt-get update
apt-get install -y \
    clang \
    libelf1 \
    libelf-dev \
    zlib1g-dev \
    libcap-dev \
    python3 \
    python3-pip

# Python 依赖
pip3 install click psutil rich
```

### 构建

```bash
# 克隆仓库（包含子模块）
git clone --recurse-submodules https://github.com/JiaoTuan/monitor.git
cd monitor

# 构建 eBPF 工具
cd tools/bpf/
make
cd ../..

# 或使用 libbpf-bootstrap 构建
cd libbpf-bootstrap/examples/c
make -j$(nproc)
cd ../../..
```

### 运行

```bash
# 列出所有可用网卡
python3 lpm/cli.py --list

# 实时监控指定网卡
python3 lpm/cli.py --interface eth0 --interval 1.0

# 运行完整诊断检查
python3 lpm/cli.py --check

# 详细诊断模式
python3 lpm/cli.py --check --verbose

# 对特定网卡的诊断
python3 lpm/cli.py --check --interface eth0 --verbose
```

## 使用示例

### 基础监控

```bash
# 监控 eth0 网卡，每 2 秒刷新
python3 lpm/cli.py --interface eth0 --interval 2.0
```

输出示例：
```
📶 网卡 [eth0]
   📤 实时: 10.50↑ 25.30↓ MB/s
   📊 累计: 1024.5↑ 2048.3↓ MB
   ⚠️ 错误: 输入0 输出0
   ❌ 丢包: 输入0 输出0
```

### 网络诊断

```bash
# 完整的网络健康检查
python3 lpm/cli.py --check --verbose
```

诊断项包括：
- Ring Buffer 丢包检查
- 网卡接口健康检查
- ARP 系统诊断
- Conntrack 连接跟踪
- IP 分片重组
- TCP TIME-WAIT 状态
- TCP 队列溢出
- SYN Flood 攻击检测
- TCP 时间戳机制
- UDP 丢包检测
- Socket 缓冲区配置

## 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--list` | 列出所有网卡 | `--list` |
| `--interval` | 监控刷新间隔（秒） | `--interval 2.0` |
| `--interface` | 指定监控的网卡 | `--interface eth0` |
| `--check` | 运行完整诊断检查 | `--check` |
| `--verbose` | 显示详细诊断信息 | `--verbose` |

## 诊断功能详解

### Ring Buffer 检测
检测网卡驱动的 Ring Buffer 是否有丢包，并提供 ethtool 调优建议。

### 接口健康检查
监控以下指标：
- RX 错误、丢包、过载
- TX 错误、丢包、过载
- Softnet 丢包

### TCP TIME-WAIT 诊断
- 检测 TIME-WAIT 连接数
- 监控超时时间配置
- 检测溢出丢包

### SYN Flood 防护
- 检测 `tcp_max_syn_backlog` 设置
- 监控 `tcp_synack_retries` 配置
- 识别受攻击端口

### ARP 系统检查
- 验证 `arp_ignore` 配置
- 检查 `arp_filter` 设置
- 监控 ARP 表和队列溢出

## 性能优化建议

基于诊断结果，工具会提供以下优化建议：

### 临时调整
```bash
# 增加 Ring Buffer 大小
ethtool -G eth0 rx 4096

# 调整 TCP 参数
echo 4096 > /proc/sys/net/ipv4/tcp_max_syn_backlog
```

### 永久生效
编辑 `/etc/sysctl.conf`：
```bash
# TCP 优化
net.ipv4.tcp_max_syn_backlog = 4096
net.ipv4.tcp_synack_retries = 2
net.core.somaxconn = 65535

# Ring Buffer 检查
watch -n 1 'ethtool -S eth0 | grep drop'
```

## 与 eBPF 集成

该工具使用 eBPF 技术实现深度网络监控：

- **libbpf** - 用于加载和管理 eBPF 程序
- **bpftool** - 用于 eBPF 程序调试和分析
- **vmlinux.h** - 内核数据结构定义

eBPF 程序位置：[tools/bpf/](tools/bpf/)

## 文件说明

| 文件 | 说明 |
|------|------|
| [lpm/cli.py](lpm/cli.py) | 命令行接口主程序 |
| [core/base/network.py](core/base/network.py) | 网络监控抽象接口 |
| [core/linux/network.py](core/linux/network.py) | Linux 网络监控实现 |
| [tools/bpf/](tools/bpf/) | eBPF 程序源代码 |

## 常见问题

### Q: 运行时提示权限不足？
A: 该工具需要 root 权限来访问内核参数和网络统计信息。
```bash
sudo python3 lpm/cli.py --check
```

### Q: 如何查看 eBPF 程序的输出？
A: 检查内核日志：
```bash
sudo dmesg | tail -20
sudo cat /sys/kernel/debug/tracing/trace
```

### Q: 支持哪些网卡？
A: 支持所有标准 Linux 网络接口（eth*, wlan*, etc）。

## 贡献指南

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License - 详见 [LICENSE](LICENSE)

## 参考资源

- [libbpf 官方文档](https://github.com/libbpf/libbpf)
- [BPF CO-RE 参考指南](https://nakryiko.com/posts/bpf-core-reference-guide/)
- [Linux 网络栈优化](https://www.kernel.org/doc/html/latest/networking/)
- [TCP/IP 详解](https://en.wikipedia.org/wiki/TCP/IP_model)


