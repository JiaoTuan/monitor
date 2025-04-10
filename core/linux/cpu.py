import psutil
from ..base.cpu import CPUBase

class LinuxCPU(CPUBase):
    def get_usage(self, interval=1) -> float:
        return psutil.cpu_percent(interval=interval)
    
    def get_cores(self) -> int:
        return psutil.cpu_count()