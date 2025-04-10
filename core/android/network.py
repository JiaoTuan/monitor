import re
from typing import List
from ..base.network import NetworkStats, NetworkMonitorBase
from lpm.utils.adb import ADBWrapper

class AndroidNetwork(NetworkMonitorBase):
    def __init__(self, adb: ADBWrapper):
        self.adb = adb

    def _parse_proc_net_dev(self, text: str) -> Dict[str, NetworkStats]:
        """解析/proc/net/dev输出"""
        result = {}
        for line in text.split('\n'):
            if ':' not in line:
                continue
            ifname, data = line.split(':', 1)
            ifname = ifname.strip()
            fields = list(map(int, data.split()))
            
            result[ifname] = NetworkStats(
                bytes_recv=fields[0],
                packets_recv=fields[1],
                errors_in=fields[2],
                drop_in=fields[3],
                bytes_sent=fields[8],
                packets_sent=fields[9],
                errors_out=fields[10],
                drop_out=fields[11]
            )
        return result

    def get_stats(self, interface: str) -> NetworkStats:
        output = self.adb.shell("cat /proc/net/dev")
        stats = self._parse_proc_net_dev(output).get(interface)
        if not stats:
            raise ValueError(f"Android网卡 {interface} 不存在")
        return stats

    def get_speed(self, interface: str, interval: float = 1.0) -> tuple[float, float]:
        start = self.get_stats(interface)
        self.adb.sleep(interval)
        end = self.get_stats(interface)
        
        upload = (end.bytes_sent - start.bytes_sent) / interval / 1024**2
        download = (end.bytes_recv - start.bytes_recv) / interval / 1024**2
        
        return (upload, download)

    def list_interfaces(self) -> list[str]:
        output = self.adb.shell("ls /sys/class/net")
        return output.split()