import sys
import click
from time import sleep
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.linux.memory import MemoryLinuxMonitor

# 初始化监控器
memory_monitor = None

def get_monitor():
    """懒加载监控器"""
    global memory_monitor
    if memory_monitor is None:
        memory_monitor = MemoryLinuxMonitor(output_dir="./out/memory/")
    return memory_monitor

@click.group()
def cli():
    """Linux 性能和稳定性监控工具"""
    pass

# ============================================================================
# 内存监控命令组
# ============================================================================

@cli.group()
def memory():
    """内存监控和分析工具"""
    pass

@memory.command()
def status():
    """显示当前内存状态"""
    try:
        monitor = get_monitor()
        mem_stats = monitor.get_memory_stats()
        swap_stats = monitor.get_swap_stats()
        pressure = monitor.get_memory_pressure()
        
        click.secho("\n📊 当前内存状态", fg='cyan', bold=True)
        
        # 内存基础信息
        click.echo("\n[物理内存]")
        click.echo(f"  总内存:     {mem_stats.total / (1024**3):8.2f} GB")
        
        # 内存使用率颜色
        mem_color = (
            'red' if mem_stats.percent > 80 
            else 'yellow' if mem_stats.percent > 60 
            else 'green'
        )
        mem_percent_str = click.style(
            f"({mem_stats.percent:.1f}%)", 
            fg=mem_color
        )
        click.echo(f"  已用:       {mem_stats.used / (1024**3):8.2f} GB {mem_percent_str}")
        
        click.echo(f"  可用:       {mem_stats.available / (1024**3):8.2f} GB")
        click.echo(f"  空闲:       {mem_stats.free / (1024**3):8.2f} GB")
        
        # 内存分布
        click.echo("\n[内存分布]")
        click.echo(f"  缓存:       {mem_stats.cached / (1024**3):8.2f} GB")
        click.echo(f"  缓冲区:     {mem_stats.buffers / (1024**3):8.2f} GB")
        click.echo(f"  Active:     {mem_stats.active / (1024**3):8.2f} GB")
        click.echo(f"  Inactive:   {mem_stats.inactive / (1024**3):8.2f} GB")
        click.echo(f"  共享内存:   {mem_stats.shared / (1024**3):8.2f} GB")
        
        # Swap 信息
        click.echo("\n[Swap 内存]")
        click.echo(f"  总大小:     {swap_stats.total / (1024**3):8.2f} GB")
        
        # Swap 使用率颜色
        swap_color = (
            'red' if swap_stats.percent > 50 
            else 'yellow' if swap_stats.percent > 20 
            else 'green'
        )
        swap_percent_str = click.style(
            f"({swap_stats.percent:.1f}%)", 
            fg=swap_color
        )
        click.echo(f"  已用:       {swap_stats.used / (1024**3):8.2f} GB {swap_percent_str}")
        
        click.echo(f"  空闲:       {swap_stats.free / (1024**3):8.2f} GB")
        click.echo(f"  换入:       {swap_stats.sin:12,d} 页")
        click.echo(f"  换出:       {swap_stats.sout:12,d} 页")
        
        # 内存压力
        click.echo("\n[内存压力指标]")
        click.echo(f"  缺页:       {pressure.page_faults:12,d}")
        click.echo(f"  主缺页:     {pressure.major_faults:12,d}")
        click.echo(f"  页扫描:     {pressure.reclaim_stalls:12,d}")
        click.echo(f"  页回收:     {pressure.direct_reclaim:12,d}")
        click.echo(f"  OOM Kill:   {pressure.oom_kills:12,d}")
        
        # 碎片化
        frag = monitor.get_memory_fragmentation()
        click.echo("\n[内存碎片化]")
        click.echo(f"  碎片指数:   {frag.extfrag_index:8.2f}")
        click.echo(f"  碎片百分比: {frag.fragmentation_percent:8.1f}%")
        click.echo()
        
    except Exception as e:
        click.secho(f"❌ 获取内存状态失败: {e}", fg='red', bold=True)
        import traceback
        traceback.print_exc()

@memory.command()
def health():
    """检查内存健康状态"""
    try:
        monitor = get_monitor()
        is_healthy, issues = monitor.check_memory_health()
        
        if is_healthy:
            click.secho("✅ 内存状态良好", fg='green', bold=True)
        else:
            click.secho("❌ 检测到内存问题:", fg='red', bold=True)
            for issue in issues:
                click.echo(f"  {issue}")
        click.echo()
                
    except Exception as e:
        click.secho(f"❌ 健康检查失败: {e}", fg='red', bold=True)
        import traceback
        traceback.print_exc()

