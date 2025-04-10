import logging
import psutil
import time
from typing import Dict
from ..base.network import NetworkStats, NetworkMonitorBase, InterfaceHealth, SocketBufferHealth, SynFloodHealth, SystemHealth, IPFragHealth, TcpCongestionHealth, TcpDisorderHealth, TcpLowLatencyHealth, TcpTimeWaitHealth, TcpQueueHealth, TcpTimestampHealth, UdpHealth
from typing import Dict, Optional, List, Tuple
from collections import defaultdict
import subprocess
import re

class LinuxNetwork(NetworkMonitorBase):
    def get_stats(self, interface: str) -> NetworkStats:
        stats = psutil.net_io_counters(pernic=True).get(interface)
        if not stats:
            raise ValueError(f"网卡 {interface} 不存在")
        
        return NetworkStats(
            bytes_sent=stats.bytes_sent,
            bytes_recv=stats.bytes_recv,
            packets_sent=stats.packets_sent,
            packets_recv=stats.packets_recv,
            errors_in=stats.errin,
            errors_out=stats.errout,
            drop_in=stats.dropin,
            drop_out=stats.dropout
        )

    def get_speed(self, interface: str, interval: float = 1.0) -> tuple[float, float]:
        start = self.get_stats(interface)
        time.sleep(interval)
        end = self.get_stats(interface)
        
        upload = (end.bytes_sent - start.bytes_sent) / interval / 1024**2
        download = (end.bytes_recv - start.bytes_recv) / interval / 1024**2
        
        return (upload, download)

    def list_interfaces(self) -> list[str]:
        return list(psutil.net_io_counters(pernic=True).keys())

    def _get_ringbuffer_settings(self, interface: str) -> tuple[int, int]:
        """获取当前ring buffer设置"""
        cmd = f"ethtool -g {interface}"
        try:
            output = subprocess.check_output(cmd, shell=True, text=True)
            rx = re.search(r"RX:\s+(\d+)", output)
            tx = re.search(r"TX:\s+(\d+)", output)
            return (int(rx.group(1)), int(tx.group(1))) if rx and tx else (0, 0)
        except subprocess.CalledProcessError:
            return (0, 0)

    def check_ringbuffer_drops(self) -> Dict[str, Optional[str]]:
        result = {}
        
        # 1. 检查/proc/net/dev丢包计数
        with open("/proc/net/dev") as f:
            for line in f:
                if ":" not in line:
                    continue
                
                ifname, data = line.split(":")
                ifname = ifname.strip()
                fields = data.split()
                
                # fifo字段是第6个值（从0开始计数）
                fifo_drops = int(fields[5]) if len(fields) > 5 else 0
                
                if fifo_drops > 0:
                    # 2. 获取ring buffer当前设置
                    rx_curr, tx_curr = self._get_ringbuffer_settings(ifname)
                    result[ifname] = (
                        f"发现 {fifo_drops} 次丢包 | "
                        f"当前RX: {rx_curr}, TX: {tx_curr} | "
                        f"建议执行: sudo ethtool -G {ifname} rx 4096 tx 4096"
                    )
                else:
                    result[ifname] = None
        
        return result


    def _parse_ifconfig(self) -> Dict[str, InterfaceHealth]:
        """解析ifconfig输出"""
        result = defaultdict(lambda: InterfaceHealth(0,0,0,0,0,0,0))
        try:
            output = subprocess.check_output("ifconfig", shell=True, text=True)
            
            current_iface = None
            for line in output.split('\n'):
                # 匹配接口名
                if not line.startswith(' '):
                    current_iface = line.split(':')[0]
                    continue
                
                # 提取RX错误指标
                if 'RX errors' in line:
                    parts = re.search(r'errors (\d+) .* dropped (\d+) .* overruns (\d+) .* frame (\d+)', line)
                    if parts and current_iface:
                        result[current_iface].rx_errors = int(parts.group(1))
                        result[current_iface].rx_dropped = int(parts.group(2))
                        result[current_iface].rx_overruns = int(parts.group(3))
                        result[current_iface].rx_frame = int(parts.group(4))
                
                # 提取TX错误指标
                elif 'TX errors' in line:
                    parts = re.search(r'errors (\d+) .* dropped (\d+) .* overruns (\d+)', line)
                    if parts and current_iface:
                        result[current_iface].tx_errors = int(parts.group(1))
                        result[current_iface].tx_dropped = int(parts.group(2))
                        result[current_iface].tx_overruns = int(parts.group(3))
        
        except subprocess.CalledProcessError:
            pass
            
        return dict(result)
    
    def _parse_softnet_stat(self) -> SystemHealth:
        """解析/proc/net/softnet_stat"""
        cpu_data = {}
        total_dropped = 0
        
        with open("/proc/net/softnet_stat") as f:
            for cpu_id, line in enumerate(f):
                fields = line.strip().split()
                processed = int(fields[0], 16)
                dropped = int(fields[1], 16)
                cpu_data[cpu_id] = (processed, dropped)
                total_dropped += dropped
        
        # 获取当前系统设置
        with open("/proc/sys/net/core/netdev_max_backlog") as f:
            backlog = int(f.read())
            
        return SystemHealth(
            netdev_max_backlog=backlog,
            cpu_queues=cpu_data
        )

    def check_interface_health(self) -> Dict[str, InterfaceHealth]:
        # 1. 先获取基础接口健康数据（调用当前类的解析方法

        health_data = self._parse_ifconfig()
        
        # 2. 添加backlog丢包检测
        sys_health = self._parse_softnet_stat()
        for iface in health_data.values():
            iface.softnet_dropped = sum(d for _, d in sys_health.cpu_queues.values())
            iface.softnet_processed = sum(p for p, _ in sys_health.cpu_queues.values())
            
        return health_data

    def get_health_advice(self, interface: str, health: InterfaceHealth) -> List[str]:
        advice = []
        
        # RX 错误诊断
        if health.rx_errors > 0:
            advice.append(f"RX errors {health.rx_errors}: 检查物理连接/网卡状态")
            
        if health.rx_dropped > 0:
            advice.append(f"RX dropped {health.rx_dropped}: "
                         "可能原因:\n"
                         "1. 系统内存不足 (检查free -m)\n"
                         "2. 协议栈处理瓶颈 (检查softnet_stat)")
            
        if health.rx_overruns > 0:
            advice.append(f"RX overruns {health.rx_overruns}: "
                         "驱动处理速度不足\n"
                         "解决方案:\n"
                         "1. 增大ring buffer: ethtool -G {interface} rx 4096\n"
                         "2. 检查CPU中断平衡: cat /proc/interrupts")
            
        if health.rx_frame > 0:
            advice.append(f"RX frame {health.rx_frame}: 检查网络物理层同步")
            
        # TX 错误诊断
        if health.tx_errors > 0:
            advice.append(f"TX errors {health.tx_errors}: 检查网线/交换机端口")
            
        if health.tx_dropped > 0:
            advice.append(f"TX dropped {health.tx_dropped}: 检查QoS/TC配置")
            
        if health.tx_overruns > 0:
            advice.append(f"TX overruns {health.tx_overruns}: "
                         "驱动队列满\n"
                         "解决方案:\n"
                         "1. 增大TX队列: ethtool -G {interface} tx 4096\n"
                         "2. 优化发送窗口: sysctl -w net.ipv4.tcp_wmem='...'")

        # 新增backlog建议
        if health.softnet_dropped > 0:
            advice.append(
                f"Backlog 丢包 {health.softnet_dropped} 次 (共处理 {health.softnet_processed} 包)\n"
                f"  建议: sudo sysctl -w net.core.netdev_max_backlog=2000\n"
                f"  永久生效: echo 'net.core.netdev_max_backlog=2000' >> /etc/sysctl.conf"
            )

        return advice
    

    def _run_sysctl(self, pattern: str) -> int:
        """获取sysctl参数值"""
        try:
            output = subprocess.check_output(
                ["sysctl", "-a"], 
                stderr=subprocess.DEVNULL,
                text=True
            )
            match = re.search(rf"{pattern}\s*=\s*(\d+)", output)
            return int(match.group(1)) if match else -1
        except:
            return -1

    def _get_arp_stats(self) -> Dict[str, int]:
        """解析/proc/net/stat/arp_cache"""
        stats = {}
        try:
            with open("/proc/net/stat/arp_cache") as f:
                headers = f.readline().split()
                values = f.readline().split()
                return dict(zip(headers, map(int, values)))
        except:
            return {}

    def check_arp_ignore(self) -> Tuple[int, List[str]]:
        """检测arp_ignore配置"""
        value = self._run_sysctl("net.ipv4.conf.all.arp_ignore")
        advice = []
        if value != 0:
            advice.append(
                "当前arp_ignore={}（可能导致ARP响应问题）\n"
                "解决方案：\n"
                "  临时设置: sudo sysctl -w net.ipv4.conf.all.arp_ignore=0\n"
                "  永久生效: echo 'net.ipv4.conf.all.arp_ignore=0' >> /etc/sysctl.conf".format(value)
            )
        return (value, advice)

    def check_arp_filter(self) -> Tuple[int, List[str]]:
        """检测arp_filter配置"""
        value = self._run_sysctl("net.ipv4.conf.all.arp_filter")
        advice = []
        if value != 0:
            advice.append(
                "当前arp_filter={}（可能导致多网卡ARP问题）\n"
                "解决方案：\n"
                "  临时设置: sudo sysctl -w net.ipv4.conf.all.arp_filter=0\n"
                "  永久生效: echo 'net.ipv4.conf.all.arp_filter=0' >> /etc/sysctl.conf".format(value)
            )
        return (value, advice)

    def check_arp_table_overflow(self) -> Tuple[bool, List[str]]:
        """检测ARP表溢出"""
        stats = self._get_arp_stats()
        current_size = int(subprocess.check_output("ip n | wc -l", shell=True, text=True))
        gc_thresh3 = self._run_sysctl("net.ipv4.neigh.default.gc_thresh3")
        advice = []
        is_overflow = False

        if stats.get("table_fulls", 0) > 0:
            is_overflow = True
            advice.append(
                "检测到ARP表溢出（table_fulls={}）\n"
                "当前ARP表大小: {}/{}\n"
                "解决方案：\n"
                "  临时调整: sudo sysctl -w net.ipv4.neigh.default.gc_thresh3=4096\n"
                "  永久生效: 将以下配置加入/etc/sysctl.conf:\n"
                "    net.ipv4.neigh.default.gc_thresh1=1024\n"
                "    net.ipv4.neigh.default.gc_thresh2=2048\n"
                "    net.ipv4.neigh.default.gc_thresh3=4096".format(
                    stats["table_fulls"], current_size, gc_thresh3
                )
            )

        return (is_overflow, advice)

    def check_arp_queue_overflow(self) -> Tuple[bool, List[str]]:
        """检测ARP请求队列溢出"""
        stats = self._get_arp_stats()
        advice = []
        is_overflow = False

        if stats.get("unresolved_discards", 0) > 0:
            is_overflow = True
            advice.append(
                "检测到ARP请求队列溢出（unresolved_discards={}）\n"
                "解决方案：\n"
                "  增加队列大小: sudo sysctl -w net.ipv4.neigh.default.unres_qlen_bytes=65536\n"
                "  永久生效: echo 'net.ipv4.neigh.default.unres_qlen_bytes=65536' >> /etc/sysctl.conf".format(
                    stats["unresolved_discards"]
                )
            )

        return (is_overflow, advice)
    
    def _get_conntrack_stats(self) -> Dict[str, int]:
        """解析/proc/net/stat/nf_conntrack"""
        stats = {}
        try:
            with open("/proc/net/stat/nf_conntrack") as f:
                headers = f.readline().split()
                values = f.readline().split()
                return dict(zip(headers, map(int, values)))
        except FileNotFoundError:
            return {}

    def _get_conntrack_count(self) -> int:
        """获取当前连接跟踪条目数"""
        try:
            output = subprocess.check_output(
                ["conntrack", "-L"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            return len(output.splitlines()) - 1  # 减去标题行
        except:
            return -1

    def check_conntrack_overflow(self) -> Tuple[bool, List[str]]:
        """检测连接跟踪表溢出"""
        advice = []
        is_overflow = False

        # 检查内核日志
        try:
            dmesg = subprocess.check_output(
                ["dmesg"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            if "ip_conntrack: table full, dropping packet" in dmesg:
                is_overflow = True
        except:
            pass

        # 检查系统参数
        try:
            with open("/proc/sys/net/netfilter/nf_conntrack_max") as f:
                max_entries = int(f.read())
            
            current = self._get_conntrack_count()
            drops = self._get_conntrack_stats().get("drop", 0)

            if drops > 0 or is_overflow:
                is_overflow = True
                advice.append(
                    "⚠️ 连接跟踪表溢出检测:\n"
                    f"  当前使用: {current}/{max_entries}\n"
                    f"  丢包统计: {drops}\n"
                    "解决方案:\n"
                    "  临时调整:\n"
                    "    sudo sysctl -w net.netfilter.nf_conntrack_max=3276800\n"
                    "    sudo sysctl -w net.netfilter.nf_conntrack_tcp_timeout_established=1200\n"
                    "  永久生效: 将以下配置加入/etc/sysctl.conf:\n"
                    "    net.netfilter.nf_conntrack_max=3276800\n"
                    "    net.netfilter.nf_conntrack_tcp_timeout_established=1200\n"
                    "    net.netfilter.nf_conntrack_udp_timeout_stream=180\n"
                    "    net.netfilter.nf_conntrack_icmp_timeout=30"
                )

        except FileNotFoundError:
            advice.append("❌ 连接跟踪模块未加载")

        return (is_overflow, advice)

    def check_conntrack_errors(self) -> Tuple[Dict[str, int], List[str]]:
        """检测CT创建失败错误"""
        stats = self._get_conntrack_stats()
        errors = {
            "insert_failed": stats.get("insert_failed", 0),
            "drop": stats.get("drop", 0),
            "invalid": stats.get("invalid", 0)
        }
        advice = []
        
        if any(errors.values()):
            advice.append(
                "⚠️ 连接跟踪错误统计:\n"
                f"  插入失败: {errors['insert_failed']}\n"
                f"  无效包丢弃: {errors['invalid']}\n"
                f"  总丢包数: {errors['drop']}\n"
                "  需要结合其他日志进一步分析"
            )

        return (errors, advice)

    def check_conntrack_aging(self) -> Tuple[bool, List[str]]:
        """检测会话老化问题"""
        advice = []
        has_issue = False
        
        try:
            with open("/proc/sys/net/netfilter/nf_conntrack_tcp_timeout_established") as f:
                timeout = int(f.read())
            
            if timeout > 86400:  # 超过1天视为不合理
                has_issue = True
                advice.append(
                    "⚠️ TCP连接跟踪超时时间过长: {}秒\n"
                    "解决方案:\n"
                    "  临时调整: sudo sysctl -w net.netfilter.nf_conntrack_tcp_timeout_established=1200\n"
                    "  永久生效: 将以下配置加入/etc/sysctl.conf:\n"
                    "    net.netfilter.nf_conntrack_tcp_timeout_established=1200".format(timeout)
                )
        except FileNotFoundError:
            pass

        return (has_issue, advice)
    
    def _get_netstat_stats(self) -> Dict[str, int]:
        """解析netstat -s输出"""
        stats = {}
        try:
            output = subprocess.check_output(
                ["netstat", "-s"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            
            # 提取关键指标
            stats["frag_timeout_drops"] = int(re.search(
                r"(\d+) fragments dropped after timeout", output
            ).group(1)) if "fragments dropped after timeout" in output else 0
            
            stats["reassembly_fails"] = int(re.search(
                r"(\d+) packet reassemblies failed", output
            ).group(1)) if "packet reassemblies failed" in output else 0

        except (subprocess.CalledProcessError, FileNotFoundError):
            stats["frag_timeout_drops"] = 0
            stats["reassembly_fails"] = 0
            
        return stats

    def _get_ipfrag_params(self) -> Dict[str, int]:
        """获取分片相关内核参数"""
        params = {}
        try:
            with open("/proc/sys/net/ipv4/ipfrag_time") as f:
                params["timeout"] = int(f.read())
            with open("/proc/sys/net/ipv4/ipfrag_high_thresh") as f:
                params["high_thresh"] = int(f.read())
            with open("/proc/sys/net/ipv4/ipfrag_low_thresh") as f:
                params["low_thresh"] = int(f.read())
        except FileNotFoundError:
            params["timeout"] = 30  # 默认值
            params["high_thresh"] = 262144
            params["low_thresh"] = 196608
            
        return params

    def check_ip_fragmentation(self) -> Tuple[IPFragHealth, List[str]]:
        """检测IP分片重组问题"""
        stats = self._get_netstat_stats()
        params = self._get_ipfrag_params()
        advice = []
        
        health = IPFragHealth(
            frag_timeout=params["timeout"],
            frag_high_thresh=params["high_thresh"],
            frag_low_thresh=params["low_thresh"],
            timeout_drops=stats["frag_timeout_drops"],
            reassembly_fails=stats["reassembly_fails"]
        )

        # 生成建议
        if health.timeout_drops > 0 or health.reassembly_fails > 0:
            advice.append(
                "⚠️ 检测到IP分片丢包:\n"
                f"  分片超时丢包: {health.timeout_drops}\n"
                f"  重组失败计数: {health.reassembly_fails}\n"
                "当前内核参数:\n"
                f"  net.ipv4.ipfrag_time={health.frag_timeout} (分片超时时间，单位秒)\n"
                f"  net.ipv4.ipfrag_high_thresh={health.frag_high_thresh} (内存中分片占用的最大内存)\n"
                f"  net.ipv4.ipfrag_low_thresh={health.frag_low_thresh} (当分片内存超过此值，内核开始尝试回收内存)\n"
                "解决方案:\n"
                "  临时调整:\n"
                "    sudo sysctl -w net.ipv4.ipfrag_time=30\n"
                "    sudo sysctl -w net.ipv4.ipfrag_high_thresh=4194304\n"
                "    sudo sysctl -w net.ipv4.ipfrag_low_thresh=3145728\n"
                "  永久生效: 将以下配置加入/etc/sysctl.conf:\n"
                "    net.ipv4.ipfrag_time=30\n"
                "    net.ipv4.ipfrag_high_thresh=4194304\n"
                "    net.ipv4.ipfrag_low_thresh=3145728"
            )

        return (health, advice)

    def check_tcp_timewait(self) -> Tuple[TcpTimeWaitHealth, List[str]]:
        """检测TCP timewait问题"""
        health = TcpTimeWaitHealth()
        advice = []
        has_issue = False

        # 1. 检查内核日志中的溢出记录
        try:
            dmesg_out = subprocess.check_output(
                ["dmesg"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            if "TCP: time wait bucket table overflow" in dmesg_out:
                health.overflow_drops = "检测到溢出丢包"
                has_issue = True
        except:
            pass

        # 2. 获取系统参数和当前状态
        try:
            # 获取最大timewait数量
            with open("/proc/sys/net/ipv4/tcp_max_tw_buckets") as f:
                health.max_tw_buckets = int(f.read().strip())
            
            # 获取当前timewait数量
            ss_out = subprocess.check_output(
                ["ss", "-tan", "state", "time-wait"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            health.current_tw = len(ss_out.splitlines()) - 1  # 减去标题行
            
            # 获取timewait超时时间
            with open("/proc/sys/net/ipv4/tcp_fin_timeout") as f:
                health.timewait_timeout = int(f.read().strip())
            
            # 生成使用率警告
            usage = (health.current_tw / health.max_tw_buckets) * 100
            if usage > 80:
                has_issue = True
                advice.append(
                    f"⚠️ TIME-WAIT连接数接近上限: {health.current_tw}/{health.max_tw_buckets} ({usage:.1f}%)"
                )
        except FileNotFoundError as e:
            advice.append(f"❌ 无法读取系统参数: {str(e)}")
            return (health, advice)

        # 3. 生成优化建议
        if has_issue or health.overflow_drops:
            advice.extend([
                "🔧 优化建议:",
                "  临时调整:",
                "    sudo sysctl -w net.ipv4.tcp_max_tw_buckets=2000000",
                "    sudo sysctl -w net.ipv4.tcp_tw_reuse=1",
                "    sudo sysctl -w net.ipv4.tcp_fin_timeout=15",
                "  永久生效 (添加到/etc/sysctl.conf):",
                "    net.ipv4.tcp_max_tw_buckets=2000000",
                "    net.ipv4.tcp_tw_reuse=1",
                "    net.ipv4.tcp_tw_recycle=0  # 在NAT环境中建议禁用",
                "    net.ipv4.tcp_fin_timeout=15",
                "  其他建议:",
                "    - 检查应用程序是否正常关闭连接",
                "    - 考虑使用连接池减少短连接"
            ])

        return (health, advice)

    def _parse_netstat_stats(self) -> Dict[str, int]:
        """解析netstat -s输出"""
        stats = {}
        try:
            output = subprocess.check_output(
                ["netstat", "-s"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            
            # 提取SYN丢弃统计
            syn_drop_match = re.search(r'(\d+) SYNs to LISTEN sockets dropped', output)
            if syn_drop_match:
                stats['syn_drops'] = int(syn_drop_match.group(1))
            
            # 提取队列溢出统计
            overflow_match = re.search(r'(\d+) times the listen queue of a socket overflowed', output)
            if overflow_match:
                stats['queue_overflows'] = int(overflow_match.group(1))
                
        except Exception as e:
            logging.warning(f"解析netstat失败: {str(e)}")
        return stats

    def _get_overflow_sockets(self, somaxconn: int) -> List[Dict]:
        """获取溢出的socket列表"""
        overflow_sockets = []
        try:
            output = subprocess.check_output(
                ["ss", "-lnt"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            
            # 跳过标题行
            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    send_q = int(parts[2])
                    if send_q > somaxconn:
                        overflow_sockets.append({
                            'local_addr': parts[3],
                            'send_q': send_q,
                            'recv_q': int(parts[1])
                        })
        except Exception as e:
            logging.warning(f"获取socket信息失败: {str(e)}")
        return overflow_sockets

    def check_tcp_queue(self) -> Tuple[TcpQueueHealth, List[str]]:
        """检测TCP队列问题"""
        health = TcpQueueHealth()
        advice = []
        has_issue = False

        # 1. 解析netstat统计信息
        stats = self._parse_netstat_stats()
        health.syn_drops = stats.get('syn_drops', 0)
        health.queue_overflows = stats.get('queue_overflows', 0)

        # 2. 获取系统参数
        try:
            with open("/proc/sys/net/core/somaxconn") as f:
                health.somaxconn = int(f.read().strip())
        except FileNotFoundError:
            health.somaxconn = None

        # 3. 检查SYN丢弃问题
        if health.syn_drops > 0:
            has_issue = True
            advice.append(
                f"⚠️ 检测到SYN丢弃: {health.syn_drops} 个SYN包被丢弃\n"
                "可能原因:\n"
                "  - TCP半连接队列(syn_backlog)已满\n"
                "解决方案:\n"
                "  1. 增大半连接队列大小:\n"
                "     sudo sysctl -w net.ipv4.tcp_max_syn_backlog=4096\n"
                "  2. 开启syncookies作为保护机制:\n"
                "     sudo sysctl -w net.ipv4.tcp_syncookies=1\n"
                "  3. 检查是否遭受SYN Flood攻击"
            )

        # 4. 检查全连接队列溢出
        if health.queue_overflows > 0:
            has_issue = True
            msg = [
                f"⚠️ 检测到连接队列溢出: {health.queue_overflows} 次溢出",
                f"当前系统somaxconn值: {health.somaxconn or '未知'}"
            ]
            
            # 获取溢出的socket详情
            if health.somaxconn:
                health.overflow_sockets = self._get_overflow_sockets(health.somaxconn)
                if health.overflow_sockets:
                    msg.append("溢出的socket列表:")
                    for sock in health.overflow_sockets:
                        msg.append(
                            f"  - 本地地址: {sock['local_addr']} "
                            f"Send-Q: {sock['send_q']} "
                            f"Recv-Q: {sock['recv_q']}"
                        )
            
            msg.extend([
                "可能原因:",
                "  - 应用程序backlog设置不合理",
                "  - 服务端处理能力不足",
                "解决方案:",
                "  1. 应用程序调整:",
                "     - 增大listen()的backlog参数",
                "     - 优化服务处理性能",
                "  2. 系统参数调整:",
                "     sudo sysctl -w net.core.somaxconn=4096",
                "  3. 紧急处理(可能断开连接):",
                "     sudo sysctl -w net.ipv4.tcp_abort_on_overflow=1"
            ])
            advice.append("\n".join(msg))

        return (health, advice)

    def check_syn_flood(self) -> Tuple[SynFloodHealth, List[str]]:
        """检测SYN Flood攻击"""
        health = SynFloodHealth()
        advice = []
        health.attack_ports = []

        # 1. 检查dmesg日志中的SYN Flood记录
        try:
            dmesg_out = subprocess.check_output(
                ["dmesg"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            
            # 使用正则匹配所有受攻击端口
            flood_matches = re.finditer(
                r'Possible SYN flooding on port (\d+).*', 
                dmesg_out
            )
            
            for match in flood_matches:
                health.detected = True
                port = match.group(1)
                if port not in health.attack_ports:
                    health.attack_ports.append(port)
                    advice.append(
                        f"⚠️ 检测到SYN Flood攻击迹象 - 端口: {port}\n"
                        f"  完整日志: {match.group(0).strip()}"
                    )
        except Exception as e:
            logging.warning(f"检查dmesg失败: {str(e)}")

        # 2. 获取当前系统参数
        try:
            with open("/proc/sys/net/ipv4/tcp_max_syn_backlog") as f:
                health.current_backlog = int(f.read().strip())
            
            with open("/proc/sys/net/ipv4/tcp_synack_retries") as f:
                health.current_synack_retries = int(f.read().strip())
        except FileNotFoundError:
            pass

        # 3. 生成防御建议
        if health.detected:
            advice.extend([
                "\n🔧 SYN Flood防御建议:",
                "1. 增大半连接队列:",
                f"   当前值: {health.current_backlog or '默认'}",
                "   sudo sysctl -w net.ipv4.tcp_max_syn_backlog=4096",
                "",
                "2. 减少SYN+ACK重试次数(加速释放半连接):",
                f"   当前值: {health.current_synack_retries or '默认'}",
                "   sudo sysctl -w net.ipv4.tcp_synack_retries=2",
                "",
                "3. 启用SYN Cookies保护:",
                "   sudo sysctl -w net.ipv4.tcp_syncookies=1",
                "",
                "4. 紧急处理(可能影响用户体验):",
                "   sudo sysctl -w net.ipv4.tcp_abort_on_overflow=1",
                "",
                "技术说明:",
                "- tcp_max_syn_backlog: 控制半连接队列大小",
                "- tcp_synack_retries: 减少可限制攻击持续时间",
                "- tcp_syncookies: 在队列满时不丢弃连接",
                "- tcp_abort_on_overflow: 直接拒绝连接但可能导致合法用户受影响"
            ])

        return (health, advice)
    
    def check_tcp_timestamp(self) -> Tuple[TcpTimestampHealth, List[str]]:
        """检测TCP时间戳机制导致的丢包"""
        health = TcpTimestampHealth()
        advice = []
        has_issue = False

        # 1. 检查netstat统计信息
        try:
            netstat_out = subprocess.check_output(
                ["netstat", "-s"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            
            # 检查被动连接拒绝
            passive_match = re.search(
                r'(\d+) passive connections rejected because of time stamp',
                netstat_out
            )
            if passive_match:
                health.rejected_passive = int(passive_match.group(1))
                has_issue = True
            
            # 检查已建立连接拒绝
            established_match = re.search(
                r'(\d+) packets rejects in established connections because of timestamp',
                netstat_out
            )
            if established_match:
                health.rejected_established = int(established_match.group(1))
                has_issue = True
                
        except Exception as e:
            logging.warning(f"检查netstat失败: {str(e)}")

        # 2. 检查当前系统参数
        try:
            with open("/proc/sys/net/ipv4/tcp_tw_recycle") as f:
                health.tcp_tw_recycle = bool(int(f.read().strip()))
        except FileNotFoundError:
            health.tcp_tw_recycle = None

        # 3. 生成建议
        if has_issue:
            advice.append(
                "⚠️ 检测到TCP时间戳机制导致的连接拒绝:\n"
                f"  被动连接拒绝: {health.rejected_passive or 0}\n"
                f"  已建立连接拒绝: {health.rejected_established or 0}\n"
                f"  当前tcp_tw_recycle状态: {health.tcp_tw_recycle if health.tcp_tw_recycle is not None else '未知'}"
            )
            
            advice.extend([
                "\n🔧 解决方案 (NAT环境建议):",
                "1. 禁用时间戳快速回收 (推荐):",
                "   sudo sysctl -w net.ipv4.tcp_tw_recycle=0",
                "",
                "2. 完全禁用TCP时间戳 (可能影响性能):",
                "   sudo sysctl -w net.ipv4.tcp_timestamps=0",
                "",
                "技术说明:",
                "- 在NAT环境下，不同机器可能共享相同IP但时间戳不同",
                "- tcp_tw_recycle会基于时间戳拒绝非递增的包",
                "- 解决方案1更推荐，因为时间戳对TCP性能有重要优化作用"
            ])

        return (health, advice)
    
    def check_tcp_disorder(self) -> Tuple[TcpDisorderHealth, List[str]]:
        """待实现的TCP乱序检测"""
        health = TcpDisorderHealth()
        advice = [
            "⏳ 待实现功能: TCP乱序丢包检测",
            "规划检测方法:",
            "1. 解析/proc/net/netstat中的TCPReorder字段",
            "2. 监控ss -i输出中的reordering参数",
            "3. 分析netstat -s中的快速重传统计",
            "",
            "典型解决方案可能包括:",
            "- 调整tcp_reordering参数",
            "- 检查网络设备缓冲设置",
            "- 排查中间设备乱序问题"
        ]
        return (health, advice)

    def check_tcp_congestion(self) -> Tuple[TcpCongestionHealth, List[str]]:
        """待实现的拥塞控制检测"""
        health = TcpCongestionHealth()
        advice = [
            "⏳ 待实现功能: TCP拥塞控制丢包检测",
            "规划检测方法:",
            "1. 解析/proc/net/netstat中的TCPLoss字段",
            "2. 监控ss -i中的cwnd和ssthresh值",
            "3. 分析tcpprobe或perf trace数据",
            "",
            "典型解决方案可能包括:",
            "- 更换拥塞控制算法(cubic/bbr等)",
            "- 调整tcp_window_scaling参数",
            "- 优化缓冲区大小设置"
        ]
        return (health, advice)

    def check_tcp_low_latency(self) -> Tuple[TcpLowLatencyHealth, List[str]]:
        """低时延场景TLP检测(部分实现)"""
        health = TcpLowLatencyHealth()
        advice = []

        # 1. 获取当前early_retrans配置
        try:
            output = subprocess.check_output(
                ["sysctl", "-a", "net.ipv4.tcp_early_retrans"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            match = re.search(r'tcp_early_retrans\s*=\s*(\d+)', output)
            if match:
                health.early_retrans = int(match.group(1))
                advice.append(f"当前tcp_early_retrans值: {health.early_retrans}")
        except Exception as e:
            logging.warning(f"获取sysctl配置失败: {str(e)}")
            advice.append("❌ 无法获取tcp_early_retrans配置")

        # 2. 打桩部分
        advice.extend([
            "\n⏳ 待完善检测项:",
            "1. TLP无效重传统计 (需内核tracepoint支持)",
            "2. 延迟ACK交互检测 (需分析包序时间戳)",
            "",
            "⚠️ 已知问题现象:",
            "- 在RTT < 10ms的超低延迟网络中",
            "- 当TLP与延迟ACK机制同时作用时",
            "- 可能导致虚假重传超时",
            "",
            "🔧 研究方向:",
            "- 调整/proc/sys/net/ipv4/tcp_early_retrans (当前已获取)",
            "- 禁用延迟ACK (可能影响性能)",
            "- 优化TLP探测间隔"
        ])

        return (health, advice)
    
    def check_udp_loss(self) -> Tuple[UdpHealth, List[str]]:
        """待实现的UDP丢包检测"""
        health = UdpHealth()
        advice = [
            "⏳ 待实现功能: UDP丢包检测",
            "规划检测方法:",
            "1. 解析/proc/net/snmp中的UDP统计项: InErrors, RcvbufErrors",
            "2. 监控ifconfig中的RX/TX errors计数",
            "3. 使用ss -uamp获取UDP socket状态",
            "",
            "典型解决方案可能包括:",
            "- 调整net.core.rmem_max/rmem_default",
            "- 优化应用程序接收逻辑",
            "- 检查网络设备队列设置"
        ]
        return (health, advice)

    def check_socket_buffer(self) -> Tuple[SocketBufferHealth, List[str]]:
        """待实现的Socket缓冲区检测"""
        health = SocketBufferHealth()
        advice = [
            "⏳ 待实现功能: Socket缓冲区丢包检测",
            "规划检测方法:",
            "1. 解析/proc/net/udp中的drops字段",
            "2. 监控/proc/sys/net/ipv4/udp_mem压力值",
            "3. 分析/proc/net/sockstat中的内存使用",
            "",
            "典型解决方案可能包括:",
            "- 增大net.core.rmem_max/wmem_max",
            "- 调整应用程序SO_RCVBUF大小",
            "- 优化内核内存分配参数"
        ]
        return (health, advice)
