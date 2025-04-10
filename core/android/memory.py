import psutil
from collections import namedtuple

MemoryInfo = namedtuple('MemoryInfo', ['total', 'used', 'free', 'percent'])

def get_memory_info():
    """获取内存使用信息"""
    mem = psutil.virtual_memory()
    return MemoryInfo(
        total=mem.total,
        used=mem.used,
        free=mem.free,
        percent=mem.percent
    )
