# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True

"""
Cython-optimized A* pathfinding for 5-10x speedup.
"""

import heapq
from libc.stdlib cimport malloc, free
from libc.math cimport fabs


cpdef list astar_fast(object warehouse, object dsm_api, int start, int goal, dict cost_params):
    if start == goal:
        return [start]
    
    cdef float alpha = cost_params.get('alpha', 2.0)
    cdef float beta = cost_params.get('beta', 0.5)
    cdef int max_aoi_ms = cost_params.get('max_aoi_ms', 5000)
    
    cdef list open_set = []
    heapq.heappush(open_set, (0.0, start))
    cdef dict came_from = {}
    cdef dict g_score = {start: 0.0}
    cdef dict f_score = {start: _heuristic_fast(warehouse, start, goal)}
    
    cdef int current
    cdef float current_g
    cdef list neighbors
    cdef int neighbor
    cdef float edge_cost, tentative_g, f
    
    while open_set:
        _, current = heapq.heappop(open_set)
        
        if current == goal:
            return _reconstruct_path_fast(came_from, current)
        
        neighbors = warehouse.get_neighbors(current)
        current_g = g_score.get(current, float('inf'))
        
        for neighbor in neighbors:
            edge_cost = _compute_edge_cost_fast(
                warehouse, dsm_api, current, neighbor,
                alpha, beta, max_aoi_ms
            )
            
            tentative_g = current_g + edge_cost
            
            if tentative_g < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + _heuristic_fast(warehouse, neighbor, goal)
                f_score[neighbor] = f
                heapq.heappush(open_set, (f, neighbor))
    
    return []


cdef inline float _heuristic_fast(object warehouse, int node, int goal):
    try:
        x1, y1 = warehouse.node_to_pos(node)
        x2, y2 = warehouse.node_to_pos(goal)
        return fabs(x2 - x1) + fabs(y2 - y1)
    except:
        return 0.0


cdef inline float _compute_edge_cost_fast(object warehouse, object dsm_api, 
                                          int from_node, int to_node,
                                          float alpha, float beta, int max_aoi_ms):
    cdef float cost = 1.0
    cdef float jam_value, flow_value
    
    if dsm_api is None:
        return cost
    
    try:
        if hasattr(dsm_api, 'read_jam'):
            jam_value = dsm_api.read_jam(to_node, max_aoi_ms)
            flow_value = dsm_api.read_flow(to_node, max_aoi_ms)
        else:
            jam_result = dsm_api.read_window('jam_signal', to_node, radius=0, max_aoi_ms=max_aoi_ms)
            jam_value = jam_result.get('peak_value', 0.0)
            
            flow_result = dsm_api.read_window('flow_trace', to_node, radius=0, max_aoi_ms=max_aoi_ms)
            flow_value = flow_result.get('peak_value', 0.0)
        
        cost += alpha * jam_value
        cost += beta * flow_value
    except:
        pass
    
    return max(1.0, cost)


cdef list _reconstruct_path_fast(dict came_from, int current):
    cdef list path = [current]
    while current in came_from:
        current = came_from[current]
        path.insert(0, current)
    return path

