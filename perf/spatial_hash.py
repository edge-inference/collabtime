"""
Grid-based spatial hash for O(1) agent location queries.
"""

import numpy as np
from typing import List, Tuple, Set, Optional


class SpatialHash:
    def __init__(self, width: int, height: int, cell_size: int = 5):
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.grid_width = (width + cell_size - 1) // cell_size
        self.grid_height = (height + cell_size - 1) // cell_size
        
        self.grid = [[set() for _ in range(self.grid_width)] for _ in range(self.grid_height)]
        
        self.agent_positions = {}
        
        self.queries = 0
        self.updates = 0
    
    def _get_cell(self, x: int, y: int) -> Tuple[int, int]:
        cell_x = min(x // self.cell_size, self.grid_width - 1)
        cell_y = min(y // self.cell_size, self.grid_height - 1)
        return (cell_x, cell_y)
    
    def update(self, agent_id: int, x: int, y: int):
        self.updates += 1
        
        if agent_id in self.agent_positions:
            old_x, old_y = self.agent_positions[agent_id]
            old_cell_x, old_cell_y = self._get_cell(old_x, old_y)
            self.grid[old_cell_y][old_cell_x].discard(agent_id)
        
        self.agent_positions[agent_id] = (x, y)
        cell_x, cell_y = self._get_cell(x, y)
        self.grid[cell_y][cell_x].add(agent_id)
    
    def remove(self, agent_id: int):
        if agent_id in self.agent_positions:
            x, y = self.agent_positions[agent_id]
            cell_x, cell_y = self._get_cell(x, y)
            self.grid[cell_y][cell_x].discard(agent_id)
            del self.agent_positions[agent_id]
    
    def get_agents_at(self, x: int, y: int) -> Set[int]:
        self.queries += 1
        cell_x, cell_y = self._get_cell(x, y)
        return self.grid[cell_y][cell_x].copy()
    
    def get_agents_in_radius(self, x: int, y: int, radius: int) -> List[int]:
        self.queries += 1
        agents = set()
        
        cell_radius = (radius + self.cell_size - 1) // self.cell_size
        center_cell_x, center_cell_y = self._get_cell(x, y)
        
        for dy in range(-cell_radius, cell_radius + 1):
            for dx in range(-cell_radius, cell_radius + 1):
                cell_x = center_cell_x + dx
                cell_y = center_cell_y + dy
                
                if 0 <= cell_x < self.grid_width and 0 <= cell_y < self.grid_height:
                    for agent_id in self.grid[cell_y][cell_x]:
                        agent_x, agent_y = self.agent_positions[agent_id]
                        if abs(agent_x - x) + abs(agent_y - y) <= radius:
                            agents.add(agent_id)
        
        return list(agents)
    
    def get_position(self, agent_id: int) -> Optional[Tuple[int, int]]:
        return self.agent_positions.get(agent_id)
    
    def get_all_positions(self) -> dict:
        return self.agent_positions.copy()
    
    def clear(self):
        self.grid = [[set() for _ in range(self.grid_width)] for _ in range(self.grid_height)]
        self.agent_positions.clear()
    
    def get_stats(self) -> dict:
        return {
            'queries': self.queries,
            'updates': self.updates,
            'num_agents': len(self.agent_positions)
        }

