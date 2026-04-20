"""
Utility functions for cleaning up experiment artifacts.
"""

from pathlib import Path
from typing import Optional
import logging


def cleanup_duplicate_plots(run_dir: Path, logger: Optional[logging.Logger] = None):
    """
    Remove old incremental files, keeping only the most recent timestamp for each experiment.
    Cleans up PNG, CSV, and JSON files.
    
    Args:
        run_dir: Path to the run directory containing mode subdirectories
        logger: Optional logger for status messages
    """
    for mode in ['distributed', 'centralized']:
        mode_dir = run_dir / mode
        if not mode_dir.exists():
            continue
        
        for exp_subdir in mode_dir.iterdir():
            if not exp_subdir.is_dir():
                continue
            
            for pattern in ['*.png', '*.csv', '*.json']:
                files = list(exp_subdir.glob(pattern))
                
                file_groups = {}
                for file_path in files:
                    parts = file_path.stem.split('_')
                    if len(parts) >= 2:
                        timestamp = parts[-1]
                        base_name = '_'.join(parts[:-1])
                        
                        if base_name not in file_groups:
                            file_groups[base_name] = []
                        file_groups[base_name].append((timestamp, file_path))
                
                deleted_count = 0
                for base_name, grouped_files in file_groups.items():
                    if len(grouped_files) > 1:
                        grouped_files.sort(key=lambda x: x[0])
                        
                        for timestamp, file_path in grouped_files[:-1]:
                            try:
                                file_path.unlink()
                                deleted_count += 1
                            except Exception as e:
                                if logger:
                                    logger.warning(f"Could not delete old file {file_path}: {e}")
                
                if deleted_count > 0 and logger:
                    logger.info(f"Cleaned up {deleted_count} old {pattern} files from {exp_subdir.name}/")

