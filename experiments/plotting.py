"""
Plotting and visualization for experiment results
"""
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List, Dict
from dataclasses import asdict
import pandas as pd
import logging


logger = logging.getLogger('ExperimentRunner')


def calculate_throughput_series(completed_timeline: List[int], time_points: List[float], window_s: float = 30.0) -> List[float]:
    """Calculate moving average throughput over time (tasks per second)."""
    if not completed_timeline or not time_points:
        return []
    
    throughput = []
    for i, current_time in enumerate(time_points):
        cutoff_time = current_time - window_s
        start_idx = 0
        for j in range(i - 1, -1, -1):
            if time_points[j] <= cutoff_time:
                start_idx = j
                break
        
        if start_idx < i:
            completed_at_start = completed_timeline[start_idx]
            completed_now = completed_timeline[i]
            actual_window = current_time - time_points[start_idx]
            
            if actual_window > 0:
                tps = (completed_now - completed_at_start) / actual_window
                throughput.append(tps * 60.0)
            else:
                throughput.append(0.0)
        else:
            if current_time > 0:
                throughput.append(completed_timeline[i] / current_time * 60.0)
            else:
                throughput.append(0.0)
    
    return throughput


def calculate_latency_series(latency_samples: List[float], completed_timeline: List[int], window_size: int = 50) -> List[float]:
    """Calculate rolling average latency over completed tasks."""
    if not latency_samples or not completed_timeline:
        return []
    
    latency_series = []
    current_task_idx = 0
    
    for num_completed in completed_timeline:
        if num_completed > 0 and current_task_idx < len(latency_samples):
            start_idx = max(0, current_task_idx - window_size + 1)
            end_idx = min(current_task_idx + 1, len(latency_samples))
            
            if start_idx < end_idx:
                window_latencies = latency_samples[start_idx:end_idx]
                avg_lat = sum(window_latencies) / len(window_latencies)
                latency_series.append(avg_lat)
            else:
                latency_series.append(0.0)
            
            if current_task_idx < num_completed:
                current_task_idx = min(num_completed, len(latency_samples))
        else:
            latency_series.append(latency_series[-1] if latency_series else 0.0)
    
    return latency_series


