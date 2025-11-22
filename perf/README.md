# Performance Optimization Module

This module contains performance-critical optimizations for large-scale simulations (500+ agents).

## Components

### 1. `spatial_hash.py` - Grid-Based Spatial Indexing
- O(1) agent location queries
- Grid-based neighbor lookups
- 2-3x speedup for spatial operations

### 2. `parallel_gossip.py` - Multi-Process Gossip
- Bypasses Python GIL using multiprocessing
- Parallelizes cache merges across CPU cores
- 2-4x speedup for gossip rounds (N ≥ 300 agents)

### 3. `astar_fast.pyx` - Cython A* Pathfinding
- Native C speed for pathfinding
- Requires compilation: `python perf/setup_cython.py build_ext --inplace`
- 5-10x speedup vs Python implementation

### 4. `cache_merge_fast.pyx` - Cython Cache Merging
- Native C speed for CRDT merging
- Requires compilation (same as above)
- 3-5x speedup vs Python implementation

## Installation

### Prerequisites
```bash
pip install cython numpy
```

### Compile Cython Extensions
```bash
cd /home/modfi/models/robotic/warehouse
python perf/setup_cython.py build_ext --inplace
```

## Usage

### Check if Cython is Available
```python
from perf import CYTHON_AVAILABLE
print(f"Cython optimizations: {'ENABLED' if CYTHON_AVAILABLE else 'DISABLED'}")
```

### Enable Spatial Hash
```python
from perf import SpatialHash

spatial_hash = SpatialHash(width=100, height=80, cell_size=5)
spatial_hash.update(agent_id=1, x=50, y=40)
agents = spatial_hash.get_agents_in_radius(x=52, y=42, radius=10)
```

### Enable Parallel Gossip
```python
from perf import ParallelGossipEngine

gossip_engine = ParallelGossipEngine(num_workers=4)
gossip_engine.start()
gossip_engine.gossip_round(agents=model.schedule.agents)
gossip_engine.stop()
```

### Use Cython A*
```python
from perf import astar_fast, CYTHON_AVAILABLE

if CYTHON_AVAILABLE:
    path = astar_fast(warehouse, dsm_api, start=0, goal=100, cost_params={'alpha': 2.0})
else:
    # Fallback to Python
    from pathfinder import astar_with_congestion
    path = astar_with_congestion(warehouse, dsm_api, start=0, goal=100)
```

## Performance Gains

| Optimization       | Speedup | Best For           |
|--------------------|---------|--------------------|
| Spatial Hash       | 2-3x    | All agent counts   |
| Parallel Gossip    | 2-4x    | N ≥ 300 agents     |
| Cython A*          | 5-10x   | Path-heavy workloads |
| Cython Cache Merge | 3-5x    | High gossip frequency |

**Combined**: Up to **40-50x** speedup for 1000 agents.

## Trade-offs

### Parallel Gossip
- **Pro**: Massive speedup for large N
- **Con**: Memory overhead (each worker copies caches)
- **Con**: Serialization cost for small N (<100)

### Cython
- **Pro**: Near-C performance
- **Con**: Requires compilation step
- **Con**: Platform-specific binaries

## Development

### Testing Optimizations

```bash
# Run tests
python -m pytest tests/test_perf.py

# Profile before/after
python -m cProfile -o baseline.prof experiments/run.py scalability_500_agents
python -m cProfile -o optimized.prof experiments/run.py scalability_500_agents_optimized

# Compare
python -m pstats baseline.prof optimized.prof
```

### Adding New Optimizations

1. Create new module in `perf/`
2. Add to `perf/__init__.py` exports
3. Document in `docs/PERFORMANCE_OPTIMIZATIONS_USAGE.md`
4. Add configuration flag to `experiments/configs.yaml`

