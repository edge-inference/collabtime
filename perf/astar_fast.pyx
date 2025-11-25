# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True

"""
Cython-optimized A* pathfinding with O(1) path conflict checking.
Uses a spatial index to avoid O(N²) agent scans.
"""

import heapq
import numpy as np
cimport numpy as cnp
from libc.math cimport fabs
from libc.stdlib cimport malloc, free

# Initialize numpy C API
cnp.import_array()

cdef struct ConflictIndex:
    int* node_to_count
    int num_nodes

cdef ConflictIndex* _build_conflict_index(
    int[:,:] path_vals,
    int[:] path_timestamps,
    int num_nodes,
    float[:,:] coords,
    int start,
    int goal,
    float proximity_radius,
    int current_time_ms,
    int max_aoi_ms
) nogil:
    cdef ConflictIndex* idx = <ConflictIndex*>malloc(sizeof(ConflictIndex))
    idx.num_nodes = num_nodes
    idx.node_to_count = <int*>malloc(num_nodes * sizeof(int))
    
    cdef int i, j, node_id
    for i in range(num_nodes):
        idx.node_to_count[i] = 0
    
    cdef int num_agents = path_vals.shape[0]
    cdef int path_len = path_vals.shape[1]
    
    cdef float min_x, max_x, min_y, max_y
    cdef float node_x, node_y
    cdef float start_x = coords[start, 0]
    cdef float start_y = coords[start, 1]
    cdef float goal_x = coords[goal, 0]
    cdef float goal_y = coords[goal, 1]
    
    min_x = start_x if start_x < goal_x else goal_x
    max_x = start_x if start_x > goal_x else goal_x
    min_y = start_y if start_y < goal_y else goal_y
    max_y = start_y if start_y > goal_y else goal_y
    
    min_x -= proximity_radius
    max_x += proximity_radius
    min_y -= proximity_radius
    max_y += proximity_radius
    
    for i in range(num_agents):
        if (current_time_ms - path_timestamps[i]) <= max_aoi_ms:
            for j in range(path_len):
                node_id = path_vals[i, j]
                if node_id >= 0 and node_id < num_nodes:
                    node_x = coords[node_id, 0]
                    node_y = coords[node_id, 1]
                    
                    if (node_x >= min_x and node_x <= max_x and
                        node_y >= min_y and node_y <= max_y):
                        idx.node_to_count[node_id] += 1
    
    return idx

cdef void _free_conflict_index(ConflictIndex* idx) noexcept nogil:
    if idx != NULL:
        if idx.node_to_count != NULL:
            free(idx.node_to_count)
        free(idx)

cpdef list astar_fast(
    int[:] indptr, 
    int[:] indices, 
    float[:,:] coords, 
    float[:] jam_values, 
    int[:] jam_timestamps,
    float[:] flow_values, 
    int[:] flow_timestamps,
    int[:,:] path_vals,
    int[:] path_timestamps,
    int start, 
    int goal, 
    dict cost_params,
    int current_time_ms
):
    if start == goal:
        return [start]
    
    cdef float alpha = cost_params.get('alpha', 2.0)
    cdef float beta = cost_params.get('beta', 0.5)
    cdef int max_aoi_ms = cost_params.get('max_aoi_ms', 5000)
    cdef float conflict_penalty = cost_params.get('conflict_penalty', 100.0)
    cdef float proximity_radius = cost_params.get('proximity_radius', 25.0)
    
    cdef int num_nodes = coords.shape[0]
    cdef ConflictIndex* conflict_idx = _build_conflict_index(
        path_vals, path_timestamps, num_nodes, coords, start, goal,
        proximity_radius, current_time_ms, max_aoi_ms
    )
    
    cdef list open_set = []
    heapq.heappush(open_set, (0.0, start))
    cdef dict came_from = {}
    cdef dict g_score = {start: 0.0}
    cdef float h_start = _heuristic_fast(coords, start, goal)
    cdef dict f_score = {start: h_start}
    
    cdef int current
    cdef float current_g
    cdef int i
    cdef int neighbor
    cdef float edge_cost, tentative_g, f
    
    while open_set:
        _, current = heapq.heappop(open_set)
        
        if current == goal:
            _free_conflict_index(conflict_idx)
            return _reconstruct_path_fast(came_from, current)
        
        # Get neighbors from CSR arrays
        for i in range(indptr[current], indptr[current+1]):
            neighbor = indices[i]
            
            current_g = g_score.get(current, float('inf'))
            
            edge_cost = _compute_edge_cost_fast(
                jam_values, jam_timestamps,
                flow_values, flow_timestamps,
                conflict_idx,
                neighbor,
                alpha, beta, max_aoi_ms, current_time_ms, conflict_penalty
            )
            
            tentative_g = current_g + edge_cost
            
            if tentative_g < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + _heuristic_fast(coords, neighbor, goal)
                f_score[neighbor] = f
                heapq.heappush(open_set, (f, neighbor))
    
    _free_conflict_index(conflict_idx)
    return []


cdef inline float _heuristic_fast(float[:,:] coords, int node, int goal):
    return fabs(coords[goal, 0] - coords[node, 0]) + fabs(coords[goal, 1] - coords[node, 1])


cdef inline float _compute_edge_cost_fast(
    float[:] jam_values, 
    int[:] jam_timestamps,
    float[:] flow_values, 
    int[:] flow_timestamps,
    ConflictIndex* conflict_idx,
    int to_node,
    float alpha, 
    float beta, 
    int max_aoi_ms,
    int current_time_ms,
    float conflict_penalty
) nogil:
    cdef float cost = 1.0
    cdef float jam_val = 0.0
    cdef float flow_val = 0.0
    
    if (current_time_ms - jam_timestamps[to_node]) <= max_aoi_ms:
        jam_val = jam_values[to_node]
        
    if (current_time_ms - flow_timestamps[to_node]) <= max_aoi_ms:
        flow_val = flow_values[to_node]
    
    if to_node >= 0 and to_node < conflict_idx.num_nodes:
        if conflict_idx.node_to_count[to_node] > 0:
            cost += conflict_penalty
    
    cost += alpha * jam_val
    cost += beta * flow_val
    
    return cost


cdef list _reconstruct_path_fast(dict came_from, int current):
    cdef list path = [current]
    while current in came_from:
        current = came_from[current]
        path.insert(0, current)
    return path
