"""
Parallel Agent Scheduler for realistic multi-agent simulation.

Each agent computes on its own "brain" (CPU core) simultaneously,
matching physical deployment where robots think in parallel.

Uses threading (not multiprocessing) because:
- Agents share state with model (coordinator, edge_reservations, etc.)
- Heavy operations (Cython A*, NumPy DSM) release GIL
- Coordinator operations are fast (dict lookups, simple logic)
"""

from concurrent.futures import ThreadPoolExecutor
from typing import List
import random
import os


class ParallelScheduler:
    """
    Parallel agent scheduler that steps all agents simultaneously.
    
    More realistic than sequential stepping - matches physical robots
    where each has its own onboard compute running in parallel.
    
    Uses threads instead of processes to share model state.
    Most heavy work (A* pathfinding, DSM) is in Cython/NumPy which releases GIL.
    """
    
    def __init__(self, model, num_workers: int = None):
        self.model = model
        self.agents = []
        
        if num_workers is None:
            cpu_count = os.cpu_count() or 4
            num_workers = min(cpu_count // 2, 32)
        
        self.num_workers = num_workers
        self.executor = None
    
    def add(self, agent):
        """Add agent to schedule"""
        self.agents.append(agent)
    
    def start_executor(self):
        """Start thread pool (lazy initialization)"""
        if self.executor is None and len(self.agents) > 0:
            self.executor = ThreadPoolExecutor(max_workers=self.num_workers)
    
    def step(self):
        """Step all agents in parallel"""
        if not self.agents:
            return
        
        # Shuffle for fairness (task claiming)
        shuffled_agents = list(self.agents)
        random.shuffle(shuffled_agents)
        
        # For small agent counts, sequential is faster (no threading overhead)
        if len(self.agents) < 50:
            for agent in shuffled_agents:
                if hasattr(agent, "step"):
                    agent.step()
            return
        
        # Parallel stepping for large agent counts
        if self.executor is None:
            self.start_executor()
        
        # Submit all agent steps in parallel
        def step_agent(agent):
            if hasattr(agent, "step"):
                agent.step()
        
        # Map step operations across thread pool
        list(self.executor.map(step_agent, shuffled_agents))
    
    def stop(self):
        """Stop thread pool"""
        if self.executor is not None:
            self.executor.shutdown(wait=True)
            self.executor = None
    
    def __del__(self):
        """Cleanup on deletion"""
        self.stop()

