"""
Utility functions for cleaning up experiment artifacts.
"""

from pathlib import Path
from typing import Optional
import logging


def cleanup_duplicate_plots(run_dir: Path, logger: Optional[logging.Logger] = None):
    """
    Remove old incremental plot files, keeping only the most recent timestamp for each experiment.
    
    Args:
        run_dir: Path to the run directory containing mode subdirectories
        logger: Optional logger for status messages
    """
    for mode in ['distributed', 'centralized']:
        mode_dir = run_dir / mode
        if not mode_dir.exists():
            continue
        
        plot_files = list(mode_dir.glob('*.png'))
        
        plot_groups = {}
        for plot_file in plot_files:
            parts = plot_file.stem.split('_')
            if len(parts) >= 2:
                timestamp = parts[-1]
                base_name = '_'.join(parts[:-1])
                
                if base_name not in plot_groups:
                    plot_groups[base_name] = []
                plot_groups[base_name].append((timestamp, plot_file))
        
        deleted_count = 0
        for base_name, files in plot_groups.items():
            if len(files) > 1:
                files.sort(key=lambda x: x[0])
                
                for timestamp, plot_file in files[:-1]:
                    try:
                        plot_file.unlink()
                        deleted_count += 1
                    except Exception as e:
                        if logger:
                            logger.warning(f"Could not delete old plot {plot_file}: {e}")
        
        if deleted_count > 0 and logger:
            logger.info(f"Cleaned up {deleted_count} old incremental plots from {mode}/")

