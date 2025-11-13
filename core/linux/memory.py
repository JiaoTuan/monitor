import os
import re
import time
from time import sleep
import subprocess
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Optional, List, Dict
from collections import defaultdict
import json

from ..base.memory import (
    MemoryStats, SwapStats, MemoryPressureStats,
    MemoryFragmentation, MemoryMonitorBase
)

try:
    import matplotlib
    matplotlib.use('Agg')  # 使用非交互式后端
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib import rcParams
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

class MemorySnapshot(NamedTuple):
    """内存快照"""
    timestamp: float
    memory_stats: MemoryStats
    swap_stats: SwapStats
    pressure_stats: MemoryPressureStats
    vmstat_data: Dict

class MemoryStructure(NamedTuple):
    """内存结构分析"""
    user_used_gb: float          # 用户空间使用
    anon_pages_gb: float         # 匿名页
    cached_pages_gb: float       # 文件缓存页
    kernel_used_gb: float        # 内核空间使用
    slab_gb: float               # Slab 缓存
    page_tables_gb: float        # 页表
    kernel_stack_gb: float       # 内核栈
    
    # 比例指标
    user_ratio: float            # 用户空间占比 %
    anon_ratio: float            # 匿名页占比 %
    file_ratio: float            # 文件页占比 %
    kernel_ratio: float          # 内核空间占比 %
    slab_ratio: float            # Slab 占比 %
    slab_unreclaim_ratio: float  # Slab 不可回收占比 %
    avail_ratio: float           # 可用比例 %
    cold_page_ratio: float       # 冷页占比 % (可回收页)