def generate_dashboard_reports(results, timestamp: str, out_dir: Path):
    """Generate per-experiment dashboard-style plots and CSV with key metrics."""
    successful = [r for r in results if r.success]
    if not successful:
        return
    rows = []
    for r in successful:
        perf = r.metrics.get('performance', {})
        ts = r.metrics.get('time_series', {})
        steps = ts.get('steps', [])
        created = ts.get('tasks_created_timeline', [])
        completed = ts.get('task_completion_timeline', [])
        active = ts.get('tasks_active_timeline', [])
        lat_samples = ts.get('latency_samples_s', [])
        step_interval_ms = perf.get('step_interval_ms', 100)
        step_dt = step_interval_ms / 1000.0
        
        time_points = [s * step_dt for s in steps]
        throughput_series = calculate_throughput_series(completed, time_points, window_s=30.0)
        latency_series = calculate_latency_series(lat_samples, completed, window_size=50)
        
        fig, axes = plt.subplots(2, 2, figsize=(18, 10))
        axes = axes.flatten()
        
        # Task Timeline
        if time_points and created and completed and active:
            axes[0].plot(time_points, created, color='tab:blue', linewidth=2, label='Created', alpha=0.8)
            axes[0].plot(time_points, completed, color='tab:green', linewidth=2, label='Completed', alpha=0.8)
            axes[0].plot(time_points, active, color='tab:orange', linewidth=2, label='Active', alpha=0.8)
            axes[0].set_title(f"Task Timeline: {r.config_name}")
            axes[0].set_xlabel('Time (s)')
            axes[0].set_ylabel('Task Count')
            axes[0].legend()
            axes[0].grid(True, alpha=0.3)
        else:
            axes[0].text(0.5, 0.5, 'No task timeline data', ha='center', va='center', transform=axes[0].transAxes)
            axes[0].set_title(f"Task Timeline: {r.config_name}")
        
        # Throughput
        if throughput_series:
            thr_time_points = time_points[:len(throughput_series)]
            axes[1].plot(thr_time_points, throughput_series, color='tab:orange', linewidth=2, label='30s moving avg')
            axes[1].set_title('Throughput over time')
            axes[1].set_xlabel('Time (s)')
            axes[1].set_ylabel('Tasks/min')
            axes[1].legend()
            axes[1].grid(True, alpha=0.3)
        else:
            axes[1].text(0.5, 0.5, 'No throughput data', ha='center', va='center', transform=axes[1].transAxes)
            axes[1].set_title('Throughput over time')
        
        # Latency
        if latency_series:
            lat_time_points = time_points[:len(latency_series)]
            axes[2].plot(lat_time_points, latency_series, color='tab:green', linewidth=2, label='Rolling avg (50 tasks)')
            axes[2].set_title('Latency over time')
            axes[2].set_xlabel('Time (s)')
            axes[2].set_ylabel('Latency (s)')
            axes[2].legend()
            axes[2].grid(True, alpha=0.3)
        else:
            axes[2].text(0.5, 0.5, 'No latency data', ha='center', va='center', transform=axes[2].transAxes)
            axes[2].set_title('Latency over time')
        
        # Utilization
        util_working = ts.get('utilization_working_timeline', [])
        util_active = ts.get('utilization_active_timeline', [])
        
        if util_working and util_active and len(util_working) > 0:
            util_time_points = time_points[:len(util_working)]
            axes[3].plot(util_time_points, util_working, color='tab:blue', linewidth=2.5, label='Working', alpha=0.9)
            axes[3].plot(util_time_points, util_active, color='tab:orange', linewidth=2.5, label='Active (Working + Navigating)', alpha=0.9)
            axes[3].set_title('Agent Utilization over time')
            axes[3].set_xlabel('Time (s)')
            axes[3].set_ylabel('Utilization (fraction of agents)')
            axes[3].set_ylim([0, 1.05])
            axes[3].legend(loc='best')
            axes[3].grid(True, alpha=0.3)
        else:
            axes[3].text(0.5, 0.5, f'No utilization data', ha='center', va='center', transform=axes[3].transAxes, fontsize=10)
            axes[3].set_title('Agent Utilization over time')
            axes[3].set_xlabel('Time (s)')
            axes[3].set_ylabel('Utilization (fraction of agents)')
            axes[3].set_ylim([0, 1.0])
            axes[3].grid(True, alpha=0.3)
        
        plt.tight_layout()
        # Include seed in filename if present to avoid overwrites
        seed_suffix = f"_seed{r.seed}" if hasattr(r, 'seed') and r.seed is not None else ""
        out_png = out_dir / f"dashboard_report_{r.config_name}{seed_suffix}_{timestamp}.png"
        plt.savefig(out_png, dpi=200)
        plt.close(fig)
        
        # Generate separate system performance plot
        generate_system_perf_plot(r, timestamp, out_dir, time_points, ts)
        
        row = {
            'config_name': r.config_name,
            'seed': r.seed if hasattr(r, 'seed') else None,
            'tasks_completed': perf.get('tasks_completed', 0),
            'tasks_failed': perf.get('tasks_failed', 0),
            'completion_rate': perf.get('completion_rate', 0.0),
            'avg_latency_s': perf.get('average_completion_time', 0.0),
            'p50_latency_s': perf.get('latency_p50', 0.0),
            'p90_latency_s': perf.get('latency_p90', 0.0),
            'p99_latency_s': perf.get('latency_p99', 0.0),
            'throughput_tps': perf.get('throughput_tps', 0.0),
        }
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / f"dashboard_metrics_{timestamp}.csv", index=False)


