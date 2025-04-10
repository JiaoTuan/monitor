from ..base.cpu import CPUBase
from lpm.utils.adb import ADBWrapper

class AndroidCPU(CPUBase):
    def __init__(self, adb: ADBWrapper):
        self.adb = adb

    def get_usage(self) -> float:
        output = self.adb.shell("cat /proc/stat")
        return self._parse_proc_stat(output)
    
    def _parse_proc_stat(self, text: str) -> float:
        return 0.0  # 示例返回值