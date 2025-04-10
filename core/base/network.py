from abc import ABC, abstractmethod
from typing import NamedTuple, Dict
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass

class NetworkStats(NamedTuple):
    """单网卡统计信息"""
    bytes_sent: int      # 发送字节数
    bytes_recv: int      # 接收字节数
    packets_sent: int    # 发送包数
    packets_recv: int    # 接收包数
    errors_in: int       # 输入错误数
    errors_out: int      # 输出错误数
    drop_in: int         # 输入丢包数
    drop_out: int        # 输出丢包数

@dataclass
class InterfaceHealth:
    rx_errors: int
    rx_dropped: int
    rx_overruns: int
    rx_frame: int
    tx_errors: int
    tx_dropped: int
    tx_overruns: int
    softnet_dropped: int = 0  # 新增：backlog丢包计数
    softnet_processed: int = 0  # 新增：已处理包数

@dataclass
class ARPHealth:
    """ARP相关健康状态"""
    arp_ignore: Optional[int] = None
    arp_filter: Optional[int] = None
    arp_table_size: Optional[int] = None
    arp_table_max: Optional[int] = None  # gc_thresh3值
    arp_cache_unresolved: Optional[int] = None  # 未解决丢弃数
    arp_cache_overflows: Optional[int] = None  # table_fulls值

@dataclass
class ConntrackHealth:
    """连接跟踪健康状态"""
    table_max: Optional[int] = None       # nf_conntrack_max
    table_usage: Optional[int] = None    # 当前使用量
    table_drops: Optional[int] = None    # 因表满导致的丢包数
    tcp_timeout: Optional[int] = None    # TCP会话超时时间
    errors: Dict[str, int] = None        # 各种错误统计

@dataclass
class IPFragHealth:
    """IP分片健康状态"""
    frag_timeout: Optional[int] = None      # ipfrag_time
    frag_high_thresh: Optional[int] = None  # ipfrag_high_thresh
    frag_low_thresh: Optional[int] = None   # ipfrag_low_thresh
    timeout_drops: Optional[int] = None     # fragments dropped after timeout
    reassembly_fails: Optional[int] = None  # packet reassemblies failed

@dataclass
class TcpTimeWaitHealth:
    """TCP timewait 健康状态"""
    max_tw_buckets: Optional[int] = None    # tcp_max_tw_buckets
    current_tw: Optional[int] = None        # 当前timewait数量
    overflow_drops: Optional[int] = None    # 因溢出导致的丢包数
    timewait_timeout: Optional[int] = None  # TIME_WAIT超时时间

@dataclass
class SynFloodHealth:
    """SYN Flood攻击检测状态"""
    detected: bool = False
    attack_ports: List[str] = None      # 受攻击的端口列表
    current_backlog: Optional[int] = None  # 当前tcp_max_syn_backlog值
    current_synack_retries: Optional[int] = None  # 当前tcp_synack_retries值

@dataclass
class SystemHealth:
    netdev_max_backlog: int  # 当前系统设置值
    cpu_queues: Dict[int, Tuple[int, int]]  # CPU核ID: (processed, dropped)

@dataclass
class TcpQueueHealth:
    """TCP队列健康状态"""
    syn_drops: Optional[int] = None         # SYNs to LISTEN sockets dropped
    queue_overflows: Optional[int] = None   # listen queue overflow次数
    somaxconn: Optional[int] = None         # net.core.somaxconn当前值
    overflow_sockets: List[Dict] = None     # 溢出的socket信息

@dataclass
class TcpTimestampHealth:
    """TCP时间戳机制健康状态"""
    rejected_passive: Optional[int] = None  # passive connections rejected
    rejected_established: Optional[int] = None  # packets rejected in established
    tcp_tw_recycle: Optional[bool] = None  # 当前tcp_tw_recycle状态

@dataclass
class TcpDisorderHealth:
    """TCP乱序丢包健康状态"""
    reordering: Optional[int] = None      # 内核检测到的乱序程度
    retransmits: Optional[int] = None   # 快速重传计数
    reorder_seen: Optional[bool] = None # 是否观测到乱序

@dataclass
class TcpCongestionHealth:
    """TCP拥塞控制健康状态"""
    lost_packets: Optional[int] = None  # 拥塞导致的丢包数
    ssthresh_changes: Optional[int] = None # 慢启动阈值变化
    congestion_window: Optional[int] = None # 当前拥塞窗口大小

@dataclass
class TcpLowLatencyHealth:
    """低时延场景TCP健康状态"""
    early_retrans: Optional[int] = None      # tcp_early_retrans值
    tlp_drops: Optional[int] = None         # TLP触发的无效重传(待实现)
    delayed_ack: Optional[bool] = None      # 延迟ACK状态(待实现)

