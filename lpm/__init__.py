from core import get_cpu_monitor
from core import get_network_monitor

def cpu_usage(interval=1):
    return get_cpu_monitor().get_usage(interval)

def network_stats(interface: str) -> dict:
    """获取指定网卡统计信息"""
    return get_network_monitor().get_stats(interface)._asdict()  # 转字典

def network_speed(interface: str, interval: float = 1.0) -> tuple:
    """获取指定网卡实时网速"""
    return get_network_monitor().get_speed(interface, interval)

def list_network_interfaces() -> list[str]:
    """列出所有网卡"""
    return get_network_monitor().list_interfaces()