@memory.command()
def structure():
    """显示内存结构分析"""
    try:
        monitor = get_monitor()
        monitor.print_memory_structure_report()
    except Exception as e:
        click.secho(f"❌ 获取内存结构失败: {e}", fg='red', bold=True)
        import traceback
        traceback.print_exc()

@memory.command('top-processes')
@click.option('--top', default=10, type=int, help='显示前 N 个进程')
def top_processes(top):
    """显示内存占用最多的进程"""
    try:
        monitor = get_monitor()
        processes = monitor.get_top_memory_processes(top_n=top)
        
        if not processes:
            click.secho("❌ 无法获取进程列表", fg='red')
            return
        
        click.secho(f"\n🔝 内存占用 TOP {top} 进程", fg='cyan', bold=True)
        click.echo()
        
        # 表头
        header = (
            f"{'排名':<6} {'PID':<10} {'用户':<12} "
            f"{'RSS (MB)':<12} {'VSZ (MB)':<12} {'命令':<40}"
        )
        click.echo(header)
        click.echo("-" * 92)
        
        # 数据行
        for i, proc in enumerate(processes, 1):
            cmd_short = proc['cmd'][:40]
            line = (
                f"{i:<6} {proc['pid']:<10} {proc['user']:<12} "
                f"{proc['rss_mb']:<12.1f} {proc['vsz_mb']:<12.1f} "
                f"{cmd_short:<40}"
            )
            click.echo(line)
        
        click.echo()
        
    except Exception as e:
        click.secho(f"❌ 获取进程列表失败: {e}", fg='red', bold=True)
        import traceback
        traceback.print_exc()

@memory.command('process-info')
@click.option('--pid', type=int, required=True, help='进程 ID')
def process_info(pid):
    """获取指定进程的内存信息"""
    try:
        monitor = get_monitor()
        mem_info = monitor.get_process_memory(pid)
        
        if not mem_info or mem_info.get('rss') == 0:
            click.secho(
                f"❌ 无法获取进程 {pid} 的信息（进程不存在？）", 
                fg='red'
            )
            return
        
        click.secho(f"\n📋 进程 {pid} 内存信息", fg='cyan', bold=True)
        click.echo()
        click.echo(
            f"  RSS (物理内存):   {mem_info['rss'] / (1024**2):8.2f} MB"
        )
        click.echo(
            f"  VMS (虚拟内存):   {mem_info['vms'] / (1024**2):8.2f} MB"
        )
        click.echo(
            f"  共享内存:         {mem_info['shared'] / (1024**2):8.2f} MB"
        )
        click.echo(
            f"  独占内存 (USS):   {mem_info['uss'] / (1024**2):8.2f} MB"
        )
        click.echo()
        
    except Exception as e:
        click.secho(f"❌ 获取进程信息失败: {e}", fg='red', bold=True)
        import traceback
        traceback.print_exc()

