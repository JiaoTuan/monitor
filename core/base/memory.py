from abc import ABC, abstractmethod
from typing import NamedTuple

class NetworkStats(NamedTuple):
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int

class NetworkMonitorBase(ABC):
    @abstractmethod
    def get_stats(self) -> NetworkStats:
        """获取累计网络流量统计"""
        pass

    @abstractmethod
    def get_speed(self, interval: float = 1.0) -> tuple[float, float]:
        """获取实时网速（MB/s）"""
        pass