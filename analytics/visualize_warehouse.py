#!/usr/bin/env python3
"""
Warehouse Layout Visualizer
Generates visual maps of warehouse configurations matching the dashboard style.
"""

import yaml
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from world.graph import WarehouseGraph


def load_configs():
    """Load all experiment configs and extract warehouse parameters."""
    config_dir = Path(__file__).parent.parent / "experiments" / "configs"
    warehouses = {}
    
    for config_file in sorted(config_dir.glob("*.yaml")):
        with open(config_file) as f:
            data = yaml.safe_load(f)
        
        if 'experiments' not in data:
            continue
            
        for exp_name, exp_config in data['experiments'].items():
            if 'dist_' not in exp_name and 'scalability_' not in exp_name:
                continue
            
            agents = exp_config['agents']['count']
            if agents in warehouses:
                continue
                
            wh = exp_config['warehouse']
            warehouses[agents] = {
                'size': wh['size'],
                'config_file': config_file.name
            }
    
    return dict(sorted(warehouses.items()))


def draw_warehouse_grid(ax, agents, config):
    """Draw warehouse using proper grid cells like the dashboard."""
    width, height = config['size']
    
    warehouse = WarehouseGraph(width=width, height=height)
    
    storage_nodes = warehouse.regions.get('storage', set())
    sortation_nodes = warehouse.regions.get('sortation', set())
    
    cell_colors = {
        'staging': '#FFD700',
        'aisle': '#E8E8E8',
        'shelf_storage': '#4A90D9',
        'shelf_sortation': '#FF7F50',
        'pick_location': '#2ECC71',
        'pack_station': '#9B59B6',
    }
    
    from matplotlib.patches import Rectangle
    from matplotlib.collections import PatchCollection
    
    patches_by_type = {k: [] for k in cell_colors}
    
    for node_id in range(width * height):
        x = node_id % width
        y = node_id // width
        node_type = warehouse.node_types.get(node_id, 'aisle')
        
        rect = Rectangle((x - 0.5, y - 0.5), 1, 1)
        
        if node_type == 'staging':
            patches_by_type['staging'].append(rect)
        elif node_type in ['aisle', 'transit']:
            patches_by_type['aisle'].append(rect)
        elif node_type == 'pick_location':
            patches_by_type['pick_location'].append(rect)
        elif node_type == 'pack_station':
            patches_by_type['pack_station'].append(rect)
        elif node_type == 'shelf':
            if node_id in storage_nodes:
                patches_by_type['shelf_storage'].append(rect)
            elif node_id in sortation_nodes:
                patches_by_type['shelf_sortation'].append(rect)
    
    draw_order = ['aisle', 'staging', 'shelf_storage', 'shelf_sortation', 'pick_location', 'pack_station']
    labels = {
        'staging': 'Staging',
        'aisle': 'Aisle',
        'shelf_storage': 'Storage Shelf',
        'shelf_sortation': 'Sortation Shelf',
        'pick_location': 'Pick Location',
        'pack_station': 'Pack Station',
    }
    
    for ptype in draw_order:
        if patches_by_type[ptype]:
            pc = PatchCollection(patches_by_type[ptype], facecolor=cell_colors[ptype], 
                                edgecolor='white', linewidth=0.3, alpha=0.85)
            ax.add_collection(pc)
            ax.plot([], [], 's', color=cell_colors[ptype], label=labels[ptype], markersize=8)
    
    ax.axvline(x=width/2 - 0.5, color='black', linestyle='--', linewidth=2, alpha=0.7)
    ax.text(width/4, height + 1.5, 'STORAGE', ha='center', fontsize=10, fontweight='bold', color='#4A90D9')
    ax.text(3*width/4, height + 1.5, 'SORTATION', ha='center', fontsize=10, fontweight='bold', color='#FF7F50')
    
    ax.set_xlim(-0.5, width - 0.5)
    ax.set_ylim(-0.5, height - 0.5)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
    
    cells = width * height
    density = agents / cells * 100
    
    ax.set_title(f'{agents} Agents: {width}x{height} = {cells:,} cells ({density:.1f}% density)',
                 fontsize=11, fontweight='bold')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')


def generate_all_layouts(output_dir: Path = None, output_format: str = "png"):
    """Generate layout visualizations for all warehouse configurations."""
    warehouses = load_configs()
    
    if not warehouses:
        print("No warehouse configurations found!")
        return
    
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "results" / "warehouse_layouts"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    n_warehouses = len(warehouses)
    cols = 3
    rows = (n_warehouses + cols - 1) // cols
    
    fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 5 * rows))
    axes = axes.flatten() if n_warehouses > 1 else [axes]
    
    for idx, (agents, config) in enumerate(warehouses.items()):
        print(f"Drawing {agents} agents warehouse...")
        draw_warehouse_grid(axes[idx], agents, config)
    
    for idx in range(n_warehouses, len(axes)):
        axes[idx].axis('off')
    
    fig.suptitle('Warehouse Layouts by Agent Count', fontsize=16, fontweight='bold', y=1.01)
    
    legend_elements = [
        mpatches.Patch(facecolor='gold', alpha=0.6, label='Staging'),
        mpatches.Patch(facecolor='lightgray', alpha=0.4, label='Aisle'),
        mpatches.Patch(facecolor='dodgerblue', alpha=0.7, label='Storage Shelf'),
        mpatches.Patch(facecolor='coral', alpha=0.7, label='Sortation Shelf'),
    ]
    fig.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.99, 0.99), fontsize=10)
    
    plt.tight_layout()
    
    output_path = output_dir / f"warehouse_layouts_all.{output_format}"
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Saved combined layout to: {output_path}")
    plt.close()
    
    for agents, config in warehouses.items():
        width, height = config['size']
        
        scale = max(1, min(width, height) / 40)
        fig, ax = plt.subplots(figsize=(8 * scale, 6 * scale))
        
        draw_warehouse_grid(ax, agents, config)
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=9)
        
        cells = width * height
        storage_pct = 50
        sortation_pct = 50
        
        info_text = (
            f"Warehouse: {width} x {height}\n"
            f"Total: {cells:,} cells\n"
            f"Cells/Agent: {cells/agents:.1f}\n"
            f"Density: {agents/cells*100:.2f}%\n"
            f"Storage: Left {storage_pct}%\n"
            f"Sortation: Right {sortation_pct}%"
        )
        ax.text(1.02, 0.3, info_text, transform=ax.transAxes, fontsize=9,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        output_path = output_dir / f"warehouse_{agents}_agents.{output_format}"
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"Saved {agents}-agent layout to: {output_path}")
        plt.close()
    
    print(f"\nGenerated {len(warehouses)} individual layouts + 1 combined view")
    print(f"Output directory: {output_dir}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Visualize warehouse layouts')
    parser.add_argument('--output', '-o', type=str, help='Output directory')
    parser.add_argument('--agents', '-a', type=int, help='Show only specific agent count')
    parser.add_argument('--format', '-f', type=str, default='png', help='Output format (png or pdf)')
    args = parser.parse_args()
    
    output_dir = Path(args.output) if args.output else None
    output_format = args.format.lower()
    if output_format not in {'png', 'pdf'}:
        print(f"Unsupported format: {args.format}")
        return
    
    if args.agents:
        warehouses = load_configs()
        if args.agents not in warehouses:
            print(f"No config found for {args.agents} agents")
            print(f"Available: {list(warehouses.keys())}")
            return
        
        fig, ax = plt.subplots(figsize=(14, 10))
        draw_warehouse_grid(ax, args.agents, warehouses[args.agents])
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
        plt.tight_layout()
        plt.show()
    else:
        generate_all_layouts(output_dir, output_format)


if __name__ == '__main__':
    main()
