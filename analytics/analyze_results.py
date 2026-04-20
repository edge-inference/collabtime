#!/usr/bin/env python3
"""
Analysis and Comparison Tool for Warehouse Simulation Results

Usage:
    python analyze_results.py --robots 1000 --compare
    python analyze_results.py --run run021 --compare --robots 1000
    python analyze_results.py --sweep 600-1000 --metric throughput
    python analyze_results.py --unified  # All metrics, full robot range
    python analyze_results.py --table    # Summary table
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent))


class ResultsAnalyzer:
    """Analyze and compare simulation results across runs."""
    
    def __init__(self, results_dir: str = "results"):
        self.results_dir = Path(results_dir)
        self.experiments = self._load_all_experiments()
        self.experiments = self._deduplicate_experiments(self.experiments)
    
    def _load_all_experiments(self) -> List[Dict]:
        """Load all experiment results from all runs."""
        experiments = []
        
        for run_dir in sorted(self.results_dir.glob("run*")):
            if not run_dir.is_dir():
                continue
            
            for mode in ['distributed', 'centralized']:
                mode_dir = run_dir / mode
                if not mode_dir.exists():
                    continue
                
                json_files = list(mode_dir.glob("experiment_details_*.json"))
                
                if json_files:
                    experiments.extend(self._load_flat_structure(run_dir, mode, mode_dir, json_files))
                else:
                    for exp_dir in mode_dir.iterdir():
                        if not exp_dir.is_dir():
                            continue
                        
                        json_files = list(exp_dir.glob("experiment_details_*.json"))
                        if not json_files:
                            continue
                        
                        latest_json = max(json_files, key=lambda p: p.stat().st_mtime)
                        
                        try:
                            with open(latest_json) as f:
                                data = json.load(f)
                            
                            if 'result' in data and data['result']['success']:
                                exp_info = {
                                    'run': run_dir.name,
                                    'mode': mode,
                                    'config_name': data['config_name'],
                                    'seed': data.get('seed', 42),
                                    'exp_dir': exp_dir,
                                    'data': data['result']
                                }
                                experiments.append(exp_info)
                        except Exception as e:
                            print(f"Warning: Failed to load {latest_json}: {e}")
        
        return experiments
    
    def _load_flat_structure(self, run_dir: Path, mode: str, mode_dir: Path, json_files: List[Path]) -> List[Dict]:
        """Load experiments from old flat structure (run013 style)."""
        experiments = []
        
        for json_file in json_files:
            try:
                with open(json_file) as f:
                    data = json.load(f)
                
                if 'results' in data:
                    for result in data['results']:
                        if result.get('success', True):
                            exp_info = {
                                'run': run_dir.name,
                                'mode': mode,
                                'config_name': result['config_name'],
                                'seed': result.get('seed', 42),
                                'exp_dir': mode_dir,
                                'data': result
                            }
                            experiments.append(exp_info)
                
                elif 'result' in data and data['result'].get('success', True):
                    exp_info = {
                        'run': run_dir.name,
                        'mode': mode,
                        'config_name': data['config_name'],
                        'seed': data.get('seed', 42),
                        'exp_dir': mode_dir,
                        'data': data['result']
                    }
                    experiments.append(exp_info)
                    
            except Exception as e:
                print(f"Warning: Failed to load {json_file}: {e}")
        
        return experiments
    
    def _deduplicate_experiments(self, experiments: List[Dict]) -> List[Dict]:
        """Remove duplicate experiments (same run + mode + config + seed)."""
        seen = {}
        deduplicated = []
        
        for exp in experiments:
            key = (exp['run'], exp['mode'], exp['config_name'], exp['seed'])
            if key not in seen:
                seen[key] = exp
                deduplicated.append(exp)
        
        return deduplicated
    
    def filter_experiments(self, 
                          run: Optional[str] = None,
                          mode: Optional[str] = None,
                          agents: Optional[int] = None,
                          config_pattern: Optional[str] = None) -> List[Dict]:
        """Filter experiments by criteria."""
        filtered = self.experiments
        
        if run:
            filtered = [e for e in filtered if e['run'] == run]
        
        if mode:
            filtered = [e for e in filtered if e['mode'] == mode]
        
        if agents:
            filtered = [e for e in filtered if f"{agents}_agents" in e['config_name']]
        
        if config_pattern:
            filtered = [e for e in filtered if config_pattern in e['config_name']]
        
        return filtered
    
    def get_paired_experiments(self, robots: int, run: Optional[str] = None) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Get distributed and centralized experiments for the same robot count."""
        exps = self.filter_experiments(agents=robots, run=run)
        
        dist = next((e for e in exps if e['mode'] == 'distributed'), None)
        cent = next((e for e in exps if e['mode'] == 'centralized'), None)
        
        return dist, cent
    
    def plot_comparison(self, robots: int, run: Optional[str] = None, output_path: Optional[Path] = None):
        """Create side-by-side comparison plot for distributed vs centralized."""
        dist, cent = self.get_paired_experiments(robots, run)
        
        if not dist or not cent:
            print(f"Error: Could not find both distributed and centralized experiments for {robots} robots")
            if run:
                print(f"  in run {run}")
            return
        
        fig = plt.figure(figsize=(20, 12))
        gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.3, wspace=0.3)
        
        dist_data = dist['data']
        cent_data = cent['data']
        
        dist_ts = dist_data['metrics']['time_series']
        cent_ts = cent_data['metrics']['time_series']
        
        dist_perf = dist_data['metrics']['performance']
        cent_perf = cent_data['metrics']['performance']
        
        dist_steps = np.array(dist_ts['steps']) * dist_perf['step_interval_ms'] / 1000.0
        cent_steps = np.array(cent_ts['steps']) * cent_perf['step_interval_ms'] / 1000.0
        
        fig.suptitle(f'Distributed vs Centralized Comparison: {robots} Robots', 
                    fontsize=16, fontweight='bold', y=0.995)
        
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.plot(dist_steps, dist_ts['task_completion_timeline'], 'b-', label='Distributed', linewidth=2)
        ax1.plot(cent_steps, cent_ts['task_completion_timeline'], 'r-', label='Centralized', linewidth=2)
        ax1.set_xlabel('Time (s)')
        ax1.set_ylabel('Tasks Completed')
        ax1.set_title('Task Completion Over Time')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.plot(dist_steps, dist_ts['tasks_active_timeline'], 'b-', label='Distributed', linewidth=2)
        ax2.plot(cent_steps, cent_ts['tasks_active_timeline'], 'r-', label='Centralized', linewidth=2)
        ax2.set_xlabel('Time (s)')
        ax2.set_ylabel('Active Tasks')
        ax2.set_title('Queue Length Over Time')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        ax3 = fig.add_subplot(gs[0, 2])
        categories = ['Completion\nRate', 'Throughput\n(tasks/s)', 'Avg Latency\n(s)']
        dist_vals = [
            dist_perf['completion_rate'] * 100,
            dist_perf['throughput_tps'],
            dist_perf['average_completion_time']
        ]
        cent_vals = [
            cent_perf['completion_rate'] * 100,
            cent_perf['throughput_tps'],
            cent_perf['average_completion_time']
        ]
        
        x = np.arange(len(categories))
        width = 0.35
        
        bars1 = ax3.bar(x - width/2, dist_vals, width, label='Distributed', color='blue', alpha=0.7)
        bars2 = ax3.bar(x + width/2, cent_vals, width, label='Centralized', color='red', alpha=0.7)
        
        ax3.set_ylabel('Value')
        ax3.set_title('Performance Metrics Comparison')
        ax3.set_xticks(x)
        ax3.set_xticklabels(categories)
        ax3.legend()
        ax3.grid(True, axis='y', alpha=0.3)
        
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                ax3.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.2f}', ha='center', va='bottom', fontsize=8)
        
        ax4 = fig.add_subplot(gs[1, 0])
        ax4.plot(dist_steps, dist_ts['utilization_working_timeline'], 'b-', label='Distributed', linewidth=2)
        ax4.plot(cent_steps, cent_ts['utilization_working_timeline'], 'r-', label='Centralized', linewidth=2)
        ax4.set_xlabel('Time (s)')
        ax4.set_ylabel('Utilization (fraction)')
        ax4.set_title('Robot Utilization (Working)')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        ax4.set_ylim([0, 1.05])
        
        ax5 = fig.add_subplot(gs[1, 1])
        # Total Distance Comparison (bar chart)
        modes = ['Distributed', 'Centralized']
        distances = [dist_perf['total_distance_traveled'], cent_perf['total_distance_traveled']]
        colors = ['blue', 'red']
        bars = ax5.bar(modes, distances, color=colors, alpha=0.6, edgecolor='black', linewidth=1.5)
        ax5.set_ylabel('Total Distance (cells)')
        ax5.set_title('Total Distance Traveled')
        ax5.grid(True, axis='y', alpha=0.3)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax5.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height):,}', ha='center', va='bottom', fontsize=10)
        
        ax6 = fig.add_subplot(gs[1, 2])
        ax6.plot(dist_steps, dist_ts['num_stuck_agents_timeline'], 'b-', label='Distributed', linewidth=2)
        ax6.plot(cent_steps, cent_ts['num_stuck_agents_timeline'], 'r-', label='Centralized', linewidth=2)
        ax6.set_xlabel('Time (s)')
        ax6.set_ylabel('Stuck Robots')
        ax6.set_title('Stuck Robots Over Time')
        ax6.legend()
        ax6.grid(True, alpha=0.3)
        
        ax7 = fig.add_subplot(gs[2, :])
        
        window = 30
        dist_completed = np.array(dist_ts['task_completion_timeline'])
        cent_completed = np.array(cent_ts['task_completion_timeline'])
        
        dist_throughput = np.gradient(dist_completed) / (dist_perf['step_interval_ms'] / 1000.0)
        cent_throughput = np.gradient(cent_completed) / (cent_perf['step_interval_ms'] / 1000.0)
        
        dist_throughput_smooth = pd.Series(dist_throughput).rolling(window=window, min_periods=1).mean()
        cent_throughput_smooth = pd.Series(cent_throughput).rolling(window=window, min_periods=1).mean()
        
        ax7.plot(dist_steps, dist_throughput_smooth, 'b-', label='Distributed', linewidth=2, alpha=0.8)
        ax7.plot(cent_steps, cent_throughput_smooth, 'r-', label='Centralized', linewidth=2, alpha=0.8)
        ax7.set_xlabel('Time (s)')
        ax7.set_ylabel('Throughput (tasks/s)')
        ax7.set_title(f'Instantaneous Throughput ({window}-step moving average)')
        ax7.legend()
        ax7.grid(True, alpha=0.3)
        
        info_text = (
            f"Distributed: {dist_perf['tasks_completed']}/{dist_data['metrics']['coordination']['tasks_in_registry']} tasks "
            f"({dist_perf['completion_rate']*100:.1f}%), "
            f"throughput={dist_perf['throughput_tps']:.2f} tps\n"
            f"Centralized: {cent_perf['tasks_completed']}/{cent_data['metrics']['coordination']['tasks_in_registry']} tasks "
            f"({cent_perf['completion_rate']*100:.1f}%), "
            f"throughput={cent_perf['throughput_tps']:.2f} tps\n"
            f"Run: {dist['run']}, Seed: {dist['seed']}"
        )
        fig.text(0.5, 0.02, info_text, ha='center', fontsize=10, 
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        if output_path is None:
            output_dir = self.results_dir / f"analysis_{robots}_robots"
            output_dir.mkdir(exist_ok=True, parents=True)
            run_suffix = f"_{run}" if run else ""
            output_path = output_dir / f"comparison_{robots}_robots{run_suffix}.png"
        
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved comparison plot to: {output_path}")
        plt.close()
    
    def plot_scaling_sweep(self, robot_counts: List[int], metric: str = 'throughput', 
                          run: Optional[str] = None, output_path: Optional[Path] = None):
        """Plot how a metric scales with robot count for both modes."""
        dist_values = []
        cent_values = []
        valid_counts = []
        
        for robots in robot_counts:
            exps = self.filter_experiments(agents=robots, run=run)
            
            dist_exps = [e for e in exps if e['mode'] == 'distributed']
            cent_exps = [e for e in exps if e['mode'] == 'centralized']
            
            if dist_exps and cent_exps:
                dist_vals = []
                cent_vals = []
                
                for exp in dist_exps:
                    perf = exp['data']['metrics']['performance']
                    if metric == 'throughput':
                        dist_vals.append(perf['throughput_tps'])
                    elif metric == 'completion_rate':
                        dist_vals.append(perf['completion_rate'] * 100)
                    elif metric == 'latency':
                        dist_vals.append(perf['average_completion_time'])
                    elif metric == 'utilization':
                        dist_vals.append(perf['agent_utilization'] * 100)
                
                for exp in cent_exps:
                    perf = exp['data']['metrics']['performance']
                    if metric == 'throughput':
                        cent_vals.append(perf['throughput_tps'])
                    elif metric == 'completion_rate':
                        cent_vals.append(perf['completion_rate'] * 100)
                    elif metric == 'latency':
                        cent_vals.append(perf['average_completion_time'])
                    elif metric == 'utilization':
                        cent_vals.append(perf['agent_utilization'] * 100)
                
                dist_values.append(np.mean(dist_vals))
                cent_values.append(np.mean(cent_vals))
                valid_counts.append(robots)
        
        if not valid_counts:
            print(f"Error: No data found for scaling sweep")
            return
        
        fig, ax = plt.subplots(figsize=(12, 7))
        
        ax.plot(valid_counts, dist_values, 'bo-', label='Distributed', linewidth=2, markersize=8)
        ax.plot(valid_counts, cent_values, 'rs-', label='Centralized', linewidth=2, markersize=8)
        
        ax.set_xlabel('Number of Robots', fontsize=12)
        
        ylabel_map = {
            'throughput': 'Throughput (tasks/s)',
            'completion_rate': 'Completion Rate (%)',
            'latency': 'Average Latency (s)',
            'utilization': 'Robot Utilization (%)'
        }
        ax.set_ylabel(ylabel_map.get(metric, metric.title()), fontsize=12)
        ax.set_title(f'{metric.replace("_", " ").title()} Scaling: Distributed vs Centralized', 
                    fontsize=14, fontweight='bold')
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)
        
        for i, robots in enumerate(valid_counts):
            ax.text(robots, dist_values[i], f'{dist_values[i]:.2f}', 
                   ha='center', va='bottom', fontsize=9)
            ax.text(robots, cent_values[i], f'{cent_values[i]:.2f}', 
                   ha='center', va='top', fontsize=9)
        
        if output_path is None:
            output_dir = self.results_dir / "analysis_scaling"
            output_dir.mkdir(exist_ok=True, parents=True)
            robot_range = f"{min(valid_counts)}-{max(valid_counts)}"
            output_path = output_dir / f"scaling_{metric}_{robot_range}_robots.png"
        
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved scaling plot to: {output_path}")
        plt.close()
    
    def plot_unified_scaling(self, run: Optional[str] = None, output_path: Optional[Path] = None):
        """Create unified 2x2 scaling plot with all metrics across full robot range."""
        import re
        
        data_by_robots = {}
        for exp in self.experiments:
            if run and exp['run'] != run:
                continue
            match = re.search(r'(\d+)_agents', exp['config_name'])
            if not match:
                continue
            robots = int(match.group(1))
            mode = exp['mode']
            key = (robots, mode)
            if key not in data_by_robots:
                data_by_robots[key] = []
            data_by_robots[key].append(exp)
        
        all_robots = sorted(set([r for r, m in data_by_robots.keys()]))
        if not all_robots:
            print("Error: No experiments found")
            return
        
        metrics = {
            'throughput': {'label': 'Throughput (tasks/s)', 'key': 'throughput_tps'},
            'completion_rate': {'label': 'Completion Rate (%)', 'key': 'completion_rate', 'mult': 100},
            'latency': {'label': 'Average Latency (s)', 'key': 'average_completion_time'},
            'utilization': {'label': 'Robot Utilization (%)', 'key': 'agent_utilization', 'mult': 100}
        }
        
        summary = {}
        for (robots, mode), exps in data_by_robots.items():
            vals = {}
            for metric, cfg in metrics.items():
                raw = [e['data']['metrics']['performance'][cfg['key']] for e in exps]
                mult = cfg.get('mult', 1)
                vals[metric] = np.mean(raw) * mult
                vals[f'{metric}_std'] = np.std(raw) * mult if len(raw) > 1 else 0
            # Communication metrics from coordination section
            comms_raw = [e['data']['metrics']['coordination'].get('comms_per_task', 0) for e in exps]
            vals['comms_per_task'] = np.mean(comms_raw) if comms_raw else 0
            comm_ops_raw = [e['data']['metrics']['coordination'].get('comm_operations', 0) for e in exps]
            vals['comm_operations'] = np.mean(comm_ops_raw) if comm_ops_raw else 0
            vals['count'] = len(exps)
            summary[(robots, mode)] = vals
        
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        
        plot_configs = [
            ('throughput', axes[0, 0], 'Task Throughput Scaling'),
            ('completion_rate', axes[0, 1], 'Task Completion Rate Scaling'),
            ('latency', axes[1, 0], 'Task Latency Scaling'),
            ('utilization', axes[1, 1], 'Robot Utilization Scaling'),
        ]
        
        for metric, ax, title in plot_configs:
            dist_x, dist_y, dist_err = [], [], []
            cent_x, cent_y, cent_err = [], [], []
            
            for robots in all_robots:
                if (robots, 'distributed') in summary:
                    s = summary[(robots, 'distributed')]
                    dist_x.append(robots)
                    dist_y.append(s[metric])
                    dist_err.append(s[f'{metric}_std'])
                if (robots, 'centralized') in summary:
                    s = summary[(robots, 'centralized')]
                    cent_x.append(robots)
                    cent_y.append(s[metric])
                    cent_err.append(s[f'{metric}_std'])
            
            ax.errorbar(dist_x, dist_y, yerr=dist_err, fmt='bo-', label='Distributed', 
                       linewidth=2, markersize=8, capsize=5, capthick=2)
            ax.errorbar(cent_x, cent_y, yerr=cent_err, fmt='rs-', label='Centralized',
                       linewidth=2, markersize=8, capsize=5, capthick=2)
            ax.set_xlabel('Number of Robots', fontsize=12)
            ax.set_ylabel(metrics[metric]['label'], fontsize=12)
            ax.set_title(title, fontsize=13, fontweight='bold')
            ax.legend(fontsize=10)
            ax.grid(True, alpha=0.3)
            
            if metric == 'completion_rate':
                ax.set_ylim([0, 105])
            elif metric == 'utilization':
                ax.set_ylim([0, max(max(dist_y, default=0), max(cent_y, default=0)) * 1.2])
            
            for i, x in enumerate(dist_x):
                ax.text(x, dist_y[i], f'{dist_y[i]:.1f}', ha='center', va='bottom', fontsize=8, color='blue')
            for i, x in enumerate(cent_x):
                ax.text(x, cent_y[i], f'{cent_y[i]:.1f}', ha='center', va='top', fontsize=8, color='red')
        
        plt.tight_layout()
        
        if output_path is None:
            output_dir = self.results_dir / "analysis_scaling"
            output_dir.mkdir(exist_ok=True, parents=True)
            run_suffix = f"_{run}" if run else ""
            output_path = output_dir / f"unified_scaling_{min(all_robots)}-{max(all_robots)}_robots{run_suffix}.png"
        
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved unified scaling plot to: {output_path}")
        plt.close()
        
        self._print_scaling_summary(summary, all_robots)
    
    def _print_scaling_summary(self, summary: Dict, all_robots: List[int]):
        """Print scaling summary table to console."""
        print("\n" + "="*100)
        print("UNIFIED SCALING SUMMARY")
        print("="*100)
        for robots in all_robots:
            if (robots, 'distributed') in summary and (robots, 'centralized') in summary:
                d = summary[(robots, 'distributed')]
                c = summary[(robots, 'centralized')]
                gap = ((d['throughput'] / c['throughput'] - 1) * 100) if c['throughput'] > 0 else 0
                print(f"\n{robots:4d} robots: Distributed {d['throughput']:5.2f} tps | Centralized {c['throughput']:5.2f} tps | Gap: {gap:+5.1f}%")
                print(f"            Completion:  {d['completion_rate']:5.1f}% | {c['completion_rate']:5.1f}% | Gap: {d['completion_rate']-c['completion_rate']:+5.1f}pp")
                lat_gap = ((d['latency']/c['latency']-1)*100) if c['latency'] > 0 else 0
                print(f"            Latency:     {d['latency']:5.0f}s | {c['latency']:5.0f}s | Gap: {lat_gap:+5.1f}%")
                print(f"            Utilization: {d['utilization']:5.1f}% | {c['utilization']:5.1f}% | Gap: {d['utilization']-c['utilization']:+5.1f}pp")
                # Communication metrics (if available)
                d_comms = d.get('comms_per_task', 0)
                c_comms = c.get('comms_per_task', 0)
                if d_comms > 0 or c_comms > 0:
                    comms_gap = ((d_comms/c_comms-1)*100) if c_comms > 0 else 0
                    print(f"            Comms/Task:  {d_comms:5.2f}  | {c_comms:5.2f}  | Gap: {comms_gap:+5.1f}%")
        print()

    def generate_summary_table(self, robots: Optional[int] = None, run: Optional[str] = None, 
                              save_path: Optional[Path] = None) -> pd.DataFrame:
        """Generate summary comparison table."""
        if robots:
            dist, cent = self.get_paired_experiments(robots, run)
            experiments = [e for e in [dist, cent] if e is not None]
        else:
            experiments = self.filter_experiments(run=run)
        
        rows = []
        for exp in experiments:
            perf = exp['data']['metrics']['performance']
            coord = exp['data']['metrics']['coordination']
            
            comm_ops = coord.get('comm_operations', 0)
            comms_per_task = coord.get('comms_per_task', 0)
            
            row = {
                'Config': exp['config_name'],
                'Mode': exp['mode'],
                'Run': exp['run'],
                'Seed': exp['seed'],
                'Tasks Completed': perf['tasks_completed'],
                'Completion Rate (%)': f"{perf['completion_rate']*100:.2f}",
                'Throughput (tps)': f"{perf['throughput_tps']:.2f}",
                'Avg Latency (s)': f"{perf['average_completion_time']:.2f}",
                'P90 Latency (s)': f"{perf['latency_p90']:.2f}",
                'Robot Utilization (%)': f"{perf['agent_utilization']*100:.2f}",
                'Comm Operations': f"{comm_ops:,}",
                'Comms/Task': f"{comms_per_task:.2f}",
                'Total Distance': f"{perf['total_distance_traveled']:.0f}",
            }
            rows.append(row)
        
        df = pd.DataFrame(rows)
        
        if save_path:
            df.to_csv(save_path, index=False)
            print(f"Saved summary table to: {save_path}")
        elif len(df) > 0:
            output_dir = self.results_dir / "analysis_tables"
            output_dir.mkdir(exist_ok=True, parents=True)
            
            if robots:
                filename = f"summary_{robots}_robots.csv"
            elif run:
                filename = f"summary_{run}.csv"
            else:
                filename = f"summary_all_experiments.csv"
            
            save_path = output_dir / filename
            df.to_csv(save_path, index=False)
            print(f"Saved summary table to: {save_path}")
        
        return df