def generate_system_perf_plot(result, timestamp: str, out_dir: Path, time_points: List[float], ts: Dict):
    """Generate standalone system performance plot (cache, gossip, contention, etc.)."""
    cache_entries = ts.get('cache_entries_timeline', [])
    coord = result.metrics.get('coordination', {})
    
    if not cache_entries:
        return
    
    fig, axes = plt.subplots(2, 3, figsize=(20, 10))
    axes = axes.flatten()
    
    # Cache entries
    cache_time_points = time_points[:len(cache_entries)]
    if cache_entries:
        axes[0].plot(cache_time_points, cache_entries, color='tab:purple', linewidth=2)
        axes[0].set_title(f'DSM Cache Entries: {result.config_name}')
        axes[0].set_xlabel('Time (s)')
        axes[0].set_ylabel('Total Cache Entries')
        axes[0].grid(True, alpha=0.3)
    
    # DSM Overhead
    high_labels = ['Avg Cache\nSize', 'Total Gossip\nRounds']
    high_values = [
        coord.get('avg_cache_size', 0),
        coord.get('total_gossip_rounds', 0)
    ]
    colors_high = ['tab:purple', 'tab:cyan']
    axes[1].bar(high_labels, high_values, color=colors_high, alpha=0.7)
    axes[1].set_title('DSM Overhead')
    axes[1].set_ylabel('Count')
    axes[1].grid(True, alpha=0.3, axis='y')
    
    # Coordinator State
    low_labels = ['Tasks in\nRegistry', 'Active\nLeases']
    low_values = [
        coord.get('tasks_in_registry', 0),
        coord.get('active_leases', 0)
    ]
    colors_low = ['tab:orange', 'tab:red']
    axes[2].bar(low_labels, low_values, color=colors_low, alpha=0.7)
    axes[2].set_title('Coordinator State')
    axes[2].set_ylabel('Count')
    axes[2].grid(True, alpha=0.3, axis='y')
    
    # Congestion
    num_jammed_nodes = ts.get('num_jammed_nodes_timeline', [])
    jam_intensity_avg = ts.get('jam_intensity_avg_timeline', [])
    
    if num_jammed_nodes and jam_intensity_avg:
        contention_time = time_points[:len(num_jammed_nodes)]
        axes[3].plot(contention_time, num_jammed_nodes, color='#1f77b4', linewidth=2.5, label='# Jammed Nodes', alpha=0.9)
        ax3_twin = axes[3].twinx()
        ax3_twin.plot(contention_time, jam_intensity_avg, color='#9467bd', linewidth=2.5, label='Avg Jam Severity', alpha=0.9, linestyle='--')
        
        axes[3].set_title('Congestion: Spread vs Severity')
        axes[3].set_xlabel('Time (s)')
        axes[3].set_ylabel('# Jammed Nodes (spread)', color='#1f77b4')
        axes[3].tick_params(axis='y', labelcolor='#1f77b4')
        ax3_twin.set_ylabel('Avg Jam Severity (0-5)', color='#9467bd')
        ax3_twin.tick_params(axis='y', labelcolor='#9467bd')
        ax3_twin.set_ylim([0, 5.5])
        axes[3].grid(True, alpha=0.3)
        
        lines1, labels1 = axes[3].get_legend_handles_labels()
        lines2, labels2 = ax3_twin.get_legend_handles_labels()
        axes[3].legend(lines1 + lines2, labels1 + labels2, loc='best', fontsize=9)
    else:
        axes[3].text(0.5, 0.5, f'No congestion data', ha='center', va='center', transform=axes[3].transAxes, fontsize=10)
        axes[3].set_title('Congestion: Spread vs Severity')
    
    # Point Contention
    num_stuck = ts.get('num_stuck_agents_timeline', [])
    avg_stuck_counter = ts.get('avg_stuck_counter_timeline', [])
    
    if num_stuck and avg_stuck_counter:
        stall_time = time_points[:len(num_stuck)]
        axes[4].plot(stall_time, num_stuck, color='#d62728', linewidth=2.5, label='# Stalled Agents', alpha=0.9)
        ax4_twin = axes[4].twinx()
        ax4_twin.plot(stall_time, avg_stuck_counter, color='#ff7f0e', linewidth=2.5, label='Avg Stall Duration', alpha=0.9, linestyle='--')
        
        axes[4].set_title('Point Contention: Stalled Agents vs Stall Duration')
        axes[4].set_xlabel('Time (s)')
        axes[4].set_ylabel('# Stalled Agents (count)', color='#d62728')
        axes[4].tick_params(axis='y', labelcolor='#d62728')
        ax4_twin.set_ylabel('Avg Stall Duration (steps)', color='#ff7f0e')
        ax4_twin.tick_params(axis='y', labelcolor='#ff7f0e')
        axes[4].grid(True, alpha=0.3)
        
        lines1, labels1 = axes[4].get_legend_handles_labels()
        lines2, labels2 = ax4_twin.get_legend_handles_labels()
        axes[4].legend(lines1 + lines2, labels1 + labels2, loc='best', fontsize=9)
    else:
        axes[4].text(0.5, 0.5, f'No point contention data', ha='center', va='center', transform=axes[4].transAxes, fontsize=10)
        axes[4].set_title('Point Contention: Stalled Agents vs Stall Duration')
    
    # Stall Location Breakdown
    stalls_in_transit = ts.get('stalls_in_transit_timeline', [])
    stalls_at_resource = ts.get('stalls_at_resource_timeline', [])
    stalls_idle = ts.get('stalls_idle_timeline', [])
    
    if stalls_in_transit and stalls_at_resource:
        stall_loc_time = time_points[:len(stalls_in_transit)]
        axes[5].stackplot(stall_loc_time,
                         stalls_in_transit,
                         stalls_at_resource,
                         stalls_idle,
                         labels=['In Transit (Aisle)', 'At Resource (Pickup/Drop)', 'Idle'],
                         colors=['#8c564b', '#e377c2', '#7f7f7f'],
                         alpha=0.7)
        
        axes[5].set_title('Stall Location Breakdown: Where Agents Get Stuck')
        axes[5].set_xlabel('Time (s)')
        axes[5].set_ylabel('# Stalled Agents by Location')
        axes[5].legend(loc='upper right', fontsize=9)
        axes[5].grid(True, alpha=0.3)
    else:
        axes[5].text(0.5, 0.5, f'No stall location data', ha='center', va='center', transform=axes[5].transAxes, fontsize=10)
        axes[5].set_title('Stall Location Breakdown')
    
    plt.tight_layout()
    # Include seed in filename
    seed_suffix = f"_seed{result.seed}" if hasattr(result, 'seed') and result.seed is not None else ""
    out_png = out_dir / f"system_perf_{result.config_name}{seed_suffix}_{timestamp}.png"
    plt.savefig(out_png, dpi=200)
    plt.close(fig)

