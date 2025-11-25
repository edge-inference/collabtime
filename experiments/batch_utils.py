"""
Batch execution utilities for running multiple experiments
"""
from typing import Dict, List, Optional


def generate_batch_experiment_list(
    batch_mode: str, 
    available_experiments: Dict, 
    scale_range: Optional[List[int]] = None
) -> List[str]:
    """Generate list of experiments for batch mode."""
    if scale_range:
        min_agents, max_agents = scale_range
        scales = list(range(min_agents, max_agents + 1, 100))
    else:
        # Default: 600, 700, 800, 900, 1000
        scales = [600, 700, 800, 900, 1000]
    
    experiments = []
    
    if batch_mode == 'scales':
        # Run all distributed for each scale
        for scale in scales:
            exp_name = f'scalability_{scale}_agents'
            if exp_name in available_experiments:
                experiments.append(exp_name)
    
    elif batch_mode == 'paired':
        # Run distributed then centralized for each scale
        for scale in scales:
            dist_name = f'scalability_{scale}_agents'
            cent_name = f'centralized_{scale}_agents'
            if dist_name in available_experiments:
                experiments.append(dist_name)
            if cent_name in available_experiments:
                experiments.append(cent_name)
    
    elif batch_mode == 'all':
        # Run everything in order
        for scale in scales:
            dist_name = f'scalability_{scale}_agents'
            cent_name = f'centralized_{scale}_agents'
            if dist_name in available_experiments:
                experiments.append(dist_name)
            if cent_name in available_experiments:
                experiments.append(cent_name)
    
    return experiments

