from abc import ABC, abstractmethod

class CPUBase(ABC):
    @abstractmethod
    def get_usage(self) -> float:
        """获取CPU使用率百分比"""
        pass
    
    @abstractmethod
    def get_cores(self) -> int:
        """获取CPU核心数"""
        pass