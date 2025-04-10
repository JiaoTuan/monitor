from .linux import LinuxCPU
from .android import AndroidCPU
from lpm.utils.platform import is_android
from .base.network import NetworkMonitorBase

def get_cpu_monitor():
    if is_android():
        from lpm.utils.adb import ADBWrapper
        return AndroidCPU(ADBWrapper())
    return LinuxCPU()

def get_network_monitor() -> NetworkMonitorBase:
    if is_android():
        from .android.network import AndroidNetwork
        return AndroidNetwork(ADBWrapper())
    else:
        from .linux.network import LinuxNetwork
        return LinuxNetwork()