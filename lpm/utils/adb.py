import subprocess

class ADBWrapper:
    def __init__(self, device_id=None):
        self.device_id = device_id
    
    def shell(self, command: str) -> str:
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(["shell", command])
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"ADB命令执行失败: {result.stderr}")
        return result.stdout