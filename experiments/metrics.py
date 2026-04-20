"""
Metrics collection for experiments
"""
import time
import numpy as np
import pandas as pd
from typing import Dict, List
from world.model import WarehouseDSMModel


def collect_step_metrics(model: WarehouseDSMModel, step: int) -> Dict:
    """Collect metrics for a single simulation step."""
    current_time_ms = int(model.step_count * model.step_duration_s * 1000)
    cache_stats_per_agent = []
    for agent in model.schedule.agents:
        try:
            if agent.local_cache:
                stats = agent.local_cache.get_stats(current_time_ms)
                cache_stats_per_agent.append(stats)
            else:
                cache_stats_per_agent.append({})
        except Exception as e:
            if model.logger:
                model.logger.warning(f"Failed to get cache stats from agent {agent.unique_id}: {e}")
            cache_stats_per_agent.append({})
    
    if model.mode == 'centralized' and model.central_scheduler:
        try:
            # Use comparable get_stats() method for fair comparison with distributed
            central_stats = model.central_scheduler.get_stats()
            total_cache_entries = sum(central_stats.values())
            total_jam_entries = central_stats.get('jam_entries', 0)
            
            if step % 100 == 0 and model.logger:
                stuck_agents = sum(1 for a in model.schedule.agents if a.stuck_counter > 0)
                max_stuck = max((a.stuck_counter for a in model.schedule.agents), default=0)
                model.logger.debug(f"Step {step}: Central scheduler stats: {central_stats}. Stuck: {stuck_agents} (Max: {max_stuck})")
        except Exception as e:
            if model.logger:
                model.logger.warning(f"Failed to read central scheduler data: {e}")
            total_cache_entries = 0
            total_jam_entries = 0
    else:
        total_cache_entries = sum(
            stats.get('flow_entries', 0) + stats.get('jam_entries', 0) + 
            stats.get('agent_locations', 0) + stats.get('path_intents', 0) + 
            stats.get('resource_states', 0)
            for stats in cache_stats_per_agent
        )
        total_jam_entries = sum(stats.get('jam_entries', 0) for stats in cache_stats_per_agent)
    
    unique_jams = {}
    if model.mode == 'centralized' and model.central_scheduler:
        try:
            # Thread-safe copy if possible, or just iterate (assuming lock handled inside scheduler or accepting risk)
            # Better: access via a method or property that returns a copy, but direct access is what we have.
            # We can try to acquire the lock if it exists
            if hasattr(model.central_scheduler, 'data_lock'):
                 with model.central_scheduler.data_lock:
                    jam_items = list(model.central_scheduler.jam_data.items())
            else:
                 jam_items = list(model.central_scheduler.jam_data.items())

            for node_id, jam_value in jam_items:
                if jam_value > 0.01:
                    unique_jams[node_id] = {'value': jam_value, 'timestamp': current_time_ms}
        except Exception as e:
            if model.logger:
                model.logger.warning(f"Failed to collect jam data from central scheduler: {e}")
    else:
        aoi_threshold_ms = model.aoi_threshold_ms
        for agent in model.schedule.agents:
            if not agent.local_cache:
                continue
            try:
                jam_vals = np.asarray(agent.local_cache.jam_values)
                jam_ts = np.asarray(agent.local_cache.jam_timestamps)
                
                valid_mask = (current_time_ms - jam_ts) <= aoi_threshold_ms
                nonzero_mask = jam_vals > 0.01
                combined_mask = valid_mask & nonzero_mask
                
                for node_id in np.where(combined_mask)[0]:
                    timestamp = int(jam_ts[node_id])
                    jam_value = float(jam_vals[node_id])
                    if node_id not in unique_jams or jam_value > unique_jams[node_id]['value']:
                        unique_jams[node_id] = {'value': jam_value, 'timestamp': timestamp}
            except Exception as e:
                if model.logger:
                    model.logger.warning(f"Failed to read jam data from agent {agent.unique_id}: {e}")
                continue
    
    num_jammed_nodes = len(unique_jams)
    total_jam = sum(j['value'] for j in unique_jams.values())
    avg_jam_intensity = total_jam / num_jammed_nodes if num_jammed_nodes > 0 else 0.0
    
    agent_states = [agent.state for agent in model.schedule.agents]
    working_count = sum(1 for state in agent_states if state.value == 'working')
    navigating_count = sum(1 for state in agent_states if state.value == 'navigating')
    utilization_working = working_count / len(agent_states) if agent_states else 0.0
    utilization_active = (working_count + navigating_count) / len(agent_states) if agent_states else 0.0
    
    stuck_counters = [agent.stuck_counter for agent in model.schedule.agents]
    num_stuck = sum(1 for sc in stuck_counters if sc > 0)
    avg_stuck = sum(stuck_counters) / len(stuck_counters) if stuck_counters else 0.0
    max_stuck = max(stuck_counters) if stuck_counters else 0
    
    stalls_in_transit = 0
    stalls_at_resource = 0
    stalls_idle = 0
    
    for agent in model.schedule.agents:
        if agent.stuck_counter > 0:
            if agent.state.value == 'navigating':
                if agent.task_location is not None and agent.node == agent.task_location:
                    stalls_at_resource += 1
                else:
                    stalls_in_transit += 1
            elif agent.state.value == 'idle':
                stalls_idle += 1
    
    return {
        'step': step,
        'timestamp': time.time(),
        'tasks_created': model.task_counter,
        'tasks_completed': len([t for t in model.completed_tasks]),
        'tasks_active': len([t for t in model.active_tasks]),
        'agent_states': agent_states,
        'cache_entries': total_cache_entries,
        'jam_entries': total_jam_entries,
        'num_jammed_nodes': num_jammed_nodes,
        'jam_intensity_avg': avg_jam_intensity,
        'gossip_rounds': step // 3,
        'utilization_working': utilization_working,
        'utilization_active': utilization_active,
        'num_stuck_agents': num_stuck,
        'avg_stuck_counter': avg_stuck,
        'max_stuck_counter': max_stuck,
        'stalls_in_transit': stalls_in_transit,
        'stalls_at_resource': stalls_at_resource,
        'stalls_idle': stalls_idle
    }


