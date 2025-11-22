"""
Parallel gossip implementation using multiprocessing to bypass GIL.
"""

from multiprocessing import Pool, cpu_count
from typing import List, Tuple
import pickle


def _merge_cache_pair(args: Tuple) -> Tuple[int, int, bytes, bytes]:
    agent_a_id, agent_b_id, cache_a_bytes, cache_b_bytes = args
    
    from dsm.local_cache import LocalDSMCache
    
    cache_a = pickle.loads(cache_a_bytes)
    cache_b = pickle.loads(cache_b_bytes)
    
    cache_a.merge_from(cache_b)
    cache_b.merge_from(cache_a)
    
    return (agent_a_id, agent_b_id, pickle.dumps(cache_a), pickle.dumps(cache_b))


class ParallelGossipEngine:
    def __init__(self, num_workers: int = None):
        self.num_workers = num_workers or max(1, cpu_count() // 2)
        self.pool = None
        
        self.total_merges = 0
        self.parallel_rounds = 0
    
    def start(self):
        if self.pool is None:
            self.pool = Pool(processes=self.num_workers)
    
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
        shuffled_agents = list(agents)
        random.shuffle(shuffled_agents)
        
        pairs = []
        merge_tasks = []
        
        for i in range(0, len(shuffled_agents) - 1, 2):
            agent_a = shuffled_agents[i]
            agent_b = shuffled_agents[i + 1]
            
            if hasattr(agent_a, 'local_cache') and hasattr(agent_b, 'local_cache'):
                if agent_a.local_cache is not None and agent_b.local_cache is not None:
                    pairs.append((agent_a, agent_b))
                    
                    cache_a_bytes = pickle.dumps(agent_a.local_cache)
                    cache_b_bytes = pickle.dumps(agent_b.local_cache)
                    merge_tasks.append((agent_a.unique_id, agent_b.unique_id, cache_a_bytes, cache_b_bytes))
        
        if not merge_tasks:
            return
        
        results = self.pool.map(_merge_cache_pair, merge_tasks)
        
        id_to_agent = {agent.unique_id: agent for agent, _ in pairs}
        for agent, _ in pairs:
            id_to_agent[agent.unique_id] = agent
        for _, agent in pairs:
            id_to_agent[agent.unique_id] = agent
        
        for agent_a_id, agent_b_id, cache_a_bytes, cache_b_bytes in results:
            id_to_agent[agent_a_id].local_cache = pickle.loads(cache_a_bytes)
            id_to_agent[agent_b_id].local_cache = pickle.loads(cache_b_bytes)
        
        self.total_merges += len(merge_tasks)
        self.parallel_rounds += 1
    
    def get_stats(self) -> dict:
        return {
            'num_workers': self.num_workers,
            'total_merges': self.total_merges,
            'parallel_rounds': self.parallel_rounds
        }
    
    def __del__(self):
        self.stop()

