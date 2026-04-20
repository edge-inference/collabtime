# Centralized Architecture Model

## What We Actually Implemented

**Architecture Pattern:** Shared Database + Connection Pool

```
Agent Requests → Semaphore (N slots) → Single Shared Database
                      ↓
                N worker threads
           (concurrent access to same data)
```

## Configuration

```yaml
centralized_replicas: 10  # Connection pool size (default)
```

## What This Models

### Optimistic Centralized System:
- ✅ Perfect data consistency (no replication lag)
- ✅ Instant updates (no consensus overhead)
- ✅ Zero network latency (co-located)
- ✅ Same algorithms as distributed (fair comparison)
- ⚠️ Thread pool limits concurrency (natural bottleneck)

### What Real Systems Would Add:
- ❌ Network latency: 1-5ms per request
- ❌ Database replication lag: 10-100ms (eventual consistency)
- ❌ Consensus overhead: 5-20ms (strong consistency)
- ❌ Connection pool exhaustion under high load

## Why This is Fair

**This model is OPTIMISTIC for centralized** (favors centralized over distributed):
- No replication overhead
- No network latency
- Perfect consistency
- Only bottleneck: thread pool contention

**Any performance gap favoring distributed is pure architectural advantage:**
- Local cache reads (zero coordination)
- P2P gossip (no central bottleneck)
- Parallel agent execution

## Metrics We Track

```python
{
    'num_replicas': 10,                    # Connection pool size
    'peak_concurrent_requests': 847,       # Max observed concurrency
    'requests_queued': 12453,              # How many had to wait
    'total_replica_wait_time_s': 45.2,     # Time spent waiting for slot
    'avg_replica_wait_time_ms': 3.63,      # Average wait per queued request
    'replica_utilization': 0.847           # peak / num_replicas
}
```

## Comparison to Real Systems

| Aspect | Our Model | Real Centralized | Real Distributed |
|--------|-----------|------------------|------------------|
| **Consistency** | Perfect | Eventual/Strong | Eventual (gossip) |
| **Latency** | 0ms (thread pool) | 1-5ms (network) | 0ms (local cache) |
| **Replication** | None (shared DB) | Async/Raft | P2P gossip |
| **Bottleneck** | Thread pool (N=10) | DB + Network | Gossip bandwidth |
| **Scalability** | O(agents/N) | O(agents/N) | O(1) per agent |

## For Publication

**Key Statement:**
> "We model centralized coordination optimistically: zero network latency, perfect consistency, and no replication overhead. Performance differences emerge purely from architectural patterns - shared-state serialization vs peer-to-peer coordination. Real deployments would incur additional centralized overhead (1-5ms network RTT, database replication lag, consensus protocols), further favoring distributed approaches."

## Implementation Details

- **Pattern**: `threading.Semaphore(num_replicas)`
- **Data Structures**: Shared Python dicts (in-memory)
- **Algorithms**: Same Cython A* as distributed
- **No Artificial Delays**: Pure computational comparison


