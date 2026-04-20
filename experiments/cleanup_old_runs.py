#!/usr/bin/env python3
"""
Cleanup old intermediate experiment files from legacy run folders.

Usage:
    python cleanup_old_runs.py --run run013 --dry-run
    python cleanup_old_runs.py --run run013 --execute
    python cleanup_old_runs.py --all --execute
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime
from collections import defaultdict

sys.path.append(str(Path(__file__).parent.parent))


class LegacyRunCleaner:
    """Clean up intermediate files from legacy flat-structure runs."""
    
    def __init__(self, results_dir: str = "results"):
        self.results_dir = Path(results_dir)
        self.files_to_delete = []
        self.files_to_keep = []
    
    def analyze_run(self, run_name: str) -> Dict[str, any]:
        """Analyze a run directory and identify files to clean up."""
        run_dir = self.results_dir / run_name
        
        if not run_dir.exists():
            print(f"Error: Run directory {run_dir} does not exist")
            return None
        
        stats = {
            'run': run_name,
            'files_analyzed': 0,
            'files_to_delete': 0,
            'files_to_keep': 0,
            'space_to_free': 0
        }
        
        for mode in ['distributed', 'centralized']:
            mode_dir = run_dir / mode
            if not mode_dir.exists():
                continue
            
            if self._is_flat_structure(mode_dir):
                print(f"Found flat structure in {mode_dir}")
                self._analyze_flat_mode_dir(mode_dir, stats)
            else:
                print(f"Skipping {mode_dir} (already using subdirectory structure)")
        
        return stats
    
    def _is_flat_structure(self, mode_dir: Path) -> bool:
        """Check if a mode directory uses flat structure (files directly in mode dir)."""
        json_files = list(mode_dir.glob("experiment_details_*.json"))
        return len(json_files) > 0
    
    def _analyze_flat_mode_dir(self, mode_dir: Path, stats: Dict):
        """Analyze a flat structure mode directory."""
        file_groups = defaultdict(list)
        
        for pattern in ['experiment_details_*.json', 'experiment_summary_*.csv', 
                       'dashboard_metrics_*.csv', 'dashboard_report_*.png', 
                       'system_perf_*.png']:
            for file_path in mode_dir.glob(pattern):
                stats['files_analyzed'] += 1
                
                timestamp = self._extract_timestamp(file_path.name)
                if timestamp:
                    group_key = self._get_group_key(file_path.name, pattern)
                    file_groups[group_key].append((timestamp, file_path))
        
        for group_key, files in file_groups.items():
            if len(files) > 1:
                files.sort(key=lambda x: x[0], reverse=True)
                
                latest_file = files[0][1]
                self.files_to_keep.append(latest_file)
                stats['files_to_keep'] += 1
                
                for timestamp, old_file in files[1:]:
                    self.files_to_delete.append(old_file)
                    stats['files_to_delete'] += 1
                    stats['space_to_free'] += old_file.stat().st_size
            elif len(files) == 1:
                self.files_to_keep.append(files[0][1])
                stats['files_to_keep'] += 1
    
    def _extract_timestamp(self, filename: str) -> str:
        """Extract timestamp from filename (format: YYYYMMDD_HHMMSS)."""
        parts = filename.split('_')
        for i, part in enumerate(parts):
            if len(part) == 8 and part.isdigit():
                if i + 1 < len(parts) and len(parts[i + 1]) >= 6:
                    time_part = parts[i + 1].split('.')[0]
                    if time_part.isdigit():
                        return f"{part}_{time_part}"
        return None
    
    def _get_group_key(self, filename: str, pattern: str) -> str:
        """Get grouping key for a file (everything except timestamp)."""
        timestamp = self._extract_timestamp(filename)
        if timestamp:
            return filename.replace(f"_{timestamp}", "")
        return filename
    
    def execute_cleanup(self, dry_run: bool = True):
        """Execute the cleanup (or show what would be deleted)."""
        if not self.files_to_delete:
            print("No files to delete.")
            return
        
        total_size = sum(f.stat().st_size for f in self.files_to_delete)
        total_size_mb = total_size / (1024 * 1024)
        
        print(f"\n{'DRY RUN - ' if dry_run else ''}Cleanup Summary:")
        print(f"  Files to delete: {len(self.files_to_delete)}")
        print(f"  Files to keep: {len(self.files_to_keep)}")
        print(f"  Space to free: {total_size_mb:.2f} MB")
        
        if dry_run:
            print("\nFiles that would be deleted:")
            for file_path in sorted(self.files_to_delete)[:20]:
                print(f"  - {file_path.relative_to(self.results_dir)}")
            if len(self.files_to_delete) > 20:
                print(f"  ... and {len(self.files_to_delete) - 20} more files")
        else:
            print("\nDeleting files...")
            deleted = 0
            for file_path in self.files_to_delete:
                try:
                    file_path.unlink()
                    deleted += 1
                except Exception as e:
                    print(f"  Error deleting {file_path}: {e}")
            
            print(f"Successfully deleted {deleted}/{len(self.files_to_delete)} files")
            print(f"Freed {total_size_mb:.2f} MB of space")


def main():
    parser = argparse.ArgumentParser(description='Clean up intermediate files from legacy experiment runs')
    parser.add_argument('--results-dir', default='results', help='Results directory')
    parser.add_argument('--run', help='Specific run to clean (e.g., run013)')
    parser.add_argument('--all', action='store_true', help='Clean all runs with flat structure')
    parser.add_argument('--dry-run', action='store_true', default=True, 
                       help='Show what would be deleted without actually deleting')
    parser.add_argument('--execute', action='store_true', 
                       help='Actually delete files (overrides --dry-run)')
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    cleaner = LegacyRunCleaner(args.results_dir)
    
    runs_to_clean = []
    if args.run:
        runs_to_clean = [args.run]
    elif args.all:
        results_path = Path(args.results_dir)
        for run_dir in sorted(results_path.glob("run*")):
            if run_dir.is_dir():
                for mode in ['distributed', 'centralized']:
                    mode_dir = run_dir / mode
                    if mode_dir.exists() and cleaner._is_flat_structure(mode_dir):
                        runs_to_clean.append(run_dir.name)
                        break
    else:
        print("Error: Must specify either --run or --all")
        sys.exit(1)
    
    if not runs_to_clean:
        print("No runs found to clean")
        sys.exit(0)
    
    print(f"Analyzing {len(runs_to_clean)} run(s): {', '.join(runs_to_clean)}")
    print("="*70)
    
    all_stats = []
    for run_name in runs_to_clean:
        print(f"\nAnalyzing {run_name}...")
        stats = cleaner.analyze_run(run_name)
        if stats:
            all_stats.append(stats)
    
    print("\n" + "="*70)
    print("OVERALL SUMMARY")
    print("="*70)
    total_to_delete = sum(s['files_to_delete'] for s in all_stats)
    total_to_keep = sum(s['files_to_keep'] for s in all_stats)
    total_space = sum(s['space_to_free'] for s in all_stats)
    
    print(f"Total files to delete: {total_to_delete}")
    print(f"Total files to keep: {total_to_keep}")
    print(f"Total space to free: {total_space / (1024*1024):.2f} MB")
    
    if total_to_delete > 0:
        print("\n" + "="*70)
        cleaner.execute_cleanup(dry_run=dry_run)
        
        if dry_run:
            print("\n" + "="*70)
            print("This was a DRY RUN. No files were deleted.")
            print("To actually delete files, run with --execute")
    else:
        print("\nNo cleanup needed!")


if __name__ == '__main__':
    main()

