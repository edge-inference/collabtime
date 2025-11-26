#!/usr/bin/env python3
"""
Warehouse DSM Experiment Runner
Automated execution and analysis of warehouse distributed shared memory experiments.
"""

import yaml
import json
import argparse
import logging
import time
import os
import sys
import subprocess
import signal
import atexit
import multiprocessing as mp
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent))

from config import (
    STEP_DURATION_S,
    calculate_task_latency,
    calculate_agent_capacity,
    TASK_WORK_DURATION_S,
    GOSSIP_PERIOD_MS
)
from experiments.fileHandler import ResultsManager

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from world.model import WarehouseDSMModel
from world.graph import WarehouseGraph
from lf.bridge import LFTickClient

# Import modular components
from experiments.metrics import collect_step_metrics, collect_final_metrics
from experiments.plotting import generate_dashboard_reports
from experiments.batch_utils import generate_batch_experiment_list


@dataclass
class ExperimentResult:
    """Container for experiment results and metadata."""
    config_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    metrics: Dict[str, Any]
    logs: List[str]
    success: bool
    error_message: Optional[str] = None
    mode: Optional[str] = None
    seed: Optional[int] = None


class ExperimentRunner:
    """Orchestrates warehouse DSM experiments with data collection and analysis."""
    
    def __init__(self, config_path: str, output_dir: str = "results", duration_override: Optional[int] = None):
        """Initialize experiment runner with configuration."""
        self.config_paths = []
        if isinstance(config_path, list):
            self.config_paths = [Path(p) for p in config_path]
        else:
            self.config_paths = [Path(config_path)]
        
        self.file_handler = ResultsManager(output_dir)
        self.duration_override = duration_override
        
        # Load and merge experiment configurations from all files
        self.config = self._load_configs()
        self.experiments = self.config['experiments']
        self.metrics_config = self.config['metrics']
        self.output_config = self.config['output']
        
        # Setup logging
        self.setup_logging()
        self.log_interval_steps = 100
    
    def _load_configs(self) -> Dict[str, Any]:
        """Load and merge configurations from multiple files."""
        merged_config = {
            'experiments': {},
            'metrics': {},
            'output': {}
        }
        
        for config_path in self.config_paths:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Merge experiments
            if 'experiments' in config:
                merged_config['experiments'].update(config['experiments'])
            
            # Use first config's metrics/output, or merge if needed
            if 'metrics' in config and not merged_config['metrics']:
                merged_config['metrics'] = config['metrics']
            if 'output' in config and not merged_config['output']:
                merged_config['output'] = config['output']
        
        return merged_config
        
    def setup_logging(self):
        """Configure logging for experiment tracking."""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('ExperimentRunner')
        
    def create_warehouse_graph(self, warehouse_config: Dict) -> WarehouseGraph:
        """Create warehouse graph from configuration."""
        size = warehouse_config['size']
        graph = WarehouseGraph(width=size[0], height=size[1])
        
        # Add storage regions
        for region in warehouse_config.get('storage_regions', []):
            center = region['center']
            radius = region['radius']
            for x in range(max(0, center[0] - radius), min(size[0], center[0] + radius + 1)):
                for y in range(max(0, center[1] - radius), min(size[1], center[1] + radius + 1)):
                    if (x - center[0])**2 + (y - center[1])**2 <= radius**2:
                        graph.add_storage_location((x, y))
        
        # Add sortation regions
        for region in warehouse_config.get('sortation_regions', []):
            center = region['center']
            radius = region['radius']
            for x in range(max(0, center[0] - radius), min(size[0], center[0] + radius + 1)):
                for y in range(max(0, center[1] - radius), min(size[1], center[1] + radius + 1)):
                    if (x - center[0])**2 + (y - center[1])**2 <= radius**2:
                        graph.add_sortation_location((x, y))
        
        return graph
        
    def generate_agent_positions(self, agents_config: Dict, warehouse_graph: WarehouseGraph, seed: Optional[int] = None) -> List[tuple]:
        """Generate initial agent positions."""
        if isinstance(agents_config['initial_positions'], str) and agents_config['initial_positions'] == 'random':
            valid_nodes = [n for n in warehouse_graph.graph.nodes()
                          if warehouse_graph.node_types.get(n) in ('staging', 'aisle', 'buffer')
                          and warehouse_graph.capacities.get(n, 0) > 0
                          and len(list(warehouse_graph.graph.neighbors(n))) > 0]
            
            if not valid_nodes:
                raise ValueError("No valid starting positions found in warehouse graph!")
            
            positions = []
            if seed is not None:
                np.random.seed(seed)
            
            for _ in range(agents_config['count']):
                pos = valid_nodes[np.random.randint(len(valid_nodes))]
                positions.append(pos)
            return positions
        else:
            return [tuple(pos) for pos in agents_config['initial_positions']]
    
    def run_single_experiment(self, config_name: str, config: Dict, use_lf: bool = False, seed_override: Optional[int] = None) -> ExperimentResult:
        """Run a single experiment configuration."""
        sim_mode = config.get('simulation', {}).get('mode', 'p2p')
        
        mode_dir = self.file_handler.get_mode_directory(
            'distributed' if sim_mode == 'p2p' else 'centralized'
        )
        
        mode_log_path = mode_dir / 'experiments.log'
        mode_file_handler = logging.FileHandler(mode_log_path)
        mode_file_handler.setLevel(logging.INFO)
        mode_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        
        self.logger.addHandler(mode_file_handler)
        
        self.logger.info("=" * 70)
        self.logger.info(f"EXPERIMENT: {config_name}")
        self.logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 70)
        
        warehouse_size = config['warehouse']['size']
        num_agents = config['agents']['count']
        task_rate = config['tasks']['arrival_rate']
        duration = config['simulation']['duration']
        step_interval = config['simulation']['step_interval']
        seed = config.get('simulation', {}).get('seed', None)
        
        if seed_override is not None:
            seed = seed_override
            config['simulation']['seed'] = seed
            self.logger.info(f"Seed overridden to: {seed}")
        
        if self.duration_override is not None:
            duration = self.duration_override
            config['simulation']['duration'] = duration
            self.logger.info(f"Duration overridden to {duration}s via command-line")
        
        task_latency = calculate_task_latency(warehouse_size[0], warehouse_size[1])
        agent_capacity = calculate_agent_capacity(warehouse_size[0], warehouse_size[1])
        system_capacity = num_agents * agent_capacity
        utilization = task_rate / system_capacity if system_capacity > 0 else 0
        
        gossip_interval = config.get('coordination', {}).get('gossip_interval', 3)
        aoi_threshold = config.get('coordination', {}).get('aoi_threshold', 1000)
        
        self.logger.info(f"Coordination Architecture: P2P (Peer-to-Peer)")
        self.logger.info(f"  Control Plane: Coordinator (strong consistency)")
        self.logger.info(f"  Data Plane: Local caches + epidemic gossip")
        self.logger.info(f"  Gossip Interval: {gossip_interval} steps")
        self.logger.info(f"  AoI Threshold: {aoi_threshold}ms")
        self.logger.info(f"Warehouse Dimensions: {warehouse_size[0]} × {warehouse_size[1]} = {warehouse_size[0] * warehouse_size[1]} cells")
        self.logger.info(f"Agents: {num_agents}")
        self.logger.info(f"Simulation Duration: {duration}s ({int(duration * 1000 / step_interval)} steps)")
        self.logger.info(f"Step Duration: {STEP_DURATION_S:.3f}s ({int(STEP_DURATION_S * 1000)}ms)")
        self.logger.info(f"Timing Mode: {'LF-coordinated' if use_lf else 'Fast-as-possible'}")
        self.logger.info(f"Random Seed: {seed if seed is not None else 'None (unseeded)'}")
        self.logger.info("")
        self.logger.info("Capacity Analysis (for this warehouse size):")
        self.logger.info(f"  Avg Task Distance: {(warehouse_size[0] + warehouse_size[1]) / 3:.1f} cells")
        self.logger.info(f"  Typical Task Latency: {task_latency:.1f}s")
        self.logger.info(f"  Agent Capacity: {agent_capacity:.4f} tasks/sec")
        self.logger.info(f"  System Capacity ({num_agents} agents): {system_capacity:.4f} tasks/sec")
        self.logger.info(f"  Task Arrival Rate: {task_rate:.4f} tasks/sec")
        self.logger.info(f"  Expected Utilization: {utilization:.1%}")
        self.logger.info("=" * 70)
        self.logger.info("")
        
        start_time = datetime.now()
        
        try:
            warehouse_graph = self.create_warehouse_graph(config['warehouse'])
            agent_positions = self.generate_agent_positions(config['agents'], warehouse_graph, seed)
            
            duration = config['simulation']['duration']
            step_interval = config['simulation']['step_interval']
            step_dt = STEP_DURATION_S
            steps = int(duration * 1000 / step_interval)
            seed = config.get('simulation', {}).get('seed', None)
            
            model = WarehouseDSMModel(
                n_agents=config['agents']['count'],
                warehouse_graph=warehouse_graph,
                agent_positions=agent_positions,
                task_arrival_rate=config['tasks']['arrival_rate'],
                task_types=config['tasks']['types'],
                task_priorities=config['tasks']['priorities'],
                step_duration_s=step_dt,
                aoi_threshold_ms=aoi_threshold,
                mode=sim_mode,
                use_spatial_hash=config['simulation'].get('use_spatial_hash', False),
                parallel_gossip=config['simulation'].get('parallel_gossip', False),
                gossip_workers=config['simulation'].get('gossip_workers', 4),
                parallel_agents=config['simulation'].get('parallel_agents', True),
                agent_workers=config['simulation'].get('agent_workers', None),
                use_cython=config['simulation'].get('use_cython', True),
                seed=seed,
                logger=self.logger
            )
            
            mode_label = "CENTRALIZED (bottleneck)" if sim_mode == 'centralized' else "P2P DISTRIBUTED"
            self.logger.info(f"Initialized {mode_label} model with {config['agents']['count']} agents")
            
            self.logger.info(f"Running {steps} steps over {duration}s")
            
            metrics_data = []
            
            if use_lf:
                client = LFTickClient()
                client.connect()
                tick_iter = client.ticks()
                self.logger.info("Connected to LF tick server on 127.0.0.1:9001")
                
                current_step = 0
                for _ in tick_iter:
                    if current_step >= steps:
                        break
                    model.step()
                    if current_step % 10 == 0:
                        step_metrics = collect_step_metrics(model, current_step)
                        metrics_data.append(step_metrics)
                        
                        if self.log_interval_steps > 0 and current_step % self.log_interval_steps == 0:
                            self.logger.info(f"Step {current_step}/{steps} ({100*current_step/steps:.1f}%) - "
                                             f"Tasks: {model.task_counter} created, "
                                             f"{len(model.completed_tasks)} completed, "
                                             f"{len(model.active_tasks)} active")
                        
                        if 'failure_schedule' in config['agents']:
                            self.handle_agent_failures(model, config['agents']['failure_schedule'], current_step, step_interval)
                    current_step += 1
            else:
                for step in range(steps):
                    model.step()
                    
                    if step % 10 == 0:
                        step_metrics = collect_step_metrics(model, step)
                        metrics_data.append(step_metrics)
                        
                        # Progress (step-based only)
                        if self.log_interval_steps > 0 and step % self.log_interval_steps == 0:
                            self.logger.info(f"Step {step}/{steps} ({100*step/steps:.1f}%) - "
                                             f"Tasks: {model.task_counter} created, "
                                             f"{len(model.completed_tasks)} completed, "
                                             f"{len(model.active_tasks)} active")
                        
                        if 'failure_schedule' in config['agents']:
                            self.handle_agent_failures(model, config['agents']['failure_schedule'], step, step_interval)
            
            # Collect final metrics
            final_metrics = collect_final_metrics(model, metrics_data, sim_duration_s=duration, step_interval_ms=step_interval)
            
            end_time = datetime.now()
            duration_seconds = (end_time - start_time).total_seconds()
            
            result = ExperimentResult(
                config_name=config_name,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                metrics=final_metrics,
                logs=[],
                success=True,
                mode=sim_mode,
                seed=seed
            )
            
            self.logger.info(f"Completed experiment: {config_name} in {duration_seconds:.2f}s")
            return result
            
        except Exception as e:
            import traceback
            end_time = datetime.now()
            duration_seconds = (end_time - start_time).total_seconds()
            
            full_trace = traceback.format_exc()
            result = ExperimentResult(
                config_name=config_name,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                metrics={},
                logs=[],
                success=False,
                error_message=str(e),
                mode=sim_mode,
                seed=seed
            )
            
            self.logger.error(f"Failed experiment: {config_name} - {e}\n{full_trace}")
            return result
        finally:
            if 'model' in locals():
                if hasattr(model, 'gossip_engine') and model.gossip_engine:
                    model.gossip_engine.stop()
                if hasattr(model, 'cleanup_shm'):
                    model.cleanup_shm()
            self.logger.removeHandler(mode_file_handler)
            mode_file_handler.close()
    
    def handle_agent_failures(self, model: WarehouseDSMModel, failure_schedule: List[Dict], 
                            current_step: int, step_interval: int):
        """Handle scheduled agent failures during simulation."""
        current_time = current_step * step_interval / 1000  # Convert to seconds
        
        for failure in failure_schedule:
            agent_id = failure['agent_id']
            fail_time = failure['time']
            duration = failure['duration']
            
            # Check if agent should fail now
            if fail_time <= current_time < fail_time + duration:
                if agent_id < len(model.schedule.agents):
                    agent = model.schedule.agents[agent_id]
                    agent.failed = True
                    self.logger.info(f"Agent {agent_id} failed at time {current_time}s")
            
            # Check if agent should recover
            elif current_time >= fail_time + duration:
                if agent_id < len(model.schedule.agents):
                    agent = model.schedule.agents[agent_id]
                    if hasattr(agent, 'failed') and agent.failed:
                        agent.failed = False
                        self.logger.info(f"Agent {agent_id} recovered at time {current_time}s")
    
    def save_results(self, results: List[ExperimentResult]):
        """Save experiment results to various formats, grouped by mode into subfolders."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Group results by mode
        by_mode: Dict[str, List[ExperimentResult]] = {'distributed': [], 'centralized': [], 'unknown': []}
        for r in results:
            mode = (r.mode or 'unknown').lower()
            if mode not in by_mode:
                by_mode[mode] = []
            by_mode[mode].append(r)

        for mode, group in by_mode.items():
            if not group:
                continue
            mode_name = 'distributed' if mode in ['distributed', 'p2p'] else 'centralized' if mode == 'centralized' else 'misc'
            out_dir = self.file_handler.get_mode_directory(mode_name)

            # Save summary CSV
            summary_data = []
            for result in group:
                summary_row = {
                    'config_name': result.config_name,
                    'mode': result.mode,
                    'success': result.success,
                    'duration_seconds': result.duration_seconds,
                    'error_message': result.error_message or ''
                }
                if result.success:
                    summary_row.update({f"perf_{k}": v for k, v in result.metrics.get('performance', {}).items()})
                    summary_row.update({f"coord_{k}": v for k, v in result.metrics.get('coordination', {}).items()})
                summary_data.append(summary_row)
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_csv(out_dir / f'experiment_summary_{timestamp}.csv', index=False)

            # Save detailed JSON
            detailed_results = {
                'timestamp': timestamp,
                'config_paths': [str(p) for p in self.config_paths],
                'mode': mode,
                'results': [asdict(result) for result in group]
            }
            with open(out_dir / f'experiment_details_{timestamp}.json', 'w') as f:
                json.dump(detailed_results, f, indent=2, default=str)

            # Plots
            if 'plots' in self.output_config:
                self._generate_mode_plots(group, timestamp, out_dir)
    
    def _generate_mode_plots(self, results: List[ExperimentResult], timestamp: str, out_dir: Path):
        """Generate plots for a specific mode in the given output directory."""
        plots = self.output_config.get('plots')
        if isinstance(plots, list) and 'dashboard_style' in plots:
            generate_dashboard_reports(results, timestamp, out_dir)
            
    def _extract_config_details(self, experiment_names: List[str]) -> Dict:
        """Extract configuration details for metadata"""
        config_details = {}
        
        for exp_name in experiment_names:
            if exp_name not in self.experiments:
                continue
            
            config = self.experiments[exp_name]
            
            warehouse_size = config.get('warehouse', {}).get('size', [0, 0])
            simulation_config = config.get('simulation', {})
            agents_config = config.get('agents', {})
            tasks_config = config.get('tasks', {})
            dsm_config = config.get('dsm', {})
            
            aoi_threshold = config.get('aoi_threshold', dsm_config.get('aoi_threshold', 1000))
            
            config_details[exp_name] = {
                'warehouse': {
                    'dimensions': warehouse_size,
                    'total_cells': warehouse_size[0] * warehouse_size[1] if len(warehouse_size) == 2 else 0,
                    'storage_regions': len(config.get('warehouse', {}).get('storage_regions', [])),
                    'sortation_regions': len(config.get('warehouse', {}).get('sortation_regions', []))
                },
                'agents': {
                    'count': agents_config.get('count', 0),
                    'initial_positions': agents_config.get('initial_positions', 'unknown')
                },
                'simulation': {
                    'mode': simulation_config.get('mode', 'distributed'),
                    'duration_s': self.duration_override if self.duration_override is not None else simulation_config.get('duration', 0),
                    'step_interval_ms': simulation_config.get('step_interval', 50),
                    'total_steps': int((self.duration_override if self.duration_override is not None else simulation_config.get('duration', 0)) * 1000 / simulation_config.get('step_interval', 50)),
                    'seed': simulation_config.get('seed')
                },
                'tasks': {
                    'arrival_rate': tasks_config.get('arrival_rate', 0),
                    'types': tasks_config.get('types', []),
                    'priorities': tasks_config.get('priorities', [])
                },
                'coordination': {
                    'gossip_interval': coord_config.get('gossip_interval', 3),
                    'aoi_threshold_ms': coord_config.get('aoi_threshold', 1000),
                    'lease_ttl_ms': coord_config.get('lease_ttl', 30000)
                } if (coord_config := config.get('coordination', {})) else None
            }
        
        return config_details
    
    def run_experiments(self, experiment_names: Optional[List[str]] = None, use_lf: bool = False, seeds: Optional[List[int]] = None) -> List[ExperimentResult]:
        """Run specified experiments or all if none specified."""
        if experiment_names is None:
            experiment_names = list(self.experiments.keys())
        
        config_details = self._extract_config_details(experiment_names)
        
        run_dir = self.file_handler.create_run_directory(
            description=f"Baseline comparison: {', '.join(experiment_names)}",
            config_names=experiment_names,
            config_details=config_details
        )
        self.logger.info(f"Created run directory: {run_dir}")
        
        results = []
        
        for exp_name in experiment_names:
            if exp_name not in self.experiments:
                self.logger.error(f"Unknown experiment: {exp_name}")
                continue
                
            config = self.experiments[exp_name]
            
            run_seeds = seeds if seeds else [config.get('simulation', {}).get('seed', 42)]
            if not run_seeds:
                run_seeds = [42]
                
            for seed in run_seeds:
                if len(run_seeds) > 1:
                    self.logger.info(f"Running {exp_name} with seed {seed}")
                
                result = self.run_single_experiment(exp_name, config, use_lf=use_lf, seed_override=seed)
                results.append(result)
        
        self.save_results(results)
        self.file_handler.mark_run_complete()
        
        return results


def start_lf_coordinator():
    """Start LF coordinator as subprocess."""
    lf_dir = Path(__file__).parent.parent / 'lf'
    coordinator_script = lf_dir / 'src-gen' / 'coordinator' / 'coordinator.py'
    
    if not coordinator_script.exists():
        print(f"Error: LF coordinator not compiled. Please run:")
        print(f"  cd {lf_dir}")
        print(f"  lfc coordinator.lf")
        return None
    
    print("Starting LF coordinator...")
    # Redirect output to log file to prevent pipe buffer overflow on long runs
    log_file = lf_dir / 'coordinator.log'
    log_fd = open(log_file, 'w')
    proc = subprocess.Popen(
        [sys.executable, str(coordinator_script)],
        stdout=log_fd,
        stderr=subprocess.STDOUT,  # Merge stderr into stdout
        cwd=str(lf_dir)
    )
    # Store file descriptor for cleanup later
    proc._log_fd = log_fd
    
    # Wait a bit for server to start
    time.sleep(2)
    
    if proc.poll() is not None:
        print("Error: LF coordinator failed to start")
        return None
    
    print(f"LF coordinator started (PID: {proc.pid})")
    
    # Register cleanup on exit
    def cleanup():
        print("Stopping LF coordinator...")
        proc.terminate()
        proc.wait(timeout=5)
        if hasattr(proc, '_log_fd'):
            proc._log_fd.close()
    
    atexit.register(cleanup)
    
    return proc




def main():
    """Main entry point for experiment runner."""
    parser = argparse.ArgumentParser(description='Run warehouse DSM experiments')
    parser.add_argument('--config', '-c', nargs='+', default=['small.yaml'],
                       help='Config file(s): small.yaml, medium.yaml, or large.yaml. Multiple files will be merged.')
    parser.add_argument('--output', '-o', default='results',
                       help='Output directory for results')
    parser.add_argument('--experiments', '-e', nargs='+',
                       help='Specific experiments to run (default: all)')
    parser.add_argument('--parallel', '-p', action='store_true',
                       help='Run experiments in parallel')
    parser.add_argument('--batch', '-b', choices=['scales', 'paired', 'all'],
                       help='Batch mode: scales=600,700,...1000, paired=dist+cent for each scale, all=everything')
    parser.add_argument('--scale-range', nargs=2, type=int, metavar=('MIN', 'MAX'),
                       help='Agent count range for batch mode (e.g., 600 1000)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    lf_group = parser.add_mutually_exclusive_group()
    lf_group.add_argument('--lf', dest='lf', action='store_true', default=True,
                        help='Drive simulation steps from Lingua Franca tick events (default, required for determinism)')
    lf_group.add_argument('--no-lf', dest='lf', action='store_false',
                        help='Use internal clock - WARNING: NOT DETERMINISTIC, for testing only')
    
    parser.add_argument('--log-interval', type=int, default=None,
                       help='Progress log interval in steps (default: 100). Use 0 to disable.')
    parser.add_argument('--duration', '-d', type=int, default=None,
                       help='Override simulation duration in seconds')
    
    parser.add_argument('--seeds', nargs='+', type=int, help='Specific seeds to run (e.g. 42 100 999)')
    parser.add_argument('--repeat', type=int, default=1, help='Number of times to repeat each experiment (auto-generating seeds starting from config seed)')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Start LF coordinator if requested
    lf_proc = None
    if args.lf:
        lf_proc = start_lf_coordinator()
        if lf_proc is None:
            print("\nERROR: LF coordinator required but unavailable.")
            print("Experiments require Lingua Franca for deterministic, reproducible results.")
            print("Please compile the LF coordinator:")
            print(f"  cd {Path(__file__).parent.parent / 'lf'}")
            print("  lfc coordinator.lf")
            print("\nOr use --no-lf for non-deterministic testing (NOT recommended for experiments).")
            sys.exit(1)
    
    # Process config paths - allow simple names like "large.yaml" or full paths
    config_paths = []
    experiments_dir = Path(__file__).parent
    configs_dir = experiments_dir / 'configs'
    
    for cfg in args.config:
        cfg_path = Path(cfg)
        if not cfg_path.exists():
            alt_path = configs_dir / cfg
            if alt_path.exists():
                config_paths.append(str(alt_path))
            elif (experiments_dir / cfg).exists():
                config_paths.append(str(experiments_dir / cfg))
            else:
                config_paths.append(cfg)
        else:
            config_paths.append(cfg)
    
    # Initialize runner
    runner = ExperimentRunner(config_paths, args.output, duration_override=args.duration)
    if args.log_interval is not None:
        runner.log_interval_steps = max(0, int(args.log_interval))
    
    # Handle batch mode
    experiments_to_run = args.experiments
    if args.batch:
        experiments_to_run = generate_batch_experiment_list(
            args.batch, 
            runner.experiments,
            args.scale_range
        )
        print(f"\nBatch mode '{args.batch}': Running {len(experiments_to_run)} experiments")
        for exp in experiments_to_run:
            print(f"  - {exp}")
        print()
    
    seeds_to_run = None
    if args.seeds:
        seeds_to_run = args.seeds
    elif args.repeat > 1:
        well_separated_seeds = [42, 1337, 9999, 54321, 123456, 777777, 314159, 271828, 161803, 866025]
        seeds_to_run = well_separated_seeds[:args.repeat]

    # Run experiments
    start_time = time.time()
    results = runner.run_experiments(experiments_to_run, use_lf=args.lf, seeds=seeds_to_run)
    total_time = time.time() - start_time
    
    # Print summary
    successful = len([r for r in results if r.success])
    failed = len([r for r in results if not r.success])
    
    print(f"\nExperiment Summary:")
    print(f"Total experiments: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total time: {total_time:.2f}s")
    
    if failed > 0:
        print(f"\nFailed experiments:")
        for result in results:
            if not result.success:
                print(f"  {result.config_name}: {result.error_message}")


if __name__ == '__main__':
    main()