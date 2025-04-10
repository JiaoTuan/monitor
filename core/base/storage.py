import psutil

def get_disk_info(mountpoint='/'):
    """获取指定挂载点的磁盘使用情况"""
    usage = psutil.disk_usage(mountpoint)
    return {
        'total': usage.total,
        'used': usage.used,
        'free': usage.free,
        'percent': usage.percent
    }