import click
from time import sleep
import lpm
from lpm import get_network_monitor

def display_network(interface: str, interval: float):
    try:
        stats = network_stats(interface)
        up, down = network_speed(interface, interval)
        
        click.echo(f"\n📶 网卡 [{interface}]")
        click.echo(f"   📤 实时: {up:.2f}↑ {down:.2f}↓ MB/s")
        click.echo(f"   📊 累计: {stats['bytes_sent']/1024**2:.1f}↑ {stats['bytes_recv']/1024**2:.1f}↓ MB")
        click.echo(f"   ⚠️ 错误: 输入{stats['errors_in']} 输出{stats['errors_out']}")
        click.echo(f"   ❌ 丢包: 输入{stats['drop_in']} 输出{stats['drop_out']}")
    except Exception as e:
        click.echo(f"\n❌ 网卡 {interface} 错误: {str(e)}")

def check_ringbuffer():
    """检测网卡Ring Buffer丢包情况"""
    monitor = lpm.get_network_monitor()
    
    results = monitor.check_ringbuffer_drops()
    has_issue = False
    
    for interface, message in results.items():
        if message is None:
            click.echo(f"✅ {interface}: PASS")
        else:
            has_issue = True
            click.echo(f"❌ {interface}: {message}")
    
    if has_issue:
        click.echo("\n💡 全局建议:")
        click.echo("1. 临时调整: 执行上述ethtool命令")
        click.echo("2. 永久生效: 将命令添加到/etc/rc.local")
        click.echo("3. 监控效果: watch -n 1 'ethtool -S eth0 | grep drop'")

def check_network(interface, verbose):
    """网络接口健康检查（支持详细模式）"""
    monitor = get_network_monitor()
    
    # 获取健康数据
    try:
        all_health = monitor.check_interface_health()
    except Exception as e:
        click.secho(f"❌ 数据获取失败: {str(e)}", fg='red', err=True)
        return

    # 确定检查范围
    interfaces_to_check = (
        [interface] if interface 
        else sorted(all_health.keys())  # 按字母排序
    )

    # 检查并输出结果
    has_issues = False
    for iface in interfaces_to_check:
        if iface not in all_health:
            click.secho(f"⚠️ 接口不存在: {iface}", fg='yellow', err=True)
            continue

        health = all_health[iface]
        is_problematic = any([
            health.rx_errors > 0,
            health.rx_overruns > 0,
            health.tx_errors > 0,
            health.softnet_dropped > 0
        ])

        # 只在发现问题或verbose模式下显示
        if is_problematic or verbose:
            click.echo(f"\n📡 接口 [ {iface} ] {'(异常)' if is_problematic else '(正常)'}")
            
            # 详细指标表格
            if verbose:
                from rich.table import Table
                from rich.console import Console
                
                console = Console()
                table = Table(title="详细指标", show_header=True)
                table.add_column("类型", style="cyan")
                table.add_column("Errors", justify="right")
                table.add_column("Dropped", justify="right")
                table.add_column("Overruns", justify="right")
                
                table.add_row(
                    "RX",
                    str(health.rx_errors),
                    str(health.rx_dropped),
                    str(health.rx_overruns)
                )
                table.add_row(
                    "TX",
                    str(health.tx_errors),
                    str(health.tx_dropped),
                    str(health.tx_overruns)
                )
                console.print(table)
            else:
                # 简洁模式输出
                click.echo(f"  RX errors: {health.rx_errors} | dropped: {health.rx_dropped} | overruns: {health.rx_overruns}")
                click.echo(f"  TX errors: {health.tx_errors} | dropped: {health.tx_dropped} | overruns: {health.tx_overruns}")

        # 诊断建议
        advice = monitor.get_health_advice(iface, health)
        if advice:
            has_issues = True
            click.secho("  ⚠️ 发现问题:", fg='yellow')
            for item in advice:
                click.echo(f"    • {item}")
        elif verbose:
            click.secho("  ✅ 所有指标正常", fg='green')

    # 总结报告
    if has_issues:
        click.secho("\n💡 修复建议:", fg='cyan')
        click.echo("1. 临时调整: 使用上述命令立即修改参数")
        click.echo("2. 永久生效: 将配置写入/etc/sysctl.conf或/etc/rc.local")
        click.echo("3. 监控变化: watch -n 1 'cat /proc/net/softnet_stat'")
    elif not verbose:
        click.secho("\n✅ 所有接口检查通过", fg='green')