@dataclass
class UdpHealth:
    """UDP丢包健康状态"""
    rx_errors: Optional[int] = None      # 接收错误计数
    tx_errors: Optional[int] = None     # 发送错误计数
    packet_recv: Optional[int] = None   # 接收包计数

@dataclass
class SocketBufferHealth:
    """Socket缓冲区健康状态"""
    rmem_alloc: Optional[int] = None    # 已分配接收内存
    rmem_drops: Optional[int] = None    # 因缓冲区满丢包
    rmem_max: Optional[int] = None      # 最大接收缓冲区大小

class NetworkMonitorBase(ABC):
    @abstractmethod
    def get_stats(self, interface: str) -> NetworkStats:
        """获取指定网卡的统计信息"""
        pass

    @abstractmethod
    def get_speed(self, interface: str, interval: float = 1.0) -> tuple[float, float]:
        """获取指定网卡的实时网速(MB/s)"""
        pass

    @abstractmethod
    def list_interfaces(self) -> list[str]:
        """列出所有可用网卡"""
        pass

    @abstractmethod
    def check_ringbuffer_drops(self) -> Dict[str, Optional[str]]:
        """
        检测网卡Ring Buffer丢包情况
        返回: {
            "interface1": "错误详情或None(正常)",
            "interface2": "建议调整rx/tx值"
        }
        """
        pass

    @abstractmethod
    def check_interface_health(self) -> Dict[str, InterfaceHealth]:
        """检查所有接口的健康状态"""
        pass

    @abstractmethod
    def get_health_advice(self, interface: str, health: InterfaceHealth) -> List[str]:
        """根据健康状态生成建议"""
        pass

    @abstractmethod
    def check_arp_ignore(self) -> Tuple[int, List[str]]:
        """检测arp_ignore配置问题"""
        pass

    @abstractmethod
    def check_arp_filter(self) -> Tuple[int, List[str]]:
        """检测arp_filter配置问题"""
        pass

    @abstractmethod
    def check_arp_table_overflow(self) -> Tuple[bool, List[str]]:
        """检测ARP表溢出问题"""
        pass

    @abstractmethod
    def check_arp_queue_overflow(self) -> Tuple[bool, List[str]]:
        """检测ARP请求队列溢出问题"""
        pass

    @abstractmethod
    def check_conntrack_overflow(self) -> Tuple[bool, List[str]]:
        """检测连接跟踪表溢出问题"""
        pass

    @abstractmethod
    def check_conntrack_errors(self) -> Tuple[Dict[str, int], List[str]]:
        """检测CT创建失败错误"""
        pass

    @abstractmethod
    def check_conntrack_aging(self) -> Tuple[bool, List[str]]:
        """检测会话老化问题"""
        pass

    @abstractmethod
    def check_ip_fragmentation(self) -> Tuple[IPFragHealth, List[str]]:
        """检测IP分片重组问题"""
        pass

    @abstractmethod
    def check_tcp_timewait(self) -> Tuple[TcpTimeWaitHealth, List[str]]:
        """检测TCP timewait相关问题和状态"""
        pass

    @abstractmethod
    def check_tcp_queue(self) -> Tuple[TcpQueueHealth, List[str]]:
        """检测TCP队列问题"""
        pass

    @abstractmethod
    def check_syn_flood(self) -> Tuple[SynFloodHealth, List[str]]:
        """检测SYN Flood攻击"""
        pass

    @abstractmethod
    def check_tcp_timestamp(self) -> Tuple[TcpTimestampHealth, List[str]]:
        """检测TCP时间戳机制问题"""
        pass
    @abstractmethod
    def check_tcp_disorder(self) -> Tuple[TcpDisorderHealth, List[str]]:
        """检测TCP乱序丢包问题"""
        pass
        
    @abstractmethod
    def check_tcp_congestion(self) -> Tuple[TcpCongestionHealth, List[str]]:
        """检测TCP拥塞控制丢包问题"""
        pass
    @abstractmethod
    def check_tcp_low_latency(self) -> Tuple[TcpLowLatencyHealth, List[str]]:
        """检测低时延场景TLP与延迟ACK交互问题"""
        pass
    @abstractmethod
    def check_udp_loss(self) -> Tuple[UdpHealth, List[str]]:
        """检测UDP层丢包问题"""
        pass
        
    @abstractmethod
    def check_socket_buffer(self) -> Tuple[SocketBufferHealth, List[str]]:
        """检测Socket缓冲区丢包问题"""
        pass