# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True

"""
Cython-optimized cache merging for 3-5x speedup in gossip rounds.
"""

cpdef void merge_caches_fast(object cache_a, object cache_b):
    _merge_layer(cache_a.flow_trace, cache_b.flow_trace)
    _merge_layer(cache_a.jam_signal, cache_b.jam_signal)
    _merge_layer(cache_a.agent_location, cache_b.agent_location)
    _merge_layer(cache_a.path_intent, cache_b.path_intent)
    _merge_layer(cache_a.resource_state, cache_b.resource_state)


cdef inline void _merge_layer(dict target, dict source):
    cdef object key, other_entry, my_entry
    cdef long other_ts, my_ts
    
    for key in source:
        other_entry = source[key]
        other_ts = other_entry.get('timestamp', 0)
        
        if key in target:
            my_entry = target[key]
            my_ts = my_entry.get('timestamp', 0)
            
            if other_ts > my_ts:
                target[key] = other_entry.copy()
        else:
            target[key] = other_entry.copy()


cpdef void merge_bidirectional_fast(object cache_a, object cache_b):
    cache_a_copy_flow = cache_a.flow_trace.copy()
    cache_a_copy_jam = cache_a.jam_signal.copy()
    cache_a_copy_agent = cache_a.agent_location.copy()
    cache_a_copy_path = cache_a.path_intent.copy()
    cache_a_copy_resource = cache_a.resource_state.copy()
    
    merge_caches_fast(cache_a, cache_b)
    
    _merge_layer(cache_b.flow_trace, cache_a_copy_flow)
    _merge_layer(cache_b.jam_signal, cache_a_copy_jam)
    _merge_layer(cache_b.agent_location, cache_a_copy_agent)
    _merge_layer(cache_b.path_intent, cache_a_copy_path)
    _merge_layer(cache_b.resource_state, cache_a_copy_resource)