def check_arp(verbose):
    """网络诊断工具"""
    monitor = get_network_monitor()

    click.secho("\n🔍 ARP系统诊断报告", fg='cyan', bold=True)

    # 1. 检查arp_ignore
    value, advice = monitor.check_arp_ignore()
    if verbose or advice:
        click.echo(f"\n[ARP Ignore] 当前值: {value}")
        for msg in advice:
            click.secho(msg, fg='yellow')

    # 2. 检查arp_filter  
    value, advice = monitor.check_arp_filter()
    if verbose or advice:
        click.echo(f"\n[ARP Filter] 当前值: {value}")
        for msg in advice:
            click.secho(msg, fg='yellow')

    # 3. 检查ARP表溢出
    is_overflow, advice = monitor.check_arp_table_overflow()
    if verbose or is_overflow:
        status = "⚠️ 异常" if is_overflow else "✅ 正常"
        click.echo(f"\n[ARP表状态] {status}")
        for msg in advice:
            click.secho(msg, fg='red' if is_overflow else 'yellow')

    # 4. 检查ARP队列溢出
    is_overflow, advice = monitor.check_arp_queue_overflow()
    if verbose or is_overflow:
        status = "⚠️ 异常" if is_overflow else "✅ 正常"
        click.echo(f"\n[ARP队列] {status}")
        for msg in advice:
            click.secho(msg, fg='red' if is_overflow else 'yellow')

def check_connect_track():
    """connect track网络诊断工具"""
    monitor = get_network_monitor()

    click.secho("\n🔍 连接跟踪诊断报告", fg='cyan', bold=True)

    # 1. 检查表溢出
    is_overflow, advice = monitor.check_conntrack_overflow()
    if is_overflow or True:  # 总是显示此检查项
        status = "⚠️ 异常" if is_overflow else "✅ 正常" 
        click.echo(f"\n[表溢出检测] {status}")
        for msg in advice:
            click.secho(msg, fg='red' if is_overflow else 'yellow')

    # 2. 检查创建错误
    errors, advice = monitor.check_conntrack_errors()
    if any(errors.values()):
        click.echo("\n[创建错误检测] ⚠️ 异常")
        for msg in advice:
            click.secho(msg, fg='red')
    else:
        click.echo("\n[创建错误检测] ✅ 正常")

    # 3. 检查老化时间
    has_issue, advice = monitor.check_conntrack_aging()
    if has_issue:
        click.echo("\n[老化时间检测] ⚠️ 异常")
        for msg in advice:
            click.secho(msg, fg='yellow')
    else:
        click.echo("\n[老化时间检测] ✅ 正常")

def check_ip_fragment():
    """网络诊断工具"""
    monitor = get_network_monitor()

    click.secho("\n🔍 IP分片重组诊断", fg='cyan', bold=True)
    health, advice = monitor.check_ip_fragmentation()

    click.echo(f"\n📊 分片统计:")
    click.echo(f"  超时丢包数: {health.timeout_drops}")
    click.echo(f"  重组失败数: {health.reassembly_fails}")

    click.echo("\n⚙️ 当前内核参数:")
    click.echo(f"  ipfrag_time: {health.frag_timeout}秒")
    click.echo(f"  ipfrag_high_thresh: {health.frag_high_thresh}字节")
    click.echo(f"  ipfrag_low_thresh: {health.frag_low_thresh}字节")

    if advice:
        click.secho("\n⚠️ 发现问题:", fg='yellow')
        for msg in advice:
            click.echo(msg)
    else:
        click.secho("\n✅ 未检测到分片重组问题", fg='green')

