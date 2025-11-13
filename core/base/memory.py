from abc import ABC, abstractmethod
from typing import NamedTuple

class MemoryStats(NamedTuple):
	"""内存统计信息"""
	total: int              # 总内存（字节）
	available: int          # 可用内存（字节）
	used: int              # 已用内存（字节）
	free: int              # 空闲内存（字节）
	percent: float         # 使用率（%）
	buffers: int           # 缓冲区（字节）
	cached: int            # 缓存（字节）
	shared: int            # 共享内存（字节）
	active: int            # 活跃内存（字节）
	inactive: int          # 非活跃内存（字节）

class SwapStats(NamedTuple):
	"""交换内存统计信息"""
	total: int              # Swap 总大小（字节）
	used: int              # Swap 已用（字节）
	free: int              # Swap 空闲（字节）
	percent: float         # Swap 使用率（%）
	sin: int               # 换入页数
	sout: int              # 换出页数

class MemoryPressureStats(NamedTuple):
	"""内存压力相关统计"""
	page_faults: int       # 缺页次数
	major_faults: int      # 主缺页次数
	reclaim_stalls: int    # 内存回收停滞次数
	direct_reclaim: int    # 直接回收次数
	kswapd_runs: int       # kswapd 运行次数
	oom_kills: int         # OOM Kill 次数

class MemoryFragmentation(NamedTuple):
	"""内存碎片化指标"""
	extfrag_index: float   # 外部碎片指数（0-1）
	fragmentation_percent: float  # 碎片化百分比
	available_pages: int   # 可用页数
	fragmented_pages: int  # 碎片化页数

class MemoryMonitorBase(ABC):
	"""内存监控基类"""

	@abstractmethod
	def get_memory_stats(self) -> MemoryStats:
		"""获取内存统计信息"""
		pass

	@abstractmethod
	def get_swap_stats(self) -> SwapStats:
		"""获取交换内存统计信息"""
		pass

	@abstractmethod
	def get_memory_pressure(self) -> MemoryPressureStats:
		"""获取内存压力指标"""
		pass

	@abstractmethod
	def get_memory_fragmentation(self) -> MemoryFragmentation:
		"""获取内存碎片化指标"""
		pass

	@abstractmethod
	def get_process_memory(self, pid: int) -> dict:
		"""获取指定进程的内存使用情况
		
		返回：
			- rss: 物理内存（字节）
			- vms: 虚拟内存（字节）
			- shared: 共享内存（字节）
			- uss: 独占内存（字节）
		"""
		pass

	@abstractmethod
	def get_top_memory_processes(self, top_n: int = 10) -> list:
		"""获取内存占用最多的进程列表"""
		pass

	@abstractmethod
	def check_memory_health(self) -> tuple[bool, list]:
		"""检查内存健康状态
		
		返回：
			- 是否正常（bool）
			- 问题建议列表
		"""
		pass

	@abstractmethod
	def monitor_memory_trend(self, interval: float = 1.0) -> dict:
		"""监控内存使用趋势
		
		返回：
			- memory_delta: 内存变化量
			- swap_delta: Swap 变化量
			- trend: 趋势描述
		"""
		pass
