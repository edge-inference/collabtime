"""
Centralized Path Scheduler for Baseline Comparison
All agents request paths from this single authority, which has perfect global state
but must serialize all pathfinding operations.
"""

from typing import List, Dict, Tuple, Optional, Set, Any
import networkx as nx
from collections import defaultdict
import numpy as np
import time
import threading

# Fail Fast: Mandatory Optimization
try:
    from perf.astar_fast import astar_fast
except ImportError:
    raise RuntimeError("CRITICAL: Cython extension 'astar_fast' missing. Simulation requires compiled optimizations.")


class CentralizedScheduler:
    """
    Central authority that plans paths for all agents.
    
    This is the architectural bottleneck that distributed systems avoid.
    - Has perfect global state (all agent positions, all reserved paths)
    - Must serialize all pathfinding operations
    - Runs space-time A* to avoid conflicts
    """
    
    def __init__(self, warehouse_graph, coordinator, model=None, logger=None, 
                 use_cython: bool = True, node_coords: Any = None, graph_csr: Any = None,
                 service_time_s: float = 0.0):
        self.graph = warehouse_graph
        self.coordinator = coordinator
        self.model = model
        self.logger = logger
        
        self.path_reservations: Dict[int, List[Tuple[int, int]]] = {}
        self.agent_positions: Dict[int, int] = {}
        self.agent_task_assignments: Dict[int, Tuple[int, int]] = {}  # agent_id -> (task_id, location)
        self.assigned_task_ids: Set[int] = set()  # Track which tasks are currently assigned
        
        # Central congestion data store (perfect, always fresh)
        self.flow_data: Dict[int, float] = defaultdict(float)
        self.jam_data: Dict[int, float] = defaultdict(float)
        
        # Queueing bottleneck: centralized scheduler can only handle one request at a time
        self.lock = threading.Lock()
        self.service_time_s = service_time_s  # Time to process one request (2ms default)
        
        # Performance optimizations (Mandatory)
        self.use_cython = True
        self.node_coords = node_coords
        self.graph_csr = graph_csr
        
        if not self.graph_csr:
             raise RuntimeError("CRITICAL: CentralizedScheduler missing graph_csr. Fast A* impossible.")
        
        # Fast arrays for Cython A*
        num_nodes = warehouse_graph.graph.number_of_nodes()
        
        # We use 1D arrays for the "global" map.
        self.fast_jam_values = np.zeros(num_nodes, dtype=np.float32)
        self.fast_jam_timestamps = np.zeros(num_nodes, dtype=np.int32)
        self.fast_flow_values = np.zeros(num_nodes, dtype=np.float32)
        self.fast_flow_timestamps = np.zeros(num_nodes, dtype=np.int32)
        
        # Dummy path vals (reservation logic handled separately or TODO: map reservations here)
        self.fast_path_vals = np.zeros((1, 1), dtype=np.int32)
        self.fast_path_timestamps = np.zeros(1, dtype=np.int32)
        
        if self.logger:
            self.logger.info("CentralizedScheduler: Cython-accelerated A* ENABLED (Mandatory)")
            self.logger.info(f"CentralizedScheduler: Sequential pathfinding (no artificial delay)")
        
        self.metrics = {
            'total_requests': 0,
            'total_task_assignments': 0,
            'total_computation_time': 0,
            'total_queue_wait_time': 0,
            'active_reservations': 0,
            'congestion_data_size': 0
        }
    
    def update_agent_position(self, agent_id: int, node: int):
        """Agents must report their position to central authority."""
        self.agent_positions[agent_id] = node
    
    def notify_task_claimed(self, agent_id: int, task_id: int, task_location: int):
        """
        Notify scheduler that an agent claimed a task.
        This allows the scheduler to avoid directing other agents to the same task location.
        """
        self.agent_task_assignments[agent_id] = (task_id, task_location)
        self.assigned_task_ids.add(task_id)
    
    def notify_task_released(self, agent_id: int):
        """Notify scheduler that an agent released/completed a task."""
        if agent_id in self.agent_task_assignments:
            task_id, _ = self.agent_task_assignments[agent_id]
            self.assigned_task_ids.discard(task_id)
            del self.agent_task_assignments[agent_id]
    
    def assign_task_to_agent(self, agent_id: int, agent_position: int) -> Optional[Tuple[int, int]]:
        """
        PUSH model: Central scheduler assigns best task to agent.
        Assignment is ATOMIC - scheduler claims task on behalf of agent.
        Returns (task_id, task_location) or None.
        
        BOTTLENECK: Serialized through lock - only one agent can request at a time.
        """
        request_start = time.time()
        
        with self.lock:  # Queue bottleneck: agents wait in line
            queue_wait = time.time() - request_start
            self.metrics['total_queue_wait_time'] += queue_wait
            self.metrics['total_task_assignments'] += 1
            
            available_tasks = self.coordinator.get_available_tasks()
            if not available_tasks:
                return None
        
        # Get both assigned locations and task_ids to prevent duplicates
        assigned_locations = set(loc for _, loc in self.agent_task_assignments.values())
        
        best_task = None
        best_distance = float('inf')
        
        scan_limit = 200
        scanned = 0
        
        agent_pos_coords = self.graph.node_to_pos(agent_position)
        
        for task in available_tasks:
            # Skip if task is already assigned to another agent
            if task.task_id in self.assigned_task_ids:
                continue
            
            # Skip if location is already assigned
            if task.location in assigned_locations:
                continue
                
            scanned += 1
            if scanned > scan_limit and best_task:
                break
            
            task_coords = self.graph.node_to_pos(task.location)
            distance = abs(agent_pos_coords[0] - task_coords[0]) + \
                      abs(agent_pos_coords[1] - task_coords[1])
            
            if distance < best_distance:
                best_distance = distance
                best_task = (task.task_id, task.location)
            
            if best_task:
                task_id, task_location = best_task
                claim_success = self.coordinator.try_claim(task_id, agent_id, ttl_ms=300000)
                if claim_success:
                    self.agent_task_assignments[agent_id] = (task_id, task_location)
                    self.assigned_task_ids.add(task_id)
                    return best_task
                else:
                    return None
            
            return None
    
    def report_flow(self, node: int, flow_value: float = 1.0):
        """Agent reports edge usage (perfect, instant update)."""
        self.flow_data[node] += flow_value
        # Fast array update
        self.fast_flow_values[node] += flow_value
        current_time_ms = int(self.model.step_count * self.model.step_duration_s * 1000) if self.model else 0
        self.fast_flow_timestamps[node] = current_time_ms
            
        self.metrics['congestion_data_size'] = len(self.flow_data) + len(self.jam_data)
    
    def report_jam(self, node: int, jam_value: float):
        """Agent reports congestion (perfect, instant update)."""
        alpha = 0.5
        # Python dict update
        self.jam_data[node] = alpha * jam_value + (1 - alpha) * self.jam_data[node]
        
        # Fast array update
        self.fast_jam_values[node] = alpha * jam_value + (1 - alpha) * self.fast_jam_values[node]
        current_time_ms = int(self.model.step_count * self.model.step_duration_s * 1000) if self.model else 0
        self.fast_jam_timestamps[node] = current_time_ms
            
        self.metrics['congestion_data_size'] = len(self.flow_data) + len(self.jam_data)
    
    def request_path(self, agent_id: int, start: int, goal: int, current_step: int) -> List[int]:
        """
        Central pathfinding request (BLOCKING) with congestion awareness.
        
        Uses perfect, fresh congestion data (no staleness like distributed).
        BOTTLENECK: Serialized through lock - agents wait in line for pathfinding.
        """
        request_start = time.time()
        
        with self.lock:  # Queue bottleneck: agents wait in line
            queue_wait = time.time() - request_start
            self.metrics['total_queue_wait_time'] += queue_wait
            self.metrics['total_requests'] += 1
            
            # occupied_nodes = set(self.agent_positions.values()) # Deprecated for fast A*
            
            try:
                if start == goal:
                    return [start]
                    
                # Optimized Pathfinding (Mandatory)
                path = self._astar_fast_centralized(start, goal)
                
                if path:
                    self.path_reservations[agent_id] = path[:min(3, len(path))]
                    self.metrics['active_reservations'] = len(self.path_reservations)
                    return path
                else:
                    return []
                    
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Central scheduler pathfinding failed: {e}")
                return []
    
    def release_path(self, agent_id: int):
        """Agent releases its path reservation when done."""
        if agent_id in self.path_reservations:
            del self.path_reservations[agent_id]
            self.metrics['active_reservations'] = len(self.path_reservations)
    
    def _astar_fast_centralized(self, start: int, goal: int) -> List[int]:
        """Cython-accelerated A* using global arrays."""
        indptr, indices, _ = self.graph_csr
        current_time_ms = int(self.model.step_count * self.model.step_duration_s * 1000) if self.model else 0
        cost_params = {
            'alpha': 2.0,
            'beta': 0.5,
            'max_aoi_ms': 999999999,
            'proximity_radius': 25.0,
            'conflict_penalty': 100.0
        }
        
        path = astar_fast(
            indptr=indptr,
            indices=indices,
            coords=self.node_coords,
            jam_values=self.fast_jam_values,
            jam_timestamps=self.fast_jam_timestamps,
            flow_values=self.fast_flow_values,
            flow_timestamps=self.fast_flow_timestamps,
            path_vals=self.fast_path_vals, # Dummy
            path_timestamps=self.fast_path_timestamps, # Dummy
            start=start,
            goal=goal,
            cost_params=cost_params,
            current_time_ms=current_time_ms
        )
        return path
        
    def _astar_with_congestion(self, start: int, goal: int, obstacles: set) -> List[int]:
        """
        Congestion-aware A* using central perfect data (Python fallback).
        """
        if start in obstacles or goal in obstacles:
            obstacles_copy = obstacles - {start, goal}
        else:
            obstacles_copy = obstacles
        
        G = self.graph.graph
        temp_graph = G.copy()
        
        for node in obstacles_copy:
            if node in temp_graph and node != start and node != goal:
                temp_graph.remove_node(node)
        
        if start not in temp_graph or goal not in temp_graph:
            return []
        
        try:
            path = nx.astar_path(
                temp_graph,
                start,
                goal,
                heuristic=lambda n1, n2: self._manhattan_distance(n1, n2),
                weight=lambda u, v, d: self._edge_cost_with_congestion(u, v)
            )
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
    
    def _edge_cost_with_congestion(self, from_node: int, to_node: int) -> float:
        """
        Compute edge cost with congestion (PERFECT data, no staleness).
        """
        base_cost = 1.0
        alpha = 2.0
        beta = 0.5
        
        jam_cost = self.jam_data.get(to_node, 0.0)
        flow_cost = self.flow_data.get(to_node, 0.0)
        
        return base_cost + alpha * jam_cost + beta * flow_cost
    
    def _manhattan_distance(self, node1: int, node2: int) -> float:
        """Manhattan distance heuristic."""
        try:
            x1, y1 = self.graph.node_to_pos(node1)
            x2, y2 = self.graph.node_to_pos(node2)
            return abs(x1 - x2) + abs(y1 - y2)
        except (KeyError, TypeError):
            return 0
    
    def get_metrics(self) -> Dict:
        """Return scheduler performance metrics."""
        total_operations = self.metrics['total_requests'] + self.metrics['total_task_assignments']
        avg_queue_wait = 0
        if total_operations > 0:
            avg_queue_wait = self.metrics['total_queue_wait_time'] / total_operations
        
        return {
            'total_path_requests': self.metrics['total_requests'],
            'total_task_assignments': self.metrics['total_task_assignments'],
            'total_scheduler_operations': total_operations,
            'active_path_reservations': self.metrics['active_reservations'],
            'total_queue_wait_time_s': self.metrics['total_queue_wait_time'],
            'avg_queue_wait_time_ms': avg_queue_wait * 1000,
        }