def collect_final_metrics(model: WarehouseDSMModel, step_data: List[Dict], sim_duration_s: float, step_interval_ms: int) -> Dict:
    """Collect and aggregate final experiment metrics."""
    df = pd.DataFrame(step_data)
    
    total_tasks = model.task_counter
    
    completion_times = []
    for t in model.completed_tasks:
        if isinstance(t, dict) and 'completion_time' in t and 'start_time' in t:
            if t['completion_time'] and t['start_time']:
                completion_times.append(t['completion_time'] - t['start_time'])
    latencies_s = completion_times
    p50 = float(np.percentile(latencies_s, 50)) if latencies_s else 0.0
    p90 = float(np.percentile(latencies_s, 90)) if latencies_s else 0.0
    p99 = float(np.percentile(latencies_s, 99)) if latencies_s else 0.0
    throughput_tps = (len(model.completed_tasks) / sim_duration_s) if sim_duration_s > 0 else 0.0
    
    tasks_claimed = sum(agent.metrics['tasks_claimed'] for agent in model.schedule.agents)
    
    performance_metrics = {
        'tasks_completed': len(model.completed_tasks),
        'tasks_failed': len(model.failed_tasks),
        'tasks_claimed': tasks_claimed,
        'completion_rate': len(model.completed_tasks) / total_tasks if total_tasks > 0 else 0,
        'claimed_completion_rate': len(model.completed_tasks) / tasks_claimed if tasks_claimed > 0 else 0,
        'average_completion_time': np.mean(latencies_s) if latencies_s else 0,
        'latency_p50': p50,
        'latency_p90': p90,
        'latency_p99': p99,
        'throughput_tps': throughput_tps,
        'sim_duration_s': float(sim_duration_s),
        'step_interval_ms': int(step_interval_ms),
        'total_distance_traveled': sum(agent.total_distance for agent in model.schedule.agents),
        'agent_utilization': np.mean([agent.utilization for agent in model.schedule.agents])
    }
    
    num_agents = len(model.schedule.agents)
    
    if model.mode == 'centralized':
        # Use get_stats() for comparable measurement with distributed
        if model.central_scheduler:
            central_stats = model.central_scheduler.get_stats()
            avg_cache_size = sum(central_stats.values())
            total_scheduler_requests = (model.central_scheduler.metrics['total_requests'] + 
                                        model.central_scheduler.metrics['total_task_assignments'])
        else:
            avg_cache_size = 0
            total_scheduler_requests = 0
        total_gossip_rounds = 0
        total_peer_exchanges = 0
        comm_operations = total_scheduler_requests
    else:
        current_time_ms = int(model.step_count * model.step_duration_s * 1000)
        avg_cache_size = np.mean([
            sum(agent.local_cache.get_stats(current_time_ms).values()) if agent.local_cache else 0
            for agent in model.schedule.agents
        ])
        total_gossip_rounds = df['gossip_rounds'].max() if 'gossip_rounds' in df else 0
        
        # Compute actual peer exchanges: each round pairs N/2 agents for bidirectional merge
        if hasattr(model, 'gossip_engine') and model.gossip_engine:
            total_peer_exchanges = model.gossip_engine.total_merges
        else:
            total_peer_exchanges = total_gossip_rounds * (num_agents // 2)
        
        total_scheduler_requests = 0
        comm_operations = total_peer_exchanges
    
    tasks_completed = len(model.completed_tasks)
    comms_per_task = comm_operations / tasks_completed if tasks_completed > 0 else 0.0
    
    coordination_metrics = {
        'avg_cache_size': float(avg_cache_size),
        'total_gossip_rounds': int(total_gossip_rounds),
        'total_peer_exchanges': int(total_peer_exchanges),
        'total_scheduler_requests': int(total_scheduler_requests),
        'comm_operations': int(comm_operations),
        'comms_per_task': float(comms_per_task),
        'tasks_in_registry': len(model.coordinator.task_registry.tasks),
        'active_leases': len([l for l in model.coordinator.lease_manager.leases.values() if l]),
        'coordination_mode': model.mode
    }
    
    time_series = {
        'tasks_created_timeline': df['tasks_created'].tolist(),
        'task_completion_timeline': df['tasks_completed'].tolist(),
        'tasks_active_timeline': df['tasks_active'].tolist(),
        'cache_entries_timeline': df.get('cache_entries', []).tolist() if 'cache_entries' in df else [],
        'jam_entries_timeline': df.get('jam_entries', []).tolist() if 'jam_entries' in df else [],
        'num_jammed_nodes_timeline': df.get('num_jammed_nodes', []).tolist() if 'num_jammed_nodes' in df else [],
        'jam_intensity_avg_timeline': df.get('jam_intensity_avg', []).tolist() if 'jam_intensity_avg' in df else [],
        'utilization_working_timeline': df.get('utilization_working', []).tolist() if 'utilization_working' in df else [],
        'utilization_active_timeline': df.get('utilization_active', []).tolist() if 'utilization_active' in df else [],
        'num_stuck_agents_timeline': df.get('num_stuck_agents', []).tolist() if 'num_stuck_agents' in df else [],
        'avg_stuck_counter_timeline': df.get('avg_stuck_counter', []).tolist() if 'avg_stuck_counter' in df else [],
        'max_stuck_counter_timeline': df.get('max_stuck_counter', []).tolist() if 'max_stuck_counter' in df else [],
        'stalls_in_transit_timeline': df.get('stalls_in_transit', []).tolist() if 'stalls_in_transit' in df else [],
        'stalls_at_resource_timeline': df.get('stalls_at_resource', []).tolist() if 'stalls_at_resource' in df else [],
        'stalls_idle_timeline': df.get('stalls_idle', []).tolist() if 'stalls_idle' in df else [],
        'steps': df['step'].tolist(),
        'latency_samples_s': latencies_s
    }
    
    return {
        'performance': performance_metrics,
        'coordination': coordination_metrics,
        'time_series': time_series
    }

