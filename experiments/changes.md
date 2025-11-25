# Experiment Configuration Reorganization

## Changes Made (Nov 24, 2024)

### 1. Config File Reorganization

**Old Structure:**
- Single monolithic `configs.yaml` file (565 lines)

**New Structure:**
- **small.yaml** - 10-100 agents (validation & baseline)
- **medium.yaml** - 200-500 agents (includes new 200-agent configs)
- **large.yaml** - 600-1000 agents (new scales: 600, 700, 800, 900, 1000)

### 2. New Configurations Added

#### Medium Scale (medium.yaml)
- **scalability_200_agents** (new)
- **centralized_200_agents** (new)
- scalability_300_agents
- centralized_300_agents
- scalability_500_agents
- centralized_500_agents

#### Large Scale (large.yaml)
All new paired configs for:
- 600, 700, 800, 900, 1000 agents
- Both distributed (`scalability_X_agents`) and centralized (`centralized_X_agents`)
- Warehouse sizes scaled appropriately
- Gossip workers scaled with agent count

### 3. Code Modularization

**Extracted Modules:**
- **batch_utils.py** - Batch execution logic for running multiple experiments
- **runner_core.py** - Core experiment runner structure (for future refactoring)

**Updated:**
- **run.py** - Now imports batch logic from `batch_utils.py`
  - Reduced complexity
  - Added multi-config file support
  - Added batch modes: `scales`, `paired`, `all`

### 4. Backup Created

**Location:** `experiments/backup/`
- `configs.yaml` - Original monolithic config
- `run.py` - Original run script (before modularization)

### 5. Documentation

**New Files:**
- **QUICK_START.md** - Quick reference guide for running experiments
- **CHANGES.md** - This file, documenting the reorganization

**Updated:**
- README_CONFIGS.md deleted (info moved to QUICK_START.md)

## Migration Guide

### Old Command
```bash
python experiments/run.py -c experiments/configs.yaml -e scalability_500_agents
```

### New Command
```bash
python experiments/run.py -c experiments/medium.yaml -e scalability_500_agents
```

### Batch Mode (New Feature)
```bash
# Run distributed then centralized for 600-1000 agents
python experiments/run.py -c experiments/large.yaml --batch paired

# Run specific range
python experiments/run.py -c experiments/large.yaml --batch paired --scale-range 700 900
```

## Benefits

1. **Clearer Organization**: Configs grouped by scale
2. **Faster Loading**: Load only needed scale range
3. **Better Maintainability**: Smaller files, easier to edit
4. **Batch Support**: Run systematic comparisons easily
5. **Multi-Config Support**: Merge configs as needed

## Backward Compatibility

- Old `configs.yaml` still works (in backup/)
- Can still specify any config file with `-c`
- All experiment names unchanged
- All CLI flags work the same

## Next Steps

To run systematic experiments finding the crossover point:
```bash
# Run paired experiments for 600-1000 agents
python experiments/run.py -c experiments/large.yaml --batch paired
```

This will run distributed and centralized for each scale sequentially, allowing direct comparison.

