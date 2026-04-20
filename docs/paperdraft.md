
### Centralized 

In the paper, acknowledge:
"We model centralized as optimistic case: perfect data consistency"
"Real replicated systems would incur replication lag or consensus overhead"
"Even in this optimistic scenario, distributed P2P shows advantages"
Should we add replication overhead for realism, or keep the optimistic (unfair-to-distributed) centralized model?


### Warehouse graph: semantic driven

Semantics: Lost (just occupancy, no storage/corridor/sortation labels)  

```bash 
nodes = {
    42: (x, y, 'storage_A'),     # Shelf location
    43: (x, y, 'corridor'),      # Walkway
    51: (x, y, 'sortation_B'),   # Drop-off zone
    60: (x, y, 'charging'),      # Charging station
}

# Your DSM layers attach to these semantics:
jam_signal[42] = 1.0      # Storage A is congested
flow_trace[43] = 0.5      # Corridor has traffic
path_intent[51] = agent_3 # Agent 3 heading to sortation B
```