def main():
    parser = argparse.ArgumentParser(description='Analyze warehouse simulation results')
    parser.add_argument('--results-dir', default='results', help='Results directory')
    parser.add_argument('--robots', type=int, help='Filter by robot count')
    parser.add_argument('--run', help='Filter by run (e.g., run021)')
    parser.add_argument('--compare', action='store_true', help='Generate comparison plot')
    parser.add_argument('--sweep', help='Generate scaling sweep (e.g., 600-1000)')
    parser.add_argument('--metric', default='throughput', 
                       choices=['throughput', 'completion_rate', 'latency', 'utilization'],
                       help='Metric for scaling sweep')
    parser.add_argument('--table', action='store_true', help='Print summary table')
    parser.add_argument('--unified', action='store_true', help='Generate unified scaling plot with all metrics')
    parser.add_argument('--output', help='Output path for plots')
    
    args = parser.parse_args()
    
    analyzer = ResultsAnalyzer(args.results_dir)
    
    print(f"Loaded {len(analyzer.experiments)} experiments from {args.results_dir}")
    
    if args.table:
        output_path = Path(args.output) if args.output else None
        df = analyzer.generate_summary_table(robots=args.robots, run=args.run, save_path=output_path)
        print("\n" + "="*100)
        print("SUMMARY TABLE")
        print("="*100)
        print(df.to_string(index=False))
        print("="*100 + "\n")
    
    if args.compare:
        if not args.robots:
            print("Error: --robots required for comparison")
            sys.exit(1)
        
        output_path = Path(args.output) if args.output else None
        analyzer.plot_comparison(args.robots, args.run, output_path)
    
    if args.sweep:
        try:
            start, end = map(int, args.sweep.split('-'))
            
            import re
            available_counts = set()
            for exp in analyzer.experiments:
                match = re.search(r'(\d+)_agents', exp['config_name'])
                if match:
                    count = int(match.group(1))
                    if start <= count <= end:
                        available_counts.add(count)
            
            robot_counts = sorted(list(available_counts))
            
            if not robot_counts:
                print(f"Error: No data found in range {start}-{end}")
                print(f"Available robot counts: {sorted([int(re.search(r'(\d+)_agents', e['config_name']).group(1)) for e in analyzer.experiments if re.search(r'(\d+)_agents', e['config_name'])])}")
                sys.exit(1)
            
            print(f"Using robot counts: {robot_counts}")
            
        except:
            print(f"Error: Invalid sweep format '{args.sweep}'. Use format: 600-1000")
            sys.exit(1)
        
        output_path = Path(args.output) if args.output else None
        analyzer.plot_scaling_sweep(robot_counts, args.metric, args.run, output_path)
    
    if args.unified:
        output_path = Path(args.output) if args.output else None
        analyzer.plot_unified_scaling(args.run, output_path)


if __name__ == '__main__':
    main()

