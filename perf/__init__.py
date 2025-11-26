"""
Performance optimization utilities.
"""

from .spatial_hash import SpatialHash
from .parallel_gossip import ParallelGossipEngine
from .parallel_scheduler import ParallelScheduler

try:
    from .astar_fast import astar_fast
    from .cache_merge_fast import merge_bidirectional_fast
    CYTHON_AVAILABLE = True
except ImportError:
    CYTHON_AVAILABLE = False
    astar_fast = None
    merge_bidirectional_fast = None

__all__ = ['SpatialHash', 'ParallelGossipEngine', 'ParallelScheduler', 'astar_fast', 'merge_bidirectional_fast', 'CYTHON_AVAILABLE']