class MemoryLinuxMonitor(MemoryMonitorBase):
    """Linux 内存监控实现"""
    
    def __init__(self, output_dir: str = "./out/memory/"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots: List[MemorySnapshot] = []
        self._setup_matplotlib()
    
    def _setup_matplotlib(self):
        """配置 matplotlib 中文支持"""
        if not MATPLOTLIB_AVAILABLE:
            return

        # 设置中文字体
        rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial Unicode MS', 'SimHei']
        rcParams['axes.unicode_minus'] = False
        rcParams['figure.figsize'] = (14, 8)
        rcParams['figure.dpi'] = 100
    
    def get_memory_stats(self) -> MemoryStats:
        """从 /proc/meminfo 获取内存统计"""
        meminfo = self._read_proc_meminfo()
        
        total = meminfo.get('MemTotal', 0) * 1024
        free = meminfo.get('MemFree', 0) * 1024
        available = meminfo.get('MemAvailable', 0) * 1024
        buffers = meminfo.get('Buffers', 0) * 1024
        cached = meminfo.get('Cached', 0) * 1024
        shared = meminfo.get('Shmem', 0) * 1024
        active = meminfo.get('Active', 0) * 1024
        inactive = meminfo.get('Inactive', 0) * 1024
        
        used = total - free
        percent = (used / total * 100) if total > 0 else 0
        
        return MemoryStats(
            total=total,
            available=available,
            used=used,
            free=free,
            percent=percent,
            buffers=buffers,
            cached=cached,
            shared=shared,
            active=active,
            inactive=inactive
        )
    
    def get_swap_stats(self) -> SwapStats:
        """从 /proc/meminfo 和 /proc/vmstat 获取 Swap 统计"""
        meminfo = self._read_proc_meminfo()
        vmstat = self._read_proc_vmstat()
        
        swap_total = meminfo.get('SwapTotal', 0) * 1024
        swap_free = meminfo.get('SwapFree', 0) * 1024
        swap_used = swap_total - swap_free
        swap_percent = (swap_used / swap_total * 100) if swap_total > 0 else 0
        
        sin = vmstat.get('pswpin', 0)
        sout = vmstat.get('pswpout', 0)
        
        return SwapStats(
            total=swap_total,
            used=swap_used,
            free=swap_free,
            percent=swap_percent,
            sin=sin,
            sout=sout
        )
    
    def get_memory_pressure(self) -> MemoryPressureStats:
        """从 /proc/vmstat 获取内存压力指标"""
        vmstat = self._read_proc_vmstat()
        
        page_faults = vmstat.get('pgfault', 0)
        major_faults = vmstat.get('pgmajfault', 0)
        
        # 内存回收相关
        pgscan_direct = vmstat.get('pgscan_direct_normal', 0)
        pgscan_direct += vmstat.get('pgscan_direct_movable', 0)
        pgscan_direct += vmstat.get('pgscan_direct_dma', 0)
        
        pgsteal_direct = vmstat.get('pgsteal_direct_normal', 0)
        pgsteal_direct += vmstat.get('pgsteal_direct_movable', 0)
        pgsteal_direct += vmstat.get('pgsteal_direct_dma', 0)
        
        kswapd_runs = vmstat.get('kswapd_high_wmark_hit_immediately', 0)
        oom_kills = vmstat.get('oom_kill', 0)
        
        return MemoryPressureStats(
            page_faults=page_faults,
            major_faults=major_faults,
            reclaim_stalls=pgscan_direct,
            direct_reclaim=pgsteal_direct,
            kswapd_runs=kswapd_runs,
            oom_kills=oom_kills
        )
    
    def get_memory_fragmentation(self) -> MemoryFragmentation:
        """从 /proc/buddyinfo 获取内存碎片化指标"""
        try:
            with open('/proc/buddyinfo', 'r') as f:
                buddy_info = f.read()
            
            # 简化版碎片化指数计算
            lines = buddy_info.strip().split('\n')
            total_pages = 0
            fragmented_pages = 0
            
            for line in lines:
                parts = line.split()
                if len(parts) > 4:
                    # 高阶块（12-10）更容易碎片化
                    for i in range(4, min(len(parts), 8)):
                        fragmented_pages += int(parts[i]) * (2 ** (i - 4))
                    total_pages += sum(int(p) for p in parts[4:])
            
            fragmentation_percent = (fragmented_pages / total_pages * 100) if total_pages > 0 else 0
            extfrag_index = min(fragmentation_percent / 100, 1.0)
            
            meminfo = self._read_proc_meminfo()
            available_pages = meminfo.get('MemAvailable', 0) // 4
            
        except Exception:
            extfrag_index = 0.0
            fragmentation_percent = 0.0
            available_pages = 0
            fragmented_pages = 0
        
        return MemoryFragmentation(
            extfrag_index=extfrag_index,
            fragmentation_percent=fragmentation_percent,
            available_pages=available_pages,
            fragmented_pages=fragmented_pages
        )
    
    def get_process_memory(self, pid: int) -> Dict:
        """获取进程内存信息"""
        try:
            with open(f'/proc/{pid}/status', 'r') as f:
                status = f.read()
            
            result = {}
            for line in status.split('\n'):
                if line.startswith('VmRSS:'):
                    result['rss'] = int(line.split()[1]) * 1024
                elif line.startswith('VmSize:'):
                    result['vms'] = int(line.split()[1]) * 1024
                elif line.startswith('VmShared:'):
                    result['shared'] = int(line.split()[1]) * 1024
            
            # 计算 USS (Unique Set Size)
            pss_total = 0
            try:
                with open(f'/proc/{pid}/smaps', 'r') as f:
                    for line in f:
                        if line.startswith('Pss:'):
                            pss_total += int(line.split()[1])
                result['uss'] = pss_total * 1024
            except:
                result['uss'] = result.get('rss', 0)
            
            return result
        except Exception:
            return {'rss': 0, 'vms': 0, 'shared': 0, 'uss': 0}
    
    def get_top_memory_processes(self, top_n: int = 10) -> List[Dict]:
        """获取内存占用最多的进程"""
        try:
            result = subprocess.run(
                ['ps', 'aux', '--sort=-rss'],
                capture_output=True, text=True
            )
            
            processes = []
            lines = result.stdout.split('\n')[1:]
            
            for line in lines[:top_n]:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 11:
                    try:
                        processes.append({
                            'pid': int(parts[1]),
                            'user': parts[0],
                            'rss_mb': float(parts[5]),
                            'vsz_mb': float(parts[4]),
                            'cmd': ' '.join(parts[10:])
                        })
                    except ValueError:
                        continue
            
            return processes
        except Exception:
            return []
    
    def check_memory_health(self) -> tuple[bool, List[str]]:
        """检查内存健康状态"""
        issues = []
        
        mem_stats = self.get_memory_stats()
        swap_stats = self.get_swap_stats()
        pressure = self.get_memory_pressure()
        
        # 检查项1: 内存使用率过高
        if mem_stats.percent > 90:
            issues.append(f"⚠️ 内存使用率过高: {mem_stats.percent:.1f}%")
        elif mem_stats.percent > 80:
            issues.append(f"⚡ 内存使用率较高: {mem_stats.percent:.1f}%")
        
        # 检查项2: Swap 活动异常
        if swap_stats.percent > 50:
            issues.append(f"❌ Swap 使用过多: {swap_stats.percent:.1f}%")
        
        # 检查项3: 高频缺页
        if pressure.major_faults > 10000:
            issues.append(f"⚠️ 主缺页次数过多: {pressure.major_faults}")
        
        # 检查项4: OOM Kill
        if pressure.oom_kills > 0:
            issues.append(f"❌ 检测到 OOM Kill: {pressure.oom_kills} 次")
        
        # 检查项5: 内存回收压力
        if pressure.reclaim_stalls > 100000:
            issues.append(f"⚠️ 内存回收压力大: pgscan {pressure.reclaim_stalls}")
        
        # 检查项6: 内存碎片化
        frag = self.get_memory_fragmentation()
        if frag.extfrag_index > 0.5:
            issues.append(f"⚠️ 内存碎片化严重: {frag.fragmentation_percent:.1f}%")
        
        is_healthy = len(issues) == 0
        return is_healthy, issues
    
    def monitor_memory_trend(self, interval: float = 1.0, duration: float = 60.0) -> Dict:
        """监控内存趋势
        
        Args:
            interval: 采样间隔（秒）
            duration: 监控总时长（秒）
        
        Returns:
            分析结果字典
        """
        from time import time
        
        self.snapshots = []
        start_time = time()
        
        print(f"⏱️  采样中: ", end='', flush=True)
        
        try:
            while time() - start_time < duration:
                timestamp = time()
                
                # 采集快照
                mem_stats = self.get_memory_stats()
                swap_stats = self.get_swap_stats()
                pressure = self.get_memory_pressure()
                vmstat = self._read_proc_vmstat()
                
                snapshot = MemorySnapshot(
                    timestamp=timestamp,
                    memory_stats=mem_stats,
                    swap_stats=swap_stats,
                    pressure_stats=pressure,
                    vmstat_data=vmstat
                )
                
                self.snapshots.append(snapshot)
                print(".", end='', flush=True)
                sleep(interval)
    
        except KeyboardInterrupt:
            print("\n⚠️  中断采样")
        
        print(f" ✅ 完成 ({len(self.snapshots)} 次采样)\n")
        
        # 保存数据和生成图表
        self._save_snapshots()
        
        # 🔴 这里是关键！检查 MATPLOTLIB_AVAILABLE
        print(f"DEBUG: MATPLOTLIB_AVAILABLE = {MATPLOTLIB_AVAILABLE}")
        print(f"DEBUG: snapshots length = {len(self.snapshots)}")
        
        if MATPLOTLIB_AVAILABLE and len(self.snapshots) > 0:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            print(f"DEBUG: 准备生成图表，timestamp = {timestamp}")
            self._generate_all_charts(timestamp)
        else:
            print(f"DEBUG: 跳过图表生成 (MATPLOTLIB={MATPLOTLIB_AVAILABLE}, snapshots={len(self.snapshots)})")
        
        # 分析数据
        analysis = self._analyze_trends()
        
        return analysis
    
    def _generate_all_charts(self, timestamp: str):
        """生成所有图表"""
        print("\n📊 生成图表中...")
        print(f"输出目录: {self.output_dir}")
        print(f"快照数: {len(self.snapshots)}")
        print(f"MATPLOTLIB可用: {MATPLOTLIB_AVAILABLE}")
        
        charts = [
            ('内存分布图', self._plot_memory_distribution),
            ('回收效率图', self._plot_reclaim_efficiency),
            ('缺页趋势图', self._plot_page_faults),
            ('Swap活动图', self._plot_swap_activity),
            ('内存趋势图', self._plot_memory_trend),
            ('内存结构图', self._plot_memory_structure),
            ('仪表盘', self._plot_dashboard)
        ]
        
        for name, plot_func in charts:
            print(f"\n  处理: {name}")
            print(f"    函数: {plot_func}")
            try:
                print(f"    调用中...")
                plot_func(timestamp)
                print(f"  ✅ {name}")
            except Exception as e:
                print(f"  ❌ {name} 失败:")
                print(f"     错误: {e}")
                import traceback
                traceback.print_exc()
    
    def _save_snapshots(self):
        """保存快照数据"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data_file = self.output_dir / f"memory_raw_{timestamp}.json"
        
        data = []
        for snap in self.snapshots:
            data.append({
                'timestamp': snap.timestamp,
                'memory': {
                    'total_gb': snap.memory_stats.total / (1024**3),
                    'used_gb': snap.memory_stats.used / (1024**3),
                    'available_gb': snap.memory_stats.available / (1024**3),
                    'percent': snap.memory_stats.percent,
                    'cached_gb': snap.memory_stats.cached / (1024**3),
                },
                'swap': {
                    'total_gb': snap.swap_stats.total / (1024**3),
                    'used_gb': snap.swap_stats.used / (1024**3),
                    'percent': snap.swap_stats.percent,
                },
                'pressure': {
                    'page_faults': snap.pressure_stats.page_faults,
                    'major_faults': snap.pressure_stats.major_faults,
                    'reclaim_stalls': snap.pressure_stats.reclaim_stalls,
                }
            })
        
        with open(data_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"💾 原始数据已保存到: {data_file}")
        return data_file
    
    def _analyze_trends(self) -> Dict:
        """分析所有趋势"""
        if len(self.snapshots) < 1:
            return {
                'duration': 0,
                'samples': 0,
                'memory_trend': {},
                'swap_trend': {},
                'pressure_trend': {},
                'issues': []
            }
        
        duration = self.snapshots[-1].timestamp - self.snapshots[0].timestamp
        
        # 内存趋势
        mem_trend = self._analyze_memory_trend()
        
        # Swap 趋势
        swap_trend = self._analyze_swap_trend()
        
        # 压力指标
        pressure_trend = self._analyze_pressure_trend()
        
        # 识别问题
        issues = self._identify_issues()
        
        return {
            'duration': duration,
            'samples': len(self.snapshots),
            'memory_trend': mem_trend,
            'swap_trend': swap_trend,
            'pressure_trend': pressure_trend,
            'issues': issues
        }
    
    def _analyze_memory_trend(self) -> Dict:
        """分析内存趋势"""
        if len(self.snapshots) < 2:
            return {}
        
        first = self.snapshots[0]
        last = self.snapshots[-1]
        
        used_start = first.memory_stats.used / (1024**3)
        used_end = last.memory_stats.used / (1024**3)
        used_max = max([s.memory_stats.used / (1024**3) for s in self.snapshots])
        used_min = min([s.memory_stats.used / (1024**3) for s in self.snapshots])
        
        used_values = [s.memory_stats.used / (1024**3) for s in self.snapshots]
        
        return {
            'used_start_gb': used_start,
            'used_end_gb': used_end,
            'used_max_gb': used_max,
            'used_min_gb': used_min,
            'used_delta_gb': used_end - used_start,
            'trend': self._classify_trend(used_values)
        }
    
    def _analyze_swap_trend(self) -> Dict:
        """分析 Swap 趋势"""
        if len(self.snapshots) < 2:
            return {}
        
        first = self.snapshots[0]
        last = self.snapshots[-1]
        
        swap_in = last.swap_stats.sin - first.swap_stats.sin
        swap_out = last.swap_stats.sout - first.swap_stats.sout
        
        # 判断压力等级
        if swap_in + swap_out > 100000:
            pressure = '🔴 严重'
            impact = '性能严重下降'
        elif swap_in + swap_out > 10000:
            pressure = '🟡 中等'
            impact = '性能明显下降'
        elif swap_in + swap_out > 1000:
            pressure = '🟠 轻微'
            impact = '性能略微下降'
        else:
            pressure = '🟢 无'
            impact = '无影响'
        
        recommendation = None
        if last.swap_stats.percent > 50:
            recommendation = '建议增加物理内存或优化应用'
        
        return {
            'swap_in_total': swap_in,
            'swap_out_total': swap_out,
            'swap_percent_start': first.swap_stats.percent,
            'swap_percent_end': last.swap_stats.percent,
            'swap_pressure': pressure,
            'swap_io_impact': impact,
            'recommendation': recommendation
        }
    
    def _analyze_pressure_trend(self) -> Dict:
        """分析内存压力趋势"""
        if len(self.snapshots) < 2:
            return {}
        
        first = self.snapshots[0]
        last = self.snapshots[-1]
        
        page_faults_delta = last.pressure_stats.page_faults - first.pressure_stats.page_faults
        major_faults_delta = last.pressure_stats.major_faults - first.pressure_stats.major_faults
        pgscan_delta = last.pressure_stats.reclaim_stalls - first.pressure_stats.reclaim_stalls
        
        reclaim_efficiency = self._calc_reclaim_efficiency()
        
        return {
            'page_faults_delta': page_faults_delta,
            'major_faults_delta': major_faults_delta,
            'pgscan_delta': pgscan_delta,
            'reclaim_efficiency': reclaim_efficiency
        }
    
    def _identify_issues(self) -> list:
        """识别内存问题"""
        issues = []
        
        if len(self.snapshots) < 2:
            return issues
        
        mem_trend = self._analyze_memory_trend()
        swap_trend = self._analyze_swap_trend()
        pressure_trend = self._analyze_pressure_trend()
        
        # 内存泄漏检测
        if mem_trend.get('used_delta_gb', 0) > 1.0:
            issues.append(
                f"⚠️ 内存持续增长: +{mem_trend['used_delta_gb']:.2f}GB (可能泄漏)"
            )
        
        # Swap 压力
        if swap_trend.get('swap_percent_end', 0) > 50:
            issues.append(
                f"❌ Swap 使用过高: {swap_trend['swap_percent_end']:.1f}%"
            )
        
        # 缺页压力
        if pressure_trend.get('major_faults_delta', 0) > 100000:
            issues.append(
                f"⚠️ 主缺页频繁: +{pressure_trend['major_faults_delta']:,d}"
            )
        
        # 回收效率低
        if pressure_trend.get('reclaim_efficiency', 100) < 30:
            issues.append(
                f"🔴 页面回收效率低: {pressure_trend['reclaim_efficiency']:.1f}%"
            )
        
        return issues
    
    def _classify_trend(self, values: List[float]) -> str:
        """分类数据趋势"""
        if len(values) < 2:
            return "数据不足"
        
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]
        
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        
        delta_percent = (
            ((avg_second - avg_first) / avg_first * 100) 
            if avg_first > 0 else 0
        )
        
        if delta_percent > 5:
            return f"🔴 上升趋势 (+{delta_percent:.1f}%)"
        elif delta_percent < -5:
            return f"🟢 下降趋势 ({delta_percent:.1f}%)"
        else:
            return f"🟡 平稳 ({delta_percent:+.1f}%)"
    
    def _plot_memory_structure(self, timestamp: str):
        """绘制内存结构分析图"""
        if not MATPLOTLIB_AVAILABLE or len(self.snapshots) < 1:
            return
        
        try:
            times = [datetime.fromtimestamp(s.timestamp) for s in self.snapshots]
            
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
            
            # 1. 最后一个快照的内存分布饼图
            last = self.snapshots[-1]
            sizes = [
                last.memory_stats.used / (1024**3),
                last.memory_stats.cached / (1024**3),
                last.memory_stats.buffers / (1024**3),
                last.memory_stats.available / (1024**3)
            ]
            labels = ['Used', 'Cached', 'Buffers', 'Available']
            colors = ['#FF6B6B', '#45B7D1', '#FFA500', '#96CEB4']
            
            ax1.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%',
                   startangle=90, textprops={'fontsize': 10, 'fontweight': 'bold'})
            ax1.set_title('💾 Current Memory Distribution', fontsize=13, fontweight='bold')
            
            # 2. 内存使用率百分比趋势
            mem_percent = [s.memory_stats.percent for s in self.snapshots]
            ax2.fill_between(times, mem_percent, alpha=0.5, color='#FF6B6B')
            ax2.plot(times, mem_percent, 'o-', color='#FF6B6B', linewidth=2.5, markersize=6)
            ax2.axhline(y=80, color='orange', linestyle='--', linewidth=2, alpha=0.5, label='80%')
            ax2.axhline(y=90, color='red', linestyle='--', linewidth=2, alpha=0.5, label='90%')
            ax2.set_title('📊 Memory Usage %', fontsize=13, fontweight='bold')
            ax2.set_ylabel('Usage %', fontsize=11, fontweight='bold')
            ax2.set_ylim(0, 100)
            ax2.legend(fontsize=10)
            ax2.grid(True, alpha=0.3)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            
            # 3. Active vs Inactive 页面
            active = [s.memory_stats.active / (1024**3) for s in self.snapshots]
            inactive = [s.memory_stats.inactive / (1024**3) for s in self.snapshots]
            ax3.stackplot(times, active, inactive, labels=['Active', 'Inactive'],
                         colors=['#FF6B6B', '#45B7D1'], alpha=0.7)
            ax3.set_title('📄 Active vs Inactive Pages', fontsize=13, fontweight='bold')
            ax3.set_ylabel('Memory (GB)', fontsize=11, fontweight='bold')
            ax3.legend(fontsize=10)
            ax3.grid(True, alpha=0.3)
            ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            
            # 4. 共享内存趋势
            shared = [s.memory_stats.shared / (1024**3) for s in self.snapshots]
            ax4.plot(times, shared, 'o-', color='#4ECDC4', linewidth=2.5, markersize=6)
            ax4.fill_between(times, shared, alpha=0.3, color='#4ECDC4')
            ax4.set_title('🔗 Shared Memory', fontsize=13, fontweight='bold')
            ax4.set_ylabel('Memory (GB)', fontsize=11, fontweight='bold')
            ax4.set_xlabel('Time', fontsize=11, fontweight='bold')
            ax4.grid(True, alpha=0.3)
            ax4.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            chart_file = self.output_dir / f"memory_structure_{timestamp}.png"
            print(f"    保存到: {chart_file}")
            plt.savefig(str(chart_file), dpi=100, bbox_inches='tight')
            plt.close()
        except Exception as e:
            print(f"⚠️  绘制内存结构图失败: {e}")
            import traceback
            traceback.print_exc()

    def _plot_dashboard(self, timestamp: str):
        """绘制综合分析仪表盘"""
        if not MATPLOTLIB_AVAILABLE or len(self.snapshots) < 1:
            return
        
        try:
            fig = plt.figure(figsize=(18, 12))
            gs = fig.add_gridspec(3, 3, hspace=0.35, wspace=0.3)
            
            times = [datetime.fromtimestamp(s.timestamp) for s in self.snapshots]
            
            # 1. 内存使用趋势 (大图)
            ax1 = fig.add_subplot(gs[0:2, 0:2])
            used = [s.memory_stats.used / (1024**3) for s in self.snapshots]
            available = [s.memory_stats.available / (1024**3) for s in self.snapshots]
            ax1.fill_between(times, used, alpha=0.5, color='#FF6B6B', label='Used')
            ax1.fill_between(times, used, [u+a for u,a in zip(used, available)], 
                            alpha=0.3, color='#96CEB4', label='Available')
            ax1.plot(times, used, 'o-', color='#FF6B6B', linewidth=2.5)
            ax1.set_title('📈 Memory Usage Trend', fontsize=12, fontweight='bold')
            ax1.set_ylabel('Memory (GB)', fontsize=10)
            ax1.legend(fontsize=10)
            ax1.grid(True, alpha=0.3)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            
            # 2. 内存分布饼图
            ax2 = fig.add_subplot(gs[0, 2])
            last = self.snapshots[-1]
            sizes = [last.memory_stats.used / (1024**3), last.memory_stats.available / (1024**3)]
            ax2.pie(sizes, labels=['Used', 'Avail'], colors=['#FF6B6B', '#96CEB4'],
                   autopct='%1.0f%%', textprops={'fontsize': 9})
            ax2.set_title('Current', fontsize=11, fontweight='bold')
            
            # 3. Swap 使用率
            ax3 = fig.add_subplot(gs[1, 2])
            swap_percent = [s.swap_stats.percent for s in self.snapshots]
            ax3.plot(times, swap_percent, 'o-', color='#FFA500', linewidth=2)
            ax3.fill_between(times, swap_percent, alpha=0.3, color='#FFA500')
            ax3.set_title('Swap %', fontsize=11, fontweight='bold')
            ax3.set_ylabel('%', fontsize=10)
            ax3.grid(True, alpha=0.3)
            ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            
            # 4. 缺页统计
            ax4 = fig.add_subplot(gs[2, 0])
            major_faults = [s.pressure_stats.major_faults for s in self.snapshots]
            ax4.plot(times, major_faults, 'o-', color='#FF6B6B', linewidth=2)
            ax4.set_title('Major Faults', fontsize=11, fontweight='bold')
            ax4.set_ylabel('Count', fontsize=10)
            ax4.grid(True, alpha=0.3)
            ax4.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            
            # 5. 页面回收
            ax5 = fig.add_subplot(gs[2, 1])
            pgscan = [s.pressure_stats.reclaim_stalls for s in self.snapshots]
            ax5.plot(times, pgscan, 'o-', color='#45B7D1', linewidth=2)
            ax5.set_title('pgscan_direct', fontsize=11, fontweight='bold')
            ax5.set_ylabel('Pages', fontsize=10)
            ax5.grid(True, alpha=0.3)
            ax5.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            
            # 6. 统计信息文本
            ax6 = fig.add_subplot(gs[2, 2])
            ax6.axis('off')
            
            summary_text = f"""
📊 监控统计

采样次数: {len(self.snapshots)}
监控时长: {(times[-1] - times[0]).total_seconds():.0f}s

最新状态:
  内存: {used[-1]:.1f}GB
  使用率: {self.snapshots[-1].memory_stats.percent:.1f}%
  Swap: {swap_percent[-1]:.1f}%
  
峰值/最低:
  内存峰值: {max(used):.1f}GB
  内存最低: {min(used):.1f}GB
  
压力指标:
  主缺页: {major_faults[-1]:,d}
  页扫描: {pgscan[-1]:,d}
            """
            
            ax6.text(0.05, 0.95, summary_text, transform=ax6.transAxes,
                    fontsize=9, verticalalignment='top', family='monospace',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            fig.suptitle('📋 Memory Monitoring Dashboard', fontsize=16, fontweight='bold')
            
            chart_file = self.output_dir / f"dashboard_{timestamp}.png"
            print(f"    保存到: {chart_file}")
            plt.savefig(str(chart_file), dpi=100, bbox_inches='tight')
            plt.close()
        except Exception as e:
            print(f"⚠️  绘制仪表盘失败: {e}")
            import traceback
            traceback.print_exc()
    
    def get_memory_structure(self) -> MemoryStructure:
        """获取内存结构分析"""
        meminfo = self._read_proc_meminfo()
        
        total_kb = meminfo.get('MemTotal', 1)
        total_gb = total_kb / (1024 ** 2)
        
        # 用户空间
        anon_pages_kb = meminfo.get('AnonPages', 0)
        cached_kb = meminfo.get('Cached', 0)
        buffers_kb = meminfo.get('Buffers', 0)
        user_used_kb = anon_pages_kb + cached_kb + buffers_kb
        
        # 内核空间
        slab_kb = meminfo.get('Slab', 0)
        slab_reclaim_kb = meminfo.get('SReclaimable', 0)
        page_tables_kb = meminfo.get('PageTables', 0)
        kernel_stack_kb = meminfo.get('KernelStack', 0)
        kernel_used_kb = slab_kb + page_tables_kb + kernel_stack_kb
        
        # 可用
        available_kb = meminfo.get('MemAvailable', 0)
        
        return MemoryStructure(
            user_used_gb=user_used_kb / (1024 ** 2),
            anon_pages_gb=anon_pages_kb / (1024 ** 2),
            cached_pages_gb=cached_kb / (1024 ** 2),
            kernel_used_gb=kernel_used_kb / (1024 ** 2),
            slab_gb=slab_kb / (1024 ** 2),
            page_tables_gb=page_tables_kb / (1024 ** 2),
            kernel_stack_gb=kernel_stack_kb / (1024 ** 2),
            
            # 比例
            user_ratio=(user_used_kb / total_kb * 100) if total_kb > 0 else 0,
            anon_ratio=(anon_pages_kb / total_kb * 100) if total_kb > 0 else 0,
            file_ratio=((cached_kb + buffers_kb) / total_kb * 100) if total_kb > 0 else 0,
            kernel_ratio=(kernel_used_kb / total_kb * 100) if total_kb > 0 else 0,
            slab_ratio=(slab_kb / total_kb * 100) if total_kb > 0 else 0,
            slab_unreclaim_ratio=((slab_kb - slab_reclaim_kb) / slab_kb * 100) if slab_kb > 0 else 0,
            avail_ratio=(available_kb / total_kb * 100) if total_kb > 0 else 0,
            cold_page_ratio=(slab_reclaim_kb / total_kb * 100) if total_kb > 0 else 0
        )
    
    def print_memory_structure_report(self):
        """打印内存结构分析报告"""
        struct = self.get_memory_structure()
        
        print("\n" + "="*70)
        print("📊 内存结构分析报告")
        print("="*70)
        
        print("\n🟦 用户空间 (User Space)")
        print(f"  • 总占用: {struct.user_used_gb:.2f}GB ({struct.user_ratio:.1f}%)")
        print(f"  • 匿名页: {struct.anon_pages_gb:.2f}GB ({struct.anon_ratio:.1f}%)")
        print(f"  • 文件缓存: {struct.cached_pages_gb:.2f}GB ({struct.file_ratio:.1f}%)")
        
        print("\n🟧 内核空间 (Kernel Space)")
        print(f"  • 总占用: {struct.kernel_used_gb:.2f}GB ({struct.kernel_ratio:.1f}%)")
        print(f"  • Slab缓存: {struct.slab_gb:.2f}GB ({struct.slab_ratio:.1f}%)")
        print(f"  • 页表: {struct.page_tables_gb:.2f}GB")
        print(f"  • 内核栈: {struct.kernel_stack_gb:.2f}GB")
        print(f"  • Slab不可回收: {struct.slab_unreclaim_ratio:.1f}%")
        
        print("\n🟩 可用/空闲")
        print(f"  • 可用内存占比: {struct.avail_ratio:.1f}%")
        print(f"  • 冷页占比: {struct.cold_page_ratio:.1f}%")
        
        print("\n" + "="*70 + "\n")
    
    # ========== 辅助方法：读取 /proc 文件 ==========
    
    def _read_proc_meminfo(self) -> Dict[str, int]:
        """读取 /proc/meminfo 文件"""
        meminfo = {}
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if ':' not in line:
                        continue
                    key, value = line.split(':', 1)
                    key = key.strip()
                    try:
                        value = int(value.split()[0])
                        meminfo[key] = value
                    except (ValueError, IndexError):
                        continue
        except Exception as e:
            print(f"❌ 读取 /proc/meminfo 失败: {e}")
        return meminfo
    
    def _read_proc_vmstat(self) -> Dict[str, int]:
        """读取 /proc/vmstat 文件"""
        vmstat = {}
        try:
            with open('/proc/vmstat', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            key = parts[0]
                            value = int(parts[1])
                            vmstat[key] = value
                        except (ValueError, IndexError):
                            continue
        except Exception as e:
            print(f"❌ 读取 /proc/vmstat 失败: {e}")
        return vmstat
    
    # ========== 缺失的分析方法 ==========
    
    def _analyze_pressure_trend(self) -> Dict:
        """分析内存压力趋势"""
        if len(self.snapshots) < 2:
            return {}
        
        page_faults = [s.pressure_stats.page_faults for s in self.snapshots]
        major_faults = [s.pressure_stats.major_faults for s in self.snapshots]
        reclaim = [s.pressure_stats.reclaim_stalls for s in self.snapshots]
        
        return {
            'page_faults_delta': page_faults[-1] - page_faults[0],
            'major_faults_delta': major_faults[-1] - major_faults[0],
            'pgscan_delta': reclaim[-1] - reclaim[0],
            'reclaim_efficiency': self._calc_reclaim_efficiency()
        }
    
    def _calc_reclaim_efficiency(self) -> float:
        """计算内存回收效率"""
        if len(self.snapshots) < 2:
            return 0.0
        
        first = self.snapshots[0]
        last = self.snapshots[-1]
        
        pgscan_delta = last.vmstat_data.get('pgscan_direct_normal', 0) - \
                      first.vmstat_data.get('pgscan_direct_normal', 0)
        pgsteal_delta = last.vmstat_data.get('pgsteal_direct_normal', 0) - \
                       first.vmstat_data.get('pgsteal_direct_normal', 0)
        
        if pgscan_delta == 0:
            return 100.0
        
        efficiency = (pgsteal_delta / pgscan_delta * 100) if pgscan_delta > 0 else 0.0
        return min(efficiency, 100.0)
    
    def _identify_issues(self) -> List[str]:
        """识别内存问题"""
        issues = []
        
        if len(self.snapshots) < 2:
            return issues
        
        mem_trend = self._analyze_memory_trend()
        swap_trend = self._analyze_swap_trend()
        pressure_trend = self._analyze_pressure_trend()
        
        # 内存泄漏检测
        if mem_trend.get('used_delta_gb', 0) > 1.0:
            issues.append(f"⚠️ 内存持续增长: +{mem_trend['used_delta_gb']:.2f}GB (可能泄漏)")
        
        # Swap 压力
        if swap_trend.get('swap_percent_end', 0) > 50:
            issues.append(f"❌ Swap 使用过高: {swap_trend['swap_percent_end']:.1f}%")
        
        # 缺页压力
        if pressure_trend.get('major_faults_delta', 0) > 100000:
            issues.append(f"⚠️ 主缺页频繁: +{pressure_trend['major_faults_delta']:,d}")
        
        # 回收效率低
        if pressure_trend.get('reclaim_efficiency', 100) < 30:
            issues.append(f"🔴 页面回收效率低: {pressure_trend['reclaim_efficiency']:.1f}%")
        
        return issues
    
    def _classify_trend(self, values: List[float]) -> str:
        """分类数据趋势"""
        if len(values) < 2:
            return "数据不足"
        
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]
        
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        
        delta_percent = ((avg_second - avg_first) / avg_first * 100) if avg_first > 0 else 0
        
        if delta_percent > 5:
            return f"🔴 上升趋势 (+{delta_percent:.1f}%)"
        elif delta_percent < -5:
            return f"🟢 下降趋势 ({delta_percent:.1f}%)"
        else:
            return f"🟡 平稳 ({delta_percent:+.1f}%)"
    
    # ========== 图表绘制方法 ==========
    
    def _plot_memory_distribution(self, timestamp: str):
        """绘制内存分布堆叠图"""
        if not MATPLOTLIB_AVAILABLE or len(self.snapshots) < 1:
            return
        
        try:
            times = [datetime.fromtimestamp(s.timestamp) for s in self.snapshots]
            used = [s.memory_stats.used / (1024**3) for s in self.snapshots]
            cached = [s.memory_stats.cached / (1024**3) for s in self.snapshots]
            buffers = [s.memory_stats.buffers / (1024**3) for s in self.snapshots]
            available = [s.memory_stats.available / (1024**3) for s in self.snapshots]
            
            fig, ax = plt.subplots(figsize=(14, 7))
            
            ax.stackplot(times, used, cached, buffers, available,
                        labels=['Used', 'Cached', 'Buffers', 'Available'],
                        colors=['#FF6B6B', '#45B7D1', '#FFA500', '#96CEB4'],
                        alpha=0.8)
            
            ax.set_title('📦 Memory Distribution', fontsize=14, fontweight='bold')
            ax.set_ylabel('Memory (GB)', fontsize=11, fontweight='bold')
            ax.set_xlabel('Time', fontsize=11, fontweight='bold')
            ax.legend(loc='upper left', fontsize=10)
            ax.grid(True, alpha=0.3)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            chart_file = self.output_dir / f"memory_distribution_{timestamp}.png"
            print(f"    保存到: {chart_file}")
            plt.savefig(str(chart_file), dpi=100, bbox_inches='tight')
            plt.close()
        except Exception as e:
            print(f"⚠️  绘制内存分布图失败: {e}")
            import traceback
            traceback.print_exc()

    def _plot_reclaim_efficiency(self, timestamp: str):
        """绘制页面回收效率图"""
        if not MATPLOTLIB_AVAILABLE or len(self.snapshots) < 1:
            return
        
        try:
            times = [datetime.fromtimestamp(s.timestamp) for s in self.snapshots]
            pgscan = [s.pressure_stats.reclaim_stalls for s in self.snapshots]
            
            fig, ax = plt.subplots(figsize=(14, 7))
            ax.plot(times, pgscan, 'o-', color='#FF6B6B', linewidth=2.5, markersize=6)
            ax.fill_between(times, pgscan, alpha=0.3, color='#FF6B6B')
            ax.set_title('♻️ Page Reclaim Efficiency', fontsize=14, fontweight='bold')
            ax.set_ylabel('pgscan_direct', fontsize=11, fontweight='bold')
            ax.set_xlabel('Time', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            chart_file = self.output_dir / f"reclaim_efficiency_{timestamp}.png"
            print(f"    保存到: {chart_file}")
            plt.savefig(str(chart_file), dpi=100, bbox_inches='tight')
            plt.close()
        except Exception as e:
            print(f"⚠️  绘制回收效率图失败: {e}")
            import traceback
            traceback.print_exc()

    def _plot_page_faults(self, timestamp: str):
        """绘制缺页趋势图"""
        if not MATPLOTLIB_AVAILABLE or len(self.snapshots) < 1:
            return
        
        try:
            times = [datetime.fromtimestamp(s.timestamp) for s in self.snapshots]
            page_faults = [s.pressure_stats.page_faults for s in self.snapshots]
            major_faults = [s.pressure_stats.major_faults for s in self.snapshots]
            
            fig, ax = plt.subplots(figsize=(14, 7))
            ax.plot(times, page_faults, 'o-', label='Page Faults', 
                   color='#45B7D1', linewidth=2.5, markersize=6)
            ax.plot(times, major_faults, 's-', label='Major Faults', 
                   color='#FF6B6B', linewidth=2.5, markersize=6)
            ax.set_title('📉 Page Faults Trend', fontsize=14, fontweight='bold')
            ax.set_ylabel('Count', fontsize=11, fontweight='bold')
            ax.set_xlabel('Time', fontsize=11, fontweight='bold')
            ax.legend(loc='upper left', fontsize=10)
            ax.grid(True, alpha=0.3)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            chart_file = self.output_dir / f"page_faults_{timestamp}.png"
            print(f"    保存到: {chart_file}")
            plt.savefig(str(chart_file), dpi=100, bbox_inches='tight')
            plt.close()
        except Exception as e:
            print(f"⚠️  绘制缺页图失败: {e}")
            import traceback
            traceback.print_exc()

    def _plot_swap_activity(self, timestamp: str):
        """绘制 Swap 活动图"""
        if not MATPLOTLIB_AVAILABLE or len(self.snapshots) < 1:
            return
        
        try:
            times = [datetime.fromtimestamp(s.timestamp) for s in self.snapshots]
            swap_in = [s.swap_stats.sin for s in self.snapshots]
            swap_out = [s.swap_stats.sout for s in self.snapshots]
            
            fig, ax = plt.subplots(figsize=(14, 7))
            ax.plot(times, swap_in, 'o-', label='Swap In', 
                   color='#4ECDC4', linewidth=2.5, markersize=6)
            ax.plot(times, swap_out, 's-', label='Swap Out', 
                   color='#FFA500', linewidth=2.5, markersize=6)
            ax.set_title('🔄 Swap Activity', fontsize=14, fontweight='bold')
            ax.set_ylabel('Pages', fontsize=11, fontweight='bold')
            ax.set_xlabel('Time', fontsize=11, fontweight='bold')
            ax.legend(loc='upper left', fontsize=10)
            ax.grid(True, alpha=0.3)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            chart_file = self.output_dir / f"swap_activity_{timestamp}.png"
            print(f"    保存到: {chart_file}")
            plt.savefig(str(chart_file), dpi=100, bbox_inches='tight')
            plt.close()
        except Exception as e:
            print(f"⚠️  绘制 Swap 活动图失败: {e}")
            import traceback
            traceback.print_exc()

    def _plot_memory_trend(self, timestamp: str):
        """绘制内存使用趋势图"""
        if not MATPLOTLIB_AVAILABLE or len(self.snapshots) < 1:
            return
        
        try:
            times = [datetime.fromtimestamp(s.timestamp) for s in self.snapshots]
            used = [s.memory_stats.used / (1024**3) for s in self.snapshots]
            available = [s.memory_stats.available / (1024**3) for s in self.snapshots]
            
            fig, ax = plt.subplots(figsize=(14, 7))
            ax.plot(times, used, 'o-', label='Used', 
                   color='#FF6B6B', linewidth=2.5, markersize=6)
            ax.plot(times, available, 's-', label='Available', 
                   color='#96CEB4', linewidth=2.5, markersize=6)
            ax.set_title('📈 Memory Trend', fontsize=14, fontweight='bold')
            ax.set_ylabel('Memory (GB)', fontsize=11, fontweight='bold')
            ax.set_xlabel('Time', fontsize=11, fontweight='bold')
            ax.legend(loc='upper left', fontsize=10)
            ax.grid(True, alpha=0.3)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            chart_file = self.output_dir / f"memory_trend_{timestamp}.png"
            print(f"    保存到: {chart_file}")
            plt.savefig(str(chart_file), dpi=100, bbox_inches='tight')
            plt.close()
        except Exception as e:
            print(f"⚠️  绘制趋势图失败: {e}")
            import traceback
            traceback.print_exc()
