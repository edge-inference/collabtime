# Simulation Scaling Parameters (50-1000 Agents)

## Configuration Scaling Table

| Agents | Warehouse Size | Total Cells | Cells/Agent | Arrival Rate (tasks/s) | Tasks/Agent/s | Gossip Interval (steps) | Gossip Workers (P2P) | Centralized Replicas | AoI Threshold (ms) | Duration (s) |
|--------|----------------|-------------|-------------|------------------------|---------------|-------------------------|----------------------|----------------------|--------------------|--------------|
| 50     | 40 × 30        | 1,200       | 24.0        | 1.0                    | 0.020         | 3                       | 6                    | 10                   | 1000               | 900          |
| 100    | 55 × 40        | 2,200       | 22.0        | 2.0                    | 0.020         | 3                       | 10                   | 10                   | 1000               | 900          |
| 200    | 70 × 55        | 3,850       | 19.3        | 3.0                    | 0.015         | 3                       | 14                   | 10                   | 1000               | 900          |
| 300    | 80 × 65        | 5,200       | 17.3        | 4.0                    | 0.013         | 4                       | 16                   | 10                   | 1000               | 900          |
| 500    | 95 × 80        | 7,600       | 15.2        | 5.0                    | 0.010         | 4                       | 24                   | 10                   | 1000               | 900          |
| 600    | 105 × 85       | 8,925       | 14.9        | 5.5                    | 0.009         | 4                       | 8                    | 10                   | 1000               | 900          |
| 700    | 110 × 90       | 9,900       | 14.1        | 6.0                    | 0.009         | 4                       | 8                    | 10                   | 1000               | 900          |
| 800    | 115 × 95       | 10,925      | 13.7        | 6.5                    | 0.008         | 4                       | 10                   | 10                   | 1000               | 900          |
| 900    | 118 × 98       | 11,564      | 12.8        | 7.0                    | 0.008         | 4                       | 10                   | 10                   | 1000               | 900          |
| 1000   | 120 × 100      | 12,000      | 12.0        | 7.5                    | 0.008         | 4                       | 12                   | 10                   | 1000               | 900          |

## Storage & Sortation Regions

**Rectangular zones (Amazon-style layout):**
- **Storage Zone**: Left half of warehouse (x < width/2)
- **Sortation Zone**: Right half of warehouse (x >= width/2)
- **Coverage**: ~100% of shelf space (vs. old circular 25%)

| Agents | Warehouse | Storage Zone | Sortation Zone | Coverage |
|--------|-----------|--------------|----------------|----------|
| 50     | 40 × 30   | Left 20 cols | Right 20 cols  | 100%     |
| 100    | 55 × 40   | Left 27 cols | Right 28 cols  | 100%     |
| 200    | 70 × 55   | Left 35 cols | Right 35 cols  | 100%     |
| 300    | 80 × 65   | Left 40 cols | Right 40 cols  | 100%     |
| 500    | 95 × 80   | Left 47 cols | Right 48 cols  | 100%     |
| 600    | 105 × 85  | Left 52 cols | Right 53 cols  | 100%     |
| 700    | 110 × 90  | Left 55 cols | Right 55 cols  | 100%     |
| 800    | 115 × 95  | Left 57 cols | Right 58 cols  | 100%     |
| 900    | 118 × 98  | Left 59 cols | Right 59 cols  | 100%     |
| 1000   | 120 × 100 | Left 60 cols | Right 60 cols  | 100%     |

## Fixed Physical Constants (from config.py)

| Parameter                  | Value        | Description                                    |
|----------------------------|--------------|------------------------------------------------|
| Step Duration              | 100 ms       | Simulation step interval (LF tick)             |
| Cell Size                  | 1.0 m        | Physical dimension of each grid cell           |
| Robot Velocity             | 0.5 m/s      | Forward movement speed                         |
| Lateral Velocity           | 0.5 m/s      | Lateral escape movement speed                  |
| Movement Duration          | 2.0 s        | Time to traverse one cell (20 steps)           |
| Task Work Duration         | 45.0 s       | Time to complete task at location (450 steps)  |
| Stuck Timeout              | 60 steps     | Steps before agent declares itself stuck       |
| Aisle Capacity             | 1 agent/cell | Maximum agents per corridor cell               |
| Work Station Capacity      | 1 agent/cell | Maximum agents per work station                |

## Scaling Design Notes

### Warehouse Scaling
- **Area Growth**: Warehouse size scales approximately as √(agents) to maintain reasonable density
- **Cells/Agent**: Decreases from 24.0 (50 agents) to 12.0 (1000 agents) as density increases
- **Storage/Sortation**: Rectangular zones (left/right halves) providing 100% shelf coverage
- **Layout**: Amazon-style grid with aisles, staging perimeter, and middle separator

### Task Load Scaling
- **Arrival Rate**: Increases sub-linearly with agent count (1.0 → 7.5 tasks/s for 50 → 1000 agents)
- **Tasks/Agent/s**: Decreases from 0.020 to 0.008 as agent count grows (conservative to avoid saturation)
- **Target Utilization**: Designed for ~75% agent utilization under distributed mode

### Coordination Scaling
- **Gossip Interval**: Fixed at 3-4 steps (300-400ms) for all scales
- **Gossip Workers**: Scales from 6 to 24 workers for P2P gossip parallelization
- **Centralized Replicas**: Fixed at 10 service replicas (realistic production deployment)
- **AoI Threshold**: Fixed at 1000ms (data freshness requirement)

### Performance Optimizations
- **Spatial Hash**: Enabled for all scales (O(1) neighbor lookup)
- **Parallel Gossip**: Enabled for all scales (multiprocess gossip merges)
- **Parallel Agents**: Enabled for distributed mode (concurrent agent execution)
- **Cython A***: Mandatory for both modes (100x speedup vs Python)

## Expected Crossover Point

The configuration is designed to identify where **distributed P2P overtakes centralized**:

- **50-300 agents**: Centralized expected to win (perfect coordination, low contention)
- **500-700 agents**: Crossover zone (centralized bottleneck vs P2P staleness trade-off)
- **800-1000 agents**: Distributed expected to win (centralized replica pool saturated)

The centralized scheduler with 10 replicas can theoretically handle ~10 concurrent path requests. When agent count >> 10, queueing delays should accumulate, favoring distributed parallel pathfinding.

## Why Sublinear Arrival Rate Scaling?

Congestion grows **non-linearly** with density:

```
Congestion
(Wait Time)
     ^
     |                      /
     |                    /
     |                  /
     |               __/
     |          ___/
     |     ___/
     |____/
     +----------------------------> Density (Robots/Cell)
        Low    Medium    High
```

### The Two Metrics

| Metric | Symbol | Meaning |
|--------|--------|---------|
| Tasks/Robot/s | λ/N | **Demand** - tasks assigned per robot per second |
| μ_eff | 1/E[T_travel + T_node] | **Capacity** - tasks a robot can complete per second |

Utilization: ρ = Demand / Capacity = (Tasks/Robot/s) / μ_eff

### Why Tasks/Robot/s Must Drop

μ_eff is **not constant** - it decreases as density increases due to congestion.

Think of it like traffic:
- At 10% road capacity: Everyone flows freely, minimal delay
- At 50% capacity: Some slowdowns, moderate delay
- At 90% capacity: Traffic jams, delays **explode**

| Robots | Density (1/Cells) | Congestion | μ_eff | Tasks/Robot/s |
|--------|-------------------|------------|-------|---------------|
| 50     | 0.042 (low)       | Minimal    | High  | 0.020         |
| 100    | 0.045             | Low        | High  | 0.020         |
| 200    | 0.052             | Low        | Med-High | 0.015      |
| 500    | 0.066             | Medium     | Medium | 0.010        |
| 1000   | 0.083 (high)      | High       | Low   | 0.0075        |

**The Chain:**
1. More robots → Higher density → More blocking
2. More blocking → T_travel increases (waiting for paths)
3. Higher T_travel → μ_eff = 1/(T_travel + T_node) **drops**
4. To keep ρ stable → Must lower Tasks/Robot/s to match lower μ_eff

Congestion grows super-linearly with density (like O(d²) near saturation), so Tasks/Robot/s must follow the same non-linear curve downward.
