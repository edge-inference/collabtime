"""
Local CRDT-style Cache for Peer-to-Peer DSM

Each agent maintains its own local cache with timestamped values.
Gossip protocol merges caches using Last-Write-Wins (LWW) semantics.
"""

from typing import Dict, Any, Optional
import time
import numpy as np
from multiprocessing import shared_memory

try:
    CYTHON_MERGE_AVAILABLE = False
except ImportError:
    CYTHON_MERGE_AVAILABLE = False


class LocalDSMCache:
    """
    Local cache of spatial and resource data with LWW merge semantics.
    """
    
    def __init__(self, agent_id: int, num_nodes: int = 0, shm_metadata: Dict[str, Any] = None):
        self.agent_id = agent_id
        self.num_nodes = num_nodes
        
        # Resource state (sparse, kept as dict)
        self.resource_state: Dict[str, Dict[str, Any]] = {}

        # Fast access arrays for A* optimization
        self.use_fast_arrays = num_nodes > 0
        self.shm_metadata = shm_metadata
        
        # Shared Memory buffers (keep references to prevent GC closing them)
        self._shm_refs = []

        if self.use_fast_arrays:
            if shm_metadata:
                # Zero-Copy Shared Memory Mode
                try:
                    # Attach to existing shared memory
                    shm_jam_vals = shared_memory.SharedMemory(name=shm_metadata['jam_vals_name'])
                    shm_jam_ts = shared_memory.SharedMemory(name=shm_metadata['jam_ts_name'])
                    shm_flow_vals = shared_memory.SharedMemory(name=shm_metadata['flow_vals_name'])
                    shm_flow_ts = shared_memory.SharedMemory(name=shm_metadata['flow_ts_name'])
                    
                    self._shm_refs.extend([shm_jam_vals, shm_jam_ts, shm_flow_vals, shm_flow_ts])
                    
                    # Create numpy wrappers around entire buffer
                    shape = shm_metadata['shape_jam'] # (num_agents, num_nodes)
                    
                    all_jam_vals = np.ndarray(shape, dtype=np.float32, buffer=shm_jam_vals.buf)
                    all_jam_ts = np.ndarray(shape, dtype=np.int32, buffer=shm_jam_ts.buf)
                    all_flow_vals = np.ndarray(shape, dtype=np.float32, buffer=shm_flow_vals.buf)
                    all_flow_ts = np.ndarray(shape, dtype=np.int32, buffer=shm_flow_ts.buf)
                    
                    # Slice ONLY this agent's row
                    self.jam_values = all_jam_vals[agent_id]
                    self.jam_timestamps = all_jam_ts[agent_id]
                    self.flow_values = all_flow_vals[agent_id]
                    self.flow_timestamps = all_flow_ts[agent_id]
                    
                    # Locations (Agents x Agents) -> Slice: (Agents,)
                    shm_loc_vals = shared_memory.SharedMemory(name=shm_metadata['loc_vals_name'])
                    shm_loc_ts = shared_memory.SharedMemory(name=shm_metadata['loc_ts_name'])
                    self._shm_refs.extend([shm_loc_vals, shm_loc_ts])
                    
                    all_loc_vals = np.ndarray(shm_metadata['shape_loc'], dtype=np.int32, buffer=shm_loc_vals.buf)
                    all_loc_ts = np.ndarray(shm_metadata['shape_loc'], dtype=np.int32, buffer=shm_loc_ts.buf)
                    
                    self.loc_vals = all_loc_vals[agent_id]
                    self.loc_timestamps = all_loc_ts[agent_id]
                    
                    # Paths (Agents x Agents x PathLen) -> Slice: (Agents, PathLen)
                    shm_path_vals = shared_memory.SharedMemory(name=shm_metadata['path_vals_name'])
                    shm_path_ts = shared_memory.SharedMemory(name=shm_metadata['path_ts_name'])
                    self._shm_refs.extend([shm_path_vals, shm_path_ts])
                    
                    all_path_vals = np.ndarray(shm_metadata['shape_path'], dtype=np.int32, buffer=shm_path_vals.buf)
                    all_path_ts = np.ndarray(shm_metadata['shape_loc'], dtype=np.int32, buffer=shm_path_ts.buf) # TS is (AxA)
                    
                    self.path_vals = all_path_vals[agent_id]
                    self.path_timestamps = all_path_ts[agent_id]
                    self.max_path_len = shm_metadata['shape_path'][2]
                    self.num_agents = shm_metadata['num_agents']
                    
                except Exception as e:
                    print(f"Agent {agent_id}: Failed to attach to SHM: {e}")
                    # Fallback not implemented for all-in mode
                    raise e
            else:
                # Local Array Mode (Fallback) - partial
                self.jam_values = np.zeros(num_nodes, dtype=np.float32)
                self.jam_timestamps = np.zeros(num_nodes, dtype=np.int32)
                self.flow_values = np.zeros(num_nodes, dtype=np.float32)
                self.flow_timestamps = np.zeros(num_nodes, dtype=np.int32)

    def __getstate__(self):
        """Custom pickle state to exclude SHM/Arrays and huge dicts"""
        state = self.__dict__.copy()
        # Remove SHM references (not picklable)
        keys_to_remove = ['jam_values', 'jam_timestamps', 'flow_values', 'flow_timestamps',
                         'loc_vals', 'loc_timestamps', 'path_vals', 'path_timestamps', '_shm_refs']
        for k in keys_to_remove:
            if k in state:
                state[k] = None
        
        # Exclude huge dicts if we are using SHM
        if self.use_fast_arrays and self.shm_metadata:
            state['jam_signal'] = {}
            state['flow_trace'] = {}
            # Also exclude loc/path dicts as we rely on SHM now
            state['agent_location'] = {}
            state['path_intent'] = {}
            
        return state

    def __setstate__(self, state):
        """Restore state (worker won't use SHM this way, but for safety)"""
        self.__dict__.update(state)
        # We do NOT re-attach SHM here. Workers attach globally or ignored.
        
    def write_flow(self, node_id: int, value: float, timestamp_ms: int):
        """Write flow trace value at node"""
        # Update SHM
        if self.use_fast_arrays and self.shm_metadata:
            if timestamp_ms >= self.flow_timestamps[node_id]:
                self.flow_values[node_id] = value
                self.flow_timestamps[node_id] = timestamp_ms
            return
        
        raise RuntimeError("SHM arrays required")
    
    def write_jam(self, node_id: int, value: float, timestamp_ms: int):
        """Write jam signal value at node"""
        # Update SHM
        if self.use_fast_arrays and self.shm_metadata:
            if timestamp_ms >= self.jam_timestamps[node_id]:
                # Simple LWW for array (no alpha blending in raw update, agent logic does blending before write)
                # Or we blend here? Agent usually calls with calculated value.
                # Original logic had blending against 'existing'.
                # We can read existing from array!
                existing_val = self.jam_values[node_id]
                alpha = 0.5
                merged_value = alpha * value + (1 - alpha) * existing_val
                self.jam_values[node_id] = min(merged_value, 5.0)
                self.jam_timestamps[node_id] = timestamp_ms
            return
        
        raise RuntimeError("SHM arrays required")
    
    def read_flow(self, node_id: int, max_aoi_ms: int, current_time_ms: int = None) -> float:
        """Read flow trace at node (with AoI filtering)"""
        if current_time_ms is None:
            current_time_ms = int(time.time() * 1000)
        current_time = current_time_ms
        
        if self.use_fast_arrays and self.shm_metadata:
            try:
                if (current_time - self.flow_timestamps[node_id]) <= max_aoi_ms:
                    return float(self.flow_values[node_id])
                return 0.0
            except IndexError:
                pass
        
        raise RuntimeError("SHM arrays required")
    
    def read_jam(self, node_id: int, max_aoi_ms: int, current_time_ms: int = None) -> float:
        """Read jam signal at node (with AoI filtering)"""
        if current_time_ms is None:
            current_time_ms = int(time.time() * 1000)
        current_time = current_time_ms
        
        if self.use_fast_arrays and self.shm_metadata:
            try:
                if (current_time - self.jam_timestamps[node_id]) <= max_aoi_ms:
                    return float(self.jam_values[node_id])
                return 0.0
            except IndexError:
                pass
        
        raise RuntimeError("SHM arrays required")
    
    def write_agent_location(self, agent_id: int, node_id: int, timestamp_ms: int):
        """Write agent's current location"""
        if self.use_fast_arrays and self.shm_metadata:
            if agent_id < len(self.loc_vals):
                if timestamp_ms >= self.loc_timestamps[agent_id]:
                    self.loc_vals[agent_id] = node_id
                    self.loc_timestamps[agent_id] = timestamp_ms
            return
        
        raise RuntimeError("SHM arrays required")
    
    def read_agents_at_node(self, node_id: int, max_aoi_ms: int, current_time_ms: int = None) -> int:
        """Count agents at a node based on cached locations (with AoI filtering)"""
        if current_time_ms is None:
            current_time_ms = int(time.time() * 1000)
        current_time = current_time_ms
        
        if self.use_fast_arrays and self.shm_metadata:
            # Vectorized count
            # Check AoI: (current - ts) <= max
            valid_mask = (current_time - self.loc_timestamps) <= max_aoi_ms
            # Check node match
            node_mask = self.loc_vals == node_id
            # Count
            return np.count_nonzero(valid_mask & node_mask)

        count = 0
        raise RuntimeError("SHM arrays required")
    
    def write_path_intent_batch(self, agent_id: int, path: list, start_time_ms: int, duration_ms: int, timestamp_ms: int):
        """
        Write full path to cache.
        Optimized for Shared Memory (Zero Copy).
        Falls back to Dict for legacy/testing modes.
        """
        # Optimized Path (Shared Memory)
        if self.use_fast_arrays and self.shm_metadata:
            if timestamp_ms >= self.path_timestamps[agent_id]:
                self.path_vals[agent_id, :] = -1
                length = min(len(path), self.max_path_len)
                self.path_vals[agent_id, :length] = path[:length]
                self.path_timestamps[agent_id] = timestamp_ms
            return

        # Fallback Path (Dicts - mostly for unit tests)
        raise RuntimeError("SHM arrays required")

    def write_resource_state(self, resource_id: str, owner_id: int, 
                            expires_at_ms: int, timestamp_ms: int):
        """Write resource lock state (who owns it, when it expires)"""
        self.resource_state[resource_id] = {
            'owner': owner_id,
            'expires_at': expires_at_ms,
            'timestamp': timestamp_ms
        }
    
    def read_resource_owner(self, resource_id: str, max_aoi_ms: int) -> Optional[int]:
        """Check who owns a resource (returns None if free or stale data)"""
        current_time = int(time.time() * 1000)
        entry = self.resource_state.get(resource_id)
        
        if not entry:
            return None
        
        age_ms = current_time - entry['timestamp']
        if age_ms > max_aoi_ms:
            return None
        
        if current_time >= entry['expires_at']:
            return None
        
        return entry['owner']
    
    def release_resource_state(self, resource_id: str, timestamp_ms: int):
        """Mark a resource as released"""
        self.resource_state[resource_id] = {
            'owner': None,
            'expires_at': 0,
            'timestamp': timestamp_ms
        }
    
    def merge_from(self, other: 'LocalDSMCache'):
        """
        Merge another agent's cache into this one using LWW.
        Unified implementation using Vectorized Numpy (works for SHM and Local).
        """
        # 1. Jam Signal
        mask = other.jam_timestamps > self.jam_timestamps
        self.jam_values[mask] = other.jam_values[mask]
        self.jam_timestamps[mask] = other.jam_timestamps[mask]
        
        # 2. Flow Trace
        mask = other.flow_timestamps > self.flow_timestamps
        self.flow_values[mask] = other.flow_values[mask]
        self.flow_timestamps[mask] = other.flow_timestamps[mask]
        
        # 3. Agent Locations
        mask = other.loc_timestamps > self.loc_timestamps
        self.loc_vals[mask] = other.loc_vals[mask]
        self.loc_timestamps[mask] = other.loc_timestamps[mask]
        
        # 4. Path Intents
        mask = other.path_timestamps > self.path_timestamps
        self.path_vals[mask, :] = other.path_vals[mask, :]
        self.path_timestamps[mask] = other.path_timestamps[mask]
        
        # 5. Resource State (Sparse)
        for resource_id, other_entry in other.resource_state.items():
            my_entry = self.resource_state.get(resource_id, {'timestamp': 0})
            if other_entry.get('timestamp', 0) > my_entry.get('timestamp', 0):
                self.resource_state[resource_id] = other_entry.copy()

    
    def get_stats(self, current_time_ms: int = None) -> Dict[str, int]:
        """Get cache statistics - counts actual entries in use"""
        if self.use_fast_arrays and self.shm_metadata:
            # Count non-zero/fresh entries in SHM arrays
            if current_time_ms is None:
                current_time_ms = int(time.time() * 1000)
            current_time = current_time_ms
            max_aoi = 10000  # 10 seconds
            
            # Count fresh jam entries (per node)
            jam_fresh = np.sum((current_time - self.jam_timestamps) <= max_aoi)
            # Count fresh flow entries (per node)
            flow_fresh = np.sum((current_time - self.flow_timestamps) <= max_aoi)
            # Count fresh location entries (per agent)
            loc_fresh = np.sum((current_time - self.loc_timestamps) <= max_aoi)
            # Count fresh path entries (per agent)
            path_fresh = np.sum((current_time - self.path_timestamps) <= max_aoi)
            
            return {
                'jam_entries': int(jam_fresh),
                'flow_entries': int(flow_fresh),
                'agent_locations': int(loc_fresh),
                'path_intents': int(path_fresh),
                'resource_states': len(self.resource_state)
            }
        
        # SHM mode is mandatory, this should never execute
        raise RuntimeError("LocalDSMCache requires shared memory arrays (use_fast_arrays=True)")
    
    def get_jam_intensity(self, current_time_ms: int, max_aoi_ms: int) -> float:
        """Get total jam intensity (sum of fresh jam values in cache)"""
        if self.use_fast_arrays and self.shm_metadata:
            fresh_mask = (current_time_ms - self.jam_timestamps) <= max_aoi_ms
            return float(np.sum(self.jam_values[fresh_mask]))
        raise RuntimeError("SHM arrays required")
    
    def cleanup_stale_entries(self, max_age_ms: int, current_time_ms: int = None):
        """Remove cache entries older than max_age_ms to prevent unbounded growth"""
        if current_time_ms is None:
            current_time_ms = int(time.time() * 1000)
        current_time = current_time_ms
        
        if self.use_fast_arrays and self.shm_metadata:
            # SHM arrays don't need cleanup - timestamps naturally filter stale data
            # Only cleanup sparse resource_state dict
            self.resource_state = {
                k: v for k, v in self.resource_state.items()
                if current_time - v['timestamp'] <= max_age_ms
            }
            return
        
        raise RuntimeError("SHM arrays required")

