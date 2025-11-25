"""
Core experiment runner logic
"""
import yaml
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from experiments.fileHandler import ResultsManager
from world.model import WarehouseDSMModel
from world.graph import WarehouseGraph


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
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger('ExperimentRunner')
    
    def run_experiments(self, experiment_names: Optional[List[str]] = None, use_lf: bool = True) -> List[ExperimentResult]:
        """Run specified experiments or all if none specified."""
        if experiment_names is None:
            experiment_names = list(self.experiments.keys())
        
        results = []
        for exp_name in experiment_names:
            if exp_name not in self.experiments:
                self.logger.warning(f"Experiment '{exp_name}' not found in config")
                continue
            
            self.logger.info(f"Starting experiment: {exp_name}")
            result = self.run_single_experiment(exp_name, use_lf)
            results.append(result)
            
            if result.success:
                self.logger.info(f"Completed: {exp_name}")
            else:
                self.logger.error(f"Failed: {exp_name} - {result.error_message}")
        
        # Save results grouped by mode
        if results:
            self.file_handler.save_results_by_mode(results, self.config_paths[0] if self.config_paths else Path('config'), self.output_config)
        
        return results
    
    def run_single_experiment(self, config_name: str, use_lf: bool = True) -> ExperimentResult:
        """Run a single experiment and collect metrics."""
        # This is a placeholder - actual implementation will be imported from run.py
        # to avoid circular dependencies
        raise NotImplementedError("Use runner_execution module")