def check_tcp_timewait():
    """网络诊断工具"""
    from lpm import get_network_monitor
    monitor = get_network_monitor()

    click.secho("\n🔍 TCP TIMEWAIT 诊断报告", fg='cyan', bold=True)
    
    health, advice = monitor.check_tcp_timewait()
    
    # 显示基础状态
    click.echo("\n[基本状态]")
    click.echo(f"  最大TIME-WAIT数量: {health.max_tw_buckets or 'N/A'}")
    click.echo(f"  当前TIME-WAIT数量: {health.current_tw or 'N/A'}")
    click.echo(f"  超时时间: {health.timewait_timeout or 'N/A'}秒")
    
    # 显示问题和建议
    if advice:
        click.secho("\n[问题检测]", fg='red' if health.overflow_drops else 'yellow')
        for msg in advice:
            lines = msg.split('\n')
            first_line = lines[0]
            rest_lines = lines[1:] if len(lines) > 1 else []
            
            if first_line.startswith("⚠️"):
                click.secho(first_line, fg='yellow')
            else:
                click.echo(first_line)
            
            for line in rest_lines:
                click.echo(f"  {line}")
    else:
        click.secho("\n[状态] ✅ 未检测到异常", fg='green')

def check_tcp_connectqueue():
    """网络诊断工具"""
    monitor = get_network_monitor()

    click.secho("\n🔍 TCP队列诊断报告", fg='cyan', bold=True)
    
    health, advice = monitor.check_tcp_queue()
    
    # 显示基础统计
    click.echo("\n[基础统计]")
    click.echo(f"  SYN丢弃数: {health.syn_drops or 0}")
    click.echo(f"  队列溢出次数: {health.queue_overflows or 0}")
    click.echo(f"  系统somaxconn值: {health.somaxconn or '未知'}")
    
    # 显示详细问题和建议
    if advice:
        click.secho("\n[问题诊断]", fg='yellow')
        for msg in advice:
            # 格式化输出带缩进的多行建议
            lines = msg.split('\n')
            click.secho(lines[0], fg='red' if '丢弃' in lines[0] else 'yellow')
            for line in lines[1:]:
                click.echo(f"  {line}")
    else:
        click.secho("\n[状态] ✅ 未检测到队列异常", fg='green')

def check_syn_flood():
    """网络诊断工具"""
    from lpm import get_network_monitor
    monitor = get_network_monitor()

    click.secho("\n🔍 SYN Flood攻击检测", fg='cyan', bold=True)
    
    health, advice = monitor.check_syn_flood()
    
    # 显示基础信息
    click.echo("\n[当前防护参数]")
    click.echo(f"  tcp_max_syn_backlog: {health.current_backlog or '默认'}")
    click.echo(f"  tcp_synack_retries: {health.current_synack_retries or '默认'}")
    
    # 显示检测结果和建议
    if health.detected:
        click.secho("\n[攻击检测]", fg='red')
        click.echo(f"受攻击端口: {', '.join(health.attack_ports)}")
        
        click.secho("\n[防御建议]", fg='yellow')
        for msg in advice:
            # 格式化多行输出
            lines = msg.split('\n')
            if lines[0].startswith("⚠️"):
                click.secho(lines[0], fg='red')
            else:
                click.echo(lines[0])
            
            for line in lines[1:]:
                if line.strip():
                    click.echo(f"  {line}")
    else:
        click.secho("\n[状态] ✅ 未检测到SYN Flood攻击迹象", fg='green')

def check_tcp_timestamp():
    """网络诊断工具"""
    monitor = get_network_monitor()


    click.secho("\n🔍 TCP时间戳机制检测", fg='cyan', bold=True)
    
    health, advice = monitor.check_tcp_timestamp()
    
    # 显示统计信息
    click.echo("\n[丢包统计]")
    click.echo(f"  被动连接拒绝: {health.rejected_passive or 0}")
    click.echo(f"  已建立连接拒绝: {health.rejected_established or 0}")
    click.echo(f"  tcp_tw_recycle状态: {'开启' if health.tcp_tw_recycle else '关闭'}")
    
    # 显示建议
    if advice:
        click.secho("\n[问题诊断]", fg='yellow')
        for msg in advice:
            lines = msg.split('\n')
            click.secho(lines[0], fg='red' if lines[0].startswith("⚠️") else 'yellow')
            for line in lines[1:]:
                if line.strip():
                    click.echo(f"  {line}")
    else:
        click.secho("\n[状态] ✅ 未检测到时间戳机制导致的丢包", fg='green')

def check_tcp_disorder():
    """网络诊断工具"""
    from lpm import get_network_monitor
    monitor = get_network_monitor()

    click.secho("\n🔍 TCP乱序丢包检测 (待实现)", fg='cyan', bold=True)
    health, advice = monitor.check_tcp_disorder()
    for msg in advice:
        click.echo(f"  {msg}")

def check_tcp_congestion():
    """网络诊断工具"""
    from lpm import get_network_monitor
    monitor = get_network_monitor()

    click.secho("\n🔍 TCP拥塞控制检测 (待实现)", fg='cyan', bold=True)
    health, advice = monitor.check_tcp_congestion()
    for msg in advice:
        click.echo(f"  {msg}")

def check_tcp_lowlat():
    """网络诊断工具"""
    from lpm import get_network_monitor
    monitor = get_network_monitor()

    click.secho("\n🔍 低时延网络TCP检测 (部分实现)", fg='cyan', bold=True)
    health, advice = monitor.check_tcp_low_latency()
    
    click.echo("\n[当前配置]")
    for msg in filter(lambda x: not x.startswith(('\n','⏳','⚠️','🔧')), advice[:1]):
        click.echo(f"  {msg}")
        
    click.secho("\n[待实现功能]", fg='yellow')
    for msg in advice[1:]:
        if msg.strip():
            prefix = "  " if not msg.startswith(('⏳','⚠️','🔧')) else ""
            click.secho(f"{prefix}{msg}", 
                fg='red' if msg.startswith('⚠️') else 'yellow')

def check_udp_loss():
    """网络诊断工具"""
    from lpm import get_network_monitor
    monitor = get_network_monitor()

    click.secho("\n🔍 UDP丢包检测 (待实现)", fg='cyan', bold=True)
    health, advice = monitor.check_udp_loss()
    for msg in advice:
        click.echo(f"  {msg}")


def check_sock_buf():
    """网络诊断工具"""
    from lpm import get_network_monitor
    monitor = get_network_monitor()

    click.secho("\n🔍 Socket缓冲区检测 (待实现)", fg='cyan', bold=True)
    health, advice = monitor.check_socket_buffer()
    for msg in advice:
        click.echo(f"  {msg}")

@click.command()
@click.option('--interval', default=1.0, help='刷新间隔(秒)')
@click.option('--interface', default=None, help='监控的网卡名称')
@click.option('--list', default=False, help='列出所有可用网卡')
@click.option('--check', default=False, help='系统网络情况检测')
@click.option('--verbose', default=False, help='显示详细信息')
def monitor(interval, interface, list, check, verbose):
    """网络性能监控工具"""

    if list:
        interfaces = lpm.list_network_interfaces()
        click.echo("🖇️ 可用网卡: " + ", ".join(interfaces))
        return

    if check:
        check_ringbuffer()
        check_network(interface, verbose)
        check_arp(verbose)
        check_connect_track()
        check_ip_fragment()
        check_tcp_timewait()
        check_tcp_connectqueue()
        check_syn_flood()
        check_tcp_timestamp()
        check_tcp_disorder()
        check_tcp_congestion()
        check_tcp_lowlat()
        check_udp_loss()
        check_sock_buf()
        return

    try:
        while True:
            click.clear()
            # 显示基础信息
            #click.echo(f"🖥️  CPU: {cpu_usage(interval):.1f}%")
            #mem = memory_usage()
            #click.echo(f"💾 内存: {mem.used/1024**2:.1f}/{mem.total/1024**2:.1f} MB")
            
            # 显示网络信息
            display_network(interface, interval)

            sleep(interval)
    except KeyboardInterrupt:
        click.echo("\n监控已停止")

if __name__ == '__main__':
    monitor()
