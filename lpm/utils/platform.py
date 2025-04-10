import os
import sys

def is_android() -> bool:
    """检测当前是否运行在Android环境"""

    if os.getenv('ANDROID_RUNTIME_ROOT'):
        return True
    
    if os.path.exists('/system/build.prop'):
        return True
    
    if 'linux' in sys.platform and 'android' in sys.version.lower():
        return True
    
    return False