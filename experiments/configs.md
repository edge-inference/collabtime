# Experiment Configuration Guide

## Configuration Files Structure

Configs are now organized by scale for better manageability:

### **configs_small.yaml**
- **10-100 agents**: Validation and baseline tests
- Experiments: `baseline_10_agents`, `scalability_20_agents`, `scalability_50_agents`, `scalability_100_agents`, `centralized_100_agents`
- Use for: Quick validation, baseline comparison

### **configs_medium.yaml**
- **300-500 agents**: Coordination overhead vs centralized bottleneck
- Experiments: `scalability_300_agents`, `centralized_300_agents`, `scalability_500_agents`, `centralized_500_agents`
- Use for: Moderate scale comparison, architecture trade-offs

### **configs_large.yaml**
- **600-1000 agents**: Finding the crossover point
- Experiments: `scalability_X_agents` and `centralized_X_agents` for X in {600, 700, 800, 900, 1000}
- Use for: Determining where distributed overtakes centralized

### **configs.yaml** (Legacy)
- Original monolithic config file
- Still supported for backward compatibility
- Consider migrating to new structure

## Running Experiments

### Single Experiment
```bash
# Run a specific experiment from a config file
python experiments/run.py -c experiments/configs_large.yaml -e scalability_600_agents

# Run with multiple config files (they will be merged)
python experiments/run.py -c experiments/configs_medium.yaml experiments/configs_large.yaml -e scalability_500_agents
```

### Batch Mode

#### **Scales Mode** (Distributed only)
Runs distributed experiments for each scale:
```bash
# Run all large-scale distributed experiments (600-1000)
python experiments/run.py -c experiments/configs_large.yaml --batch scales

# Run specific range (e.g., 700-900)
python experiments/run.py -c experiments/configs_large.yaml --batch scales --scale-range 700 900
```

Output: `scalability_600_agents`, `scalability_700_agents`, ..., `scalability_1000_agents`

#### **Paired Mode** (Both architectures per scale)
Runs distributed then centralized for each scale sequentially:
```bash
# Run paired comparisons for 600-1000 agents
python experiments/run.py -c experiments/configs_large.yaml --batch paired

# Run specific range
python experiments/run.py -c experiments/configs_large.yaml --batch paired --scale-range 600 800
```

Output: 
- `scalability_600_agents` → `centralized_600_agents`
- `scalability_700_agents` → `centralized_700_agents`
- ...

#### **All Mode** (Everything)
Same as `paired`, runs all available experiments:
```bash
python experiments/run.py -c experiments/configs_large.yaml --batch all
```

### Load Multiple Config Files
```bash
# Merge small, medium, and large configs
python experiments/run.py -c experiments/configs_small.yaml experiments/configs_medium.yaml experiments/configs_large.yaml --batch all
```

## Configuration Parameters

### Common Settings
All configs use these optimizations:
- `use_cython: true` - Cython-accelerated A* (mandatory)
- `use_spatial_hash: true` - Spatial indexing for fast lookups
- `parallel_gossip: true` - Zero-copy parallel gossip (distributed only)

### Scale-Dependent Parameters

| Agents | Warehouse Size | Task Rate | Gossip Workers | Storage Radius | Sortation Radius |
|--------|---------------|-----------|----------------|----------------|------------------|
| 10     | 20×15         | 0.1       | 4              | 3              | 1                |
| 20     | 25×20         | 0.25      | 4              | 4              | 2                |
| 50     | 40×30         | 1.0       | 6              | 6              | 3                |
| 100    | 60×50         | 2.5       | 12             | 10             | 5                |
| 300    | 80×65         | 4.0       | 16             | 13             | 6                |
| 500    | 95×80         | 5.0       | 24             | 16             | 7                |
| 600    | 105×85        | 5.5       | 28             | 17             | 8                |
| 700    | 110×90        | 6.0       | 32             | 18             | 8                |
| 800    | 115×95        | 6.5       | 36             | 19             | 9                |
| 900    | 118×98        | 7.0       | 40             | 20             | 9                |
| 1000   | 120×100       | 7.5       | 48             | 20             | 10               |

### Scaling Rationale

1. **Warehouse Size**: Scales roughly with √(agent_count) to maintain density
2. **Task Arrival Rate**: Scaled to keep agents ~40% utilized
3. **Gossip Workers**: Scales with agent count, capped at reasonable thread pool size
4. **Storage/Sortation Regions**: Scale with warehouse size to maintain spatial distribution

## Expected Results

### Small Scale (≤100 agents)
- Both architectures perform well
- Centralized faster in wall-clock time
- Minimal coordination overhead

### Medium Scale (300-500 agents)
- **Generation B (Old)**: Distributed had ~4% better completion rate
- **Generation A (Optimized)**: Both architectures nearly equal
- Centralized still faster in wall-clock (~2-3x)

### Large Scale (600-1000 agents)
- **Expected**: Distributed should overtake centralized
- **Reason**: Central scheduler saturates, becomes bottleneck
- **Goal**: Find the exact crossover point

## Batch Experiment Workflow

### Finding the Crossover Point
```bash
# Step 1: Run paired experiments 600-1000
python experiments/run.py -c experiments/configs_large.yaml --batch paired

# Step 2: Analyze results
python experiments/analyze_crossover.py

# Step 3: If needed, refine range (e.g., 700-800 in steps of 50)
# (requires adding configs for 750_agents)
```

### Quick Validation
```bash
# Run small scale to verify setup
python experiments/run.py -c experiments/configs_small.yaml -e baseline_10_agents
```

### Full Sweep
```bash
# Run everything from 100 to 1000 agents
python experiments/run.py \
  -c experiments/configs_small.yaml \
     experiments/configs_medium.yaml \
     experiments/configs_large.yaml \
  --batch all \
  --scale-range 100 1000
```

## Tips

1. **Use batch mode for systematic comparisons**: Ensures consistent execution order
2. **Paired mode for fair comparison**: Runs distributed then centralized back-to-back
3. **Monitor resource usage**: Large scales (≥800) may stress system resources
4. **Check SHM cleanup**: Ensure no leaked shared memory between runs (`ipcs -m`)
5. **LF coordinator**: Always use `--lf` for reproducible results (default)

## Output Structure

Results are organized by run ID and mode:
```
results/
  runXXX/
    run_metadata.json
    distributed/
      experiment_details_YYYYMMDD_HHMMSS.json
      system_perf_EXPNAME_YYYYMMDD_HHMMSS.png
      dashboard_report_EXPNAME_YYYYMMDD_HHMMSS.png
    centralized/
      experiment_details_YYYYMMDD_HHMMSS.json
      system_perf_EXPNAME_YYYYMMDD_HHMMSS.png
      dashboard_report_EXPNAME_YYYYMMDD_HHMMSS.png
```

## Migrating from Old configs.yaml

If you have custom experiments in `configs.yaml`:
1. Identify the agent count/scale
2. Add to appropriate file (`small`, `medium`, or `large`)
3. Ensure all optimization flags are set (`use_cython`, `use_spatial_hash`, `parallel_gossip`)
4. Update `gossip_workers` based on agent count (see table above)