@memory.command()
@click.option('--duration', default=60, type=int, help='监控时长（秒）')
@click.option('--interval', default=1.0, type=float, help='采样间隔（秒）')
def monitor(duration, interval):
    """监控内存使用趋势并生成报告
    
    示例:
    
        python -m lpm.cli memory monitor --duration 120 --interval 2
    """
    try:
        mon = get_monitor()
        click.secho(
            f"\n📊 开始内存监控 (时长 {duration}s, 间隔 {interval}s)", 
            fg='cyan', 
            bold=True
        )
        click.echo()
        
        # 运行监控
        analysis = mon.monitor_memory_trend(
            interval=interval,
            duration=duration
        )
        
        # 显示分析结果
        click.secho("\n📋 分析结果", fg='cyan', bold=True)
        click.echo()
        
        click.echo(f"监控时长: {analysis['duration']:.1f}秒")
        click.echo(f"采样次数: {analysis['samples']}")
        
        # 内存趋势
        mem_trend = analysis.get('memory_trend', {})
        if mem_trend:
            click.echo("\n📈 内存趋势:")
            click.echo(f"  起始内存: {mem_trend['used_start_gb']:.2f}GB")
            click.echo(f"  结束内存: {mem_trend['used_end_gb']:.2f}GB")
            click.echo(f"  最大内存: {mem_trend['used_max_gb']:.2f}GB")
            
            delta = mem_trend['used_delta_gb']
            if delta > 0.5:
                delta_msg = f"+{delta:.2f}GB (⚠️ 疑似内存泄漏)"
                delta_str = click.style(delta_msg, fg='red', bold=True)
                click.echo(f"  内存增长: {delta_str}")
            elif delta < -0.1:
                click.echo(f"  内存下降: {delta:.2f}GB")
            else:
                click.echo(f"  内存变化: {delta:+.2f}GB (平稳)")
            
            click.echo(f"  趋势: {mem_trend['trend']}")
        
        # Swap 趋势
        swap_trend = analysis.get('swap_trend', {})
        if swap_trend:
            click.echo("\n🔄 Swap 趋势:")
            click.echo(f"  换入页数: {swap_trend['swap_in_total']:,d}")
            click.echo(f"  换出页数: {swap_trend['swap_out_total']:,d}")
            click.echo(f"  Swap使用率: {swap_trend['swap_percent_end']:.1f}%")
            click.echo(f"  压力等级: {swap_trend['swap_pressure']}")
            click.echo(f"  性能影响: {swap_trend['swap_io_impact']}")
            if swap_trend.get('recommendation'):
                click.echo(f"  建议: {swap_trend['recommendation']}")
        
        # 压力指标
        pressure_trend = analysis.get('pressure_trend', {})
        if pressure_trend:
            click.echo("\n⚡ 内存压力变化:")
            click.echo(f"  缺页增长: {pressure_trend['page_faults_delta']:,d}")
            click.echo(f"  主缺页增长: {pressure_trend['major_faults_delta']:,d}")
            click.echo(f"  页扫描增长: {pressure_trend['pgscan_delta']:,d}")
            click.echo(f"  回收效率: {pressure_trend['reclaim_efficiency']:.1f}%")
        
        # 问题列表
        issues = analysis.get('issues', [])
        if issues:
            click.secho("\n🔍 检测到的问题:", fg='yellow', bold=True)
            for issue in issues:
                click.echo(f"  {issue}")
        else:
            click.secho("\n✅ 未检测到明显问题", fg='green', bold=True)
        
        click.secho(
            "\n📁 详细报告已保存到 out/memory/ 目录:", 
            fg='green', 
            bold=True
        )
        click.echo("  • 原始数据: memory_raw_YYYYMMDD_HHMMSS.json")
        click.echo("  • 内存分布图: memory_distribution_*.png")
        click.echo("  • 回收效率图: reclaim_efficiency_*.png")
        click.echo("  • 缺页趋势图: page_faults_*.png")
        click.echo("  • Swap活动图: swap_activity_*.png")
        click.echo("  • 内存趋势图: memory_trend_*.png")
        click.echo("  • 内存结构图: memory_structure_*.png")
        click.echo("  • 仪表盘图: dashboard_*.png")
        click.echo()
        
    except KeyboardInterrupt:
        click.secho("\n⚠️  监控已中断", fg='yellow')
    except Exception as e:
        click.secho(f"❌ 监控失败: {e}", fg='red', bold=True)
        import traceback
        traceback.print_exc()

# ============================================================================
# 网络监控命令组
# ============================================================================

@cli.group()
def network():
    """网络监控和诊断工具"""
    pass

@network.command('monitor-net')
@click.option('--interface', default=None, help='指定网卡名称')
@click.option('--interval', default=1.0, type=float, help='刷新间隔（秒）')
def monitor_net(interface, interval):
    """实时监控网卡流量"""
    try:
        click.secho(f"\n📡 网络流量监控", fg='cyan', bold=True)
        if interface:
            click.echo(f"网卡: {interface}")
        click.echo()
        
        while True:
            sleep(interval)
            
    except KeyboardInterrupt:
        click.secho("\n⚠️  监控已停止", fg='yellow')
    except Exception as e:
        click.secho(f"❌ 监控错误: {e}", fg='red', bold=True)

@network.command()
def check():
    """网络健康检查"""
    try:
        click.secho("\n🔍 网络健康检查", fg='cyan', bold=True)
        click.echo("检查中...")
        click.echo()
    except Exception as e:
        click.secho(f"❌ 检查失败: {e}", fg='red', bold=True)

@network.command()
def list_interfaces():
    """列出所有网卡"""
    try:
        click.secho("\n📋 系统网卡列表", fg='cyan', bold=True)
        click.echo()
    except Exception as e:
        click.secho(f"❌ 获取网卡列表失败: {e}", fg='red', bold=True)

# ============================================================================
# 主命令
# ============================================================================

@cli.command()
@click.option('--version', is_flag=True, help='显示版本')
def info(version):
    """显示工具信息"""
    if version:
        click.echo("Version: 1.0.0")
    else:
        click.secho("\n🎯 Linux 性能和稳定性监控工具", fg='cyan', bold=True)
        click.echo("\n使用命令:")
        click.echo("  memory status           - 显示当前内存状态")
        click.echo("  memory health           - 检查内存健康状态")
        click.echo("  memory structure        - 显示内存结构分析")
        click.echo("  memory top-processes    - 显示TOP进程")
        click.echo("  memory process-info     - 查看进程信息")
        click.echo("  memory monitor          - 监控趋势")
        click.echo()
        click.echo("  network check           - 网络健康检查")
        click.echo("  network monitor-net     - 监控流量")
        click.echo()

if __name__ == '__main__':
    cli()
