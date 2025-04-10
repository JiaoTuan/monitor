import platform
import psutil

def get_system_info():
    """获取基础系统信息"""
    return {
        'hostname': platform.node(),
        'os': platform.system(),
        'uptime': psutil.boot_time()
    }
