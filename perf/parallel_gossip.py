"""
Parallel gossip implementation using Zero-Copy Shared Memory.
Eliminates serialization overhead for ALL distributed data.
"""

from multiprocessing import Pool, cpu_count, shared_memory
from typing import List, Tuple, Dict, Any
import numpy as np
import time

# Global variables for worker processes
_global_arrays = {}
_shm_refs = []  # Keep references to SHM objects to prevent GC closing handles

def _worker_init(shm_metadata: Dict[str, Any]):
    """Initialize worker process: attach to shared memory blocks"""
    global _global_arrays, _shm_refs
    
    try:
        jam_shape = shm_metadata['shape_jam']
        loc_shape = shm_metadata['shape_loc']
        path_shape = shm_metadata['shape_path']
        
        # Attach to all blocks
        blocks = {
            'jam': (jam_shape, np.float32, np.int32),
            'flow': (jam_shape, np.float32, np.int32),
            'loc': (loc_shape, np.int32, np.int32),
            'path': (path_shape, np.int32, np.int32)
        }
        
        for key, (shape, val_dtype, ts_dtype) in blocks.items():
            val_shm = shared_memory.SharedMemory(name=shm_metadata[f'{key}_vals_name'])
            ts_shm = shared_memory.SharedMemory(name=shm_metadata[f'{key}_ts_name'])
            
            _shm_refs.append(val_shm)
            _shm_refs.append(ts_shm)
            
            _global_arrays[f'{key}_vals'] = np.ndarray(shape, dtype=val_dtype, buffer=val_shm.buf)
            _global_arrays[f'{key}_ts'] = np.ndarray(shape[:-1] if len(shape)==3 else shape, dtype=ts_dtype, buffer=ts_shm.buf)
            
    except Exception as e:
        print(f"Worker init failed: {e}")

def _merge_task(args: Tuple[int, int]) -> int:
    """
    Perform bidirectional merge of two agents using ONLY Shared Memory.
    Zero serialization.
    """
    agent_a_id, agent_b_id = args
    
    # Merge Jam (AxN)
    _merge_rows(agent_a_id, agent_b_id, 'jam')
    # Merge Flow (AxN)
    _merge_rows(agent_a_id, agent_b_id, 'flow')
    
    # Merge Locations (AxA) - Beliefs about other agents
    _merge_rows(agent_a_id, agent_b_id, 'loc')
    
    # Merge Paths (AxAxL) - Beliefs about paths
    _merge_rows(agent_a_id, agent_b_id, 'path')
    
    return 1

def _merge_rows(id_a: int, id_b: int, prefix: str):
    """Vectorized merge of two rows in shared memory"""
    vals = _global_arrays[f'{prefix}_vals']
    ts = _global_arrays[f'{prefix}_ts']
    
    # Get rows (Each agent's belief vector/matrix)
    # Shape: (N,) or (A,) or (A, L)
    row_a_vals = vals[id_a]
    row_a_ts = ts[id_a]
    row_b_vals = vals[id_b]
    row_b_ts = ts[id_b]
    
    # Calculate masks (Who has newer data?)
    b_newer = row_b_ts > row_a_ts
    a_newer = row_a_ts > row_b_ts
    
    # Update A from B
    if row_a_vals.ndim == 2: # Path case (A, L)
        # Mask is (A,). Row is (A, L).
        row_a_vals[b_newer, :] = row_b_vals[b_newer, :]
    else:
        row_a_vals[b_newer] = row_b_vals[b_newer]
    row_a_ts[b_newer] = row_b_ts[b_newer]
    
    # Update B from A
    if row_b_vals.ndim == 2:
        row_b_vals[a_newer, :] = row_a_vals[a_newer, :]
    else:
        row_b_vals[a_newer] = row_a_vals[a_newer]
    row_b_ts[a_newer] = row_a_ts[a_newer]


class ParallelGossipEngine:
    def __init__(self, num_workers: int = None, shm_metadata: Dict[str, Any] = None):
        self.num_workers = num_workers or max(1, cpu_count() // 2)
        self.shm_metadata = shm_metadata
        self.pool = None
        
        self.total_merges = 0
        self.parallel_rounds = 0
    
    def start(self):
        if self.pool is None and self.shm_metadata:
            self.pool = Pool(
                processes=self.num_workers,
                initializer=_worker_init,
                initargs=(self.shm_metadata,)
            )
    
    def stop(self):
        if self.pool is not None:
            self.pool.close()
            self.pool.join()
            self.pool = None
    
    def gossip_round(self, agents: List) -> None:
        if not agents or len(agents) < 2:
            return
        
        if self.pool is None:
            self.start()
        
        import random
        # Fast shuffle of indices only
        agent_ids = [a.unique_id for a in agents]
        random.shuffle(agent_ids)
        
        merge_tasks = []
        for i in range(0, len(agent_ids) - 1, 2):
            merge_tasks.append((agent_ids[i], agent_ids[i+1]))
        
        if not merge_tasks:
            return
        
        # Execute parallel merge (Pure signal)
        self.pool.map(_merge_task, merge_tasks)
        
        self.total_merges += len(merge_tasks)
        self.parallel_rounds += 1
    
    def __del__(self):
        self.stop()
