# Scaling Study Design

## Study Types

| Type | What Varies | What's Fixed | Measures |
|------|-------------|--------------|----------|
| **Strong Scaling** | N (robots) | λ (total workload) | Speedup for fixed work |
| **Weak Scaling** | N and λ proportionally | λ/N (work per robot) | Efficiency at scale |
| **Capacity Sweep** | Both N and λ (sublinearly) | Target utilization ρ | Sustainable capacity |

## Current Study: Capacity Sweep

We sweep **two variables** simultaneously:
- **N** (number of robots): 50 → 1000
- **λ** (arrival rate): 1.0 → 7.5 tasks/s (sublinear growth)

**Why sublinear λ?** Congestion grows non-linearly with density, reducing μ_eff (per-robot capacity). To maintain stable utilization, we must lower per-robot demand as density increases.

**What it measures:** Maximum sustainable throughput at each scale. The sublinear arrival rate scaling IS the finding - it quantifies how congestion limits capacity growth.

**Limitation:** Hard to isolate whether performance changes come from N or λ.

## Proposed Addition: Strong Scaling Study

Fix λ = 5.0 tasks/s for ALL scales (50-1000 robots).

| Robots | Arrival Rate | λ/N (Demand/Robot) |
|--------|--------------|-------------------|
| 50     | 5.0          | 0.100 (overloaded) |
| 100    | 5.0          | 0.050             |
| 200    | 5.0          | 0.025             |
| 500    | 5.0          | 0.010             |
| 1000   | 5.0          | 0.005 (underloaded) |

**What it measures:** How does adding robots improve performance for fixed demand?

**Expected results:**
- At low N (50-100): System overloaded, high latency, low completion
- At medium N (200-500): Performance improves as capacity exceeds demand
- At high N (800-1000): Congestion overhead may cause diminishing returns

**Key insight:** Isolates the scalability of the coordination architecture (P2P vs Centralized) under identical workload conditions.

## Proposed Addition: Weak Scaling Study

Fix λ/N = 0.015 tasks/robot/s for all scales.

| Robots | Arrival Rate | λ/N (Demand/Robot) |
|--------|--------------|-------------------|
| 50     | 0.75         | 0.015             |
| 100    | 1.5          | 0.015             |
| 200    | 3.0          | 0.015             |
| 500    | 7.5          | 0.015             |
| 1000   | 15.0         | 0.015             |

**What it measures:** Does per-robot efficiency stay constant as we scale?

**Expected results:**
- Ideal: Constant throughput/robot, constant latency
- Reality: Efficiency drops due to congestion overhead at high density

**Key insight:** Quantifies the "coordination tax" - how much efficiency is lost to interference as fleet size grows.

## Recommendation

Run all three studies:
1. **Capacity Sweep** (current): Shows sustainable operating points
2. **Strong Scaling**: Shows speedup for fixed demand
3. **Weak Scaling**: Shows efficiency degradation at scale

Together, these provide a complete picture of system scalability.

