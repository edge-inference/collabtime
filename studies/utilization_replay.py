#!/usr/bin/env python3
"""Run paired warehouse state-occupancy experiments with replayed task streams."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
from pathlib import Path
import random
import time
from typing import Iterable, Sequence

import numpy as np
import yaml

from config import TASK_WORK_DURATION_S
from experiments.metrics import collect_final_metrics, collect_step_metrics
from studies.task_stream import TaskEvent, generate_task_stream, task_stream_digest, write_task_stream
from world.graph import WarehouseGraph
from world.model import WarehouseDSMModel


ROOT = Path(__file__).resolve().parent.parent

CONFIG_PAIRS = {
    50: ("small.yaml", "dist_50_agents", "cent_50_agents"),
    100: ("small.yaml", "dist_100_agents", "cent_100_agents"),
    200: ("medium.yaml", "scalability_200_agents", "centralized_200_agents"),
    300: ("medium.yaml", "scalability_300_agents", "centralized_300_agents"),
    500: ("medium.yaml", "scalability_500_agents", "centralized_500_agents"),
    600: ("large.yaml", "scalability_600_agents", "centralized_600_agents"),
    700: ("large.yaml", "scalability_700_agents", "centralized_700_agents"),
    800: ("large.yaml", "scalability_800_agents", "centralized_800_agents"),
}


def _json_default(value):
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _mean(values: Sequence[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def _parse_int_list(value: str) -> list[int]:
    return [int(token.strip()) for token in value.split(",") if token.strip()]


def _load_pair(fleet_size: int) -> tuple[dict, dict]:
    if fleet_size not in CONFIG_PAIRS:
        raise ValueError(f"no configuration pair for fleet size {fleet_size}")
    filename, distributed_name, centralized_name = CONFIG_PAIRS[fleet_size]
    path = ROOT / "experiments" / "configs" / filename
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    configs = payload["experiments"]
    distributed = configs[distributed_name]
    centralized = configs[centralized_name]

    comparable_fields = (
        ("warehouse", "size"),
        ("agents", "count"),
        ("tasks", "arrival_rate"),
        ("simulation", "duration"),
        ("simulation", "step_interval"),
    )
    for section, key in comparable_fields:
        if distributed[section][key] != centralized[section][key]:
            raise ValueError(
                f"configuration mismatch at N={fleet_size}: {section}.{key}"
            )
    return distributed, centralized


def _build_warehouse(config: dict, layout_seed: int) -> WarehouseGraph:
    random.seed(layout_seed)
    width, height = config["warehouse"]["size"]
    return WarehouseGraph(width=width, height=height)


def _layout_digest(warehouse: WarehouseGraph) -> str:
    payload = [
        (int(node), warehouse.node_types[node], int(warehouse.capacities[node]))
        for node in sorted(warehouse.node_types)
    ]
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _candidate_nodes(warehouse: WarehouseGraph) -> list[int]:
    return sorted(
        node
        for node, node_type in warehouse.node_types.items()
        if node_type in {"pick_location", "pack_station"}
    )


def _initial_positions(warehouse: WarehouseGraph, count: int, seed: int) -> list[int]:
    valid_nodes = sorted(
        node
        for node in warehouse.graph.nodes()
        if warehouse.node_types.get(node) in {"staging", "aisle", "buffer"}
        and warehouse.capacities.get(node, 0) > 0
        and warehouse.graph.degree[node] > 0
    )
    if not valid_nodes:
        raise ValueError("warehouse has no valid initial positions")
    rng = np.random.default_rng(seed)
    return [int(node) for node in rng.choice(valid_nodes, size=count, replace=True)]


class ReplayWarehouseModel(WarehouseDSMModel):
    """Warehouse model whose arrivals are supplied by an external trace."""

    def __init__(self, *args, task_stream: Sequence[TaskEvent], **kwargs):
        self._task_stream = tuple(task_stream)
        self._task_stream_index = 0
        self.replayed_events: list[TaskEvent] = []
        super().__init__(*args, **kwargs)

    def _generate_tasks(self) -> None:
        sim_time_s = self.step_count * self.step_duration_s
        while self._task_stream_index < len(self._task_stream):
            event = self._task_stream[self._task_stream_index]
            if event.arrival_time_s > sim_time_s + 1e-12:
                break
            self._create_replayed_task(event, sim_time_s)
            self._task_stream_index += 1

    def _create_replayed_task(self, event: TaskEvent, admitted_time_s: float) -> None:
        task_id = self.coordinator.create_task(event.location)
        self.active_tasks[task_id] = {
            "location": event.location,
            "created_step": self.step_count,
            "created_time": admitted_time_s,
            "start_time": admitted_time_s,
            "scheduled_arrival_time": event.arrival_time_s,
            "stream_sequence": event.sequence,
        }
        self.task_counter += 1
        self.replayed_events.append(event)


def _state_fractions(step_data: Sequence[dict], min_time_s: float, step_duration_s: float) -> dict:
    rows = [row for row in step_data if row["step"] * step_duration_s >= min_time_s]
    working = _mean([float(row["utilization_working"]) for row in rows])
    active = _mean([float(row["utilization_active"]) for row in rows])
    navigating = active - working
    idle = 1.0 - active
    stuck = _mean([float(row["num_stuck_agents"]) for row in rows])
    return {
        "working_fraction": working,
        "navigating_fraction": navigating,
        "idle_fraction": idle,
        "active_fraction": active,
        "mean_stuck_agents": stuck,
        "sample_count": len(rows),
    }


def _run_mode(
    fleet_size: int,
    mode_name: str,
    config: dict,
    events: Sequence[TaskEvent],
    expected_layout_digest: str,
    initial_positions: Sequence[int],
    run_seed: int,
    layout_seed: int,
    duration_s: float,
    warmup_s: float,
    sample_every_steps: int,
) -> dict:
    warehouse = _build_warehouse(config, layout_seed)
    actual_layout_digest = _layout_digest(warehouse)
    if actual_layout_digest != expected_layout_digest:
        raise RuntimeError("paired run did not reproduce the warehouse layout")

    step_interval_ms = int(config["simulation"]["step_interval"])
    step_duration_s = step_interval_ms / 1000.0
    total_steps = int(duration_s / step_duration_s)
    simulation = config["simulation"]
    logger = logging.getLogger(f"utilization-study.{fleet_size}.{run_seed}.{mode_name}")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.ERROR)

    model = None
    started = time.monotonic()
    try:
        model = ReplayWarehouseModel(
            n_agents=fleet_size,
            warehouse_graph=warehouse,
            agent_positions=list(initial_positions),
            task_arrival_rate=float(config["tasks"]["arrival_rate"]),
            task_types=config["tasks"]["types"],
            task_priorities=config["tasks"]["priorities"],
            step_duration_s=step_duration_s,
            aoi_threshold_ms=int(config.get("coordination", {}).get("aoi_threshold", 1000)),
            mode="p2p" if mode_name == "distributed" else "centralized",
            use_spatial_hash=bool(simulation.get("use_spatial_hash", False)),
            parallel_gossip=bool(simulation.get("parallel_gossip", False)),
            gossip_workers=int(simulation.get("gossip_workers", 4)),
            parallel_agents=bool(simulation.get("parallel_agents", True)),
            agent_workers=simulation.get("agent_workers"),
            use_cython=bool(simulation.get("use_cython", True)),
            centralized_replicas=int(simulation.get("centralized_replicas", 10)),
            seed=run_seed,
            logger=logger,
            task_stream=events,
        )

        step_data: list[dict] = []
        for step in range(total_steps):
            model.step()
            if step % sample_every_steps == 0:
                step_data.append(collect_step_metrics(model, step))

        final_metrics = collect_final_metrics(
            model,
            step_data,
            sim_duration_s=duration_s,
            step_interval_ms=step_interval_ms,
        )
        replay_digest = task_stream_digest(model.replayed_events)
        expected_stream_digest = task_stream_digest(events)
        if len(model.replayed_events) != len(events) or replay_digest != expected_stream_digest:
            raise RuntimeError("model did not replay the complete task stream")

        full = _state_fractions(step_data, 0.0, step_duration_s)
        steady = _state_fractions(step_data, warmup_s, step_duration_s)
        performance = final_metrics["performance"]
        result = {
            "fleet_size": fleet_size,
            "mode": mode_name,
            "seed": run_seed,
            "duration_s": duration_s,
            "warmup_s": warmup_s,
            "step_interval_ms": step_interval_ms,
            "sample_every_steps": sample_every_steps,
            "layout_seed": layout_seed,
            "layout_digest": actual_layout_digest,
            "stream_digest": expected_stream_digest,
            "stream_event_count": len(events),
            "tasks_created": int(model.task_counter),
            "tasks_completed": int(performance["tasks_completed"]),
            "tasks_active_end": int(model.task_counter - performance["tasks_completed"]),
            "completion_rate": float(performance["completion_rate"]),
            "throughput_tps": float(performance["throughput_tps"]),
            "average_completion_time_s": float(performance["average_completion_time"]),
            "latency_p90_s": float(performance["latency_p90"]),
            "agent_work_fraction_final": float(performance["agent_utilization"]),
            "offered_work_fraction_nominal": (
                float(config["tasks"]["arrival_rate"]) * TASK_WORK_DURATION_S / fleet_size
            ),
            "offered_work_fraction_realized": (
                len(events) * TASK_WORK_DURATION_S / (fleet_size * duration_s)
            ),
            "full": full,
            "post_warmup": steady,
        }
        result["wall_time_s"] = time.monotonic() - started
        return result
    finally:
        if model is not None:
            model.cleanup_shm()


def _record_path(output_dir: Path, fleet_size: int, seed: int, mode: str) -> Path:
    return output_dir / "raw" / f"N{fleet_size:04d}_seed{seed}_{mode}.json"


def _write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _flatten_record(record: dict) -> dict:
    row = {key: value for key, value in record.items() if key not in {"full", "post_warmup"}}
    for window in ("full", "post_warmup"):
        for key, value in record[window].items():
            row[f"{window}_{key}"] = value
    return row


def _write_summary(output_dir: Path) -> Path:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((output_dir / "raw").glob("N*_seed*_*.json"))
    ]
    rows = [_flatten_record(record) for record in records]
    path = output_dir / "run_summary.csv"
    if not rows:
        return path
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_study(
    fleet_sizes: Iterable[int],
    seeds: Iterable[int],
    output_dir: Path,
    duration_override_s: float | None,
    warmup_s: float,
    sample_every_steps: int,
    force: bool,
) -> None:
    fleet_sizes = list(fleet_sizes)
    seeds = list(seeds)
    output_dir.mkdir(parents=True, exist_ok=True)

    study_metadata = {
        "fleet_sizes": fleet_sizes,
        "seeds": seeds,
        "duration_override_s": duration_override_s,
        "warmup_s": warmup_s,
        "sample_every_steps": sample_every_steps,
        "task_work_duration_s": TASK_WORK_DURATION_S,
        "base_commit": "329ab7daed9c4d726b1af77de17c5cb7738c2e24",
    }
    (output_dir / "study_metadata.json").write_text(
        json.dumps(study_metadata, indent=2) + "\n", encoding="utf-8"
    )

    for fleet_size in fleet_sizes:
        distributed, centralized = _load_pair(fleet_size)
        duration_s = float(duration_override_s or distributed["simulation"]["duration"])
        layout_seed = 10_000 + fleet_size
        reference_warehouse = _build_warehouse(distributed, layout_seed)
        layout_digest = _layout_digest(reference_warehouse)
        candidates = _candidate_nodes(reference_warehouse)

        for seed in seeds:
            events = generate_task_stream(
                arrival_rate=float(distributed["tasks"]["arrival_rate"]),
                duration_s=duration_s,
                candidate_nodes=candidates,
                seed=seed,
            )
            positions = _initial_positions(reference_warehouse, fleet_size, seed + 1_000_000)
            trace_path = output_dir / "traces" / f"N{fleet_size:04d}_seed{seed}.json"
            write_task_stream(
                trace_path,
                events,
                {
                    "fleet_size": fleet_size,
                    "seed": seed,
                    "arrival_rate": distributed["tasks"]["arrival_rate"],
                    "duration_s": duration_s,
                    "layout_digest": layout_digest,
                },
            )

            mode_order = ["distributed", "centralized"]
            if seed % 2:
                mode_order.reverse()
            configs = {"distributed": distributed, "centralized": centralized}

            for mode in mode_order:
                path = _record_path(output_dir, fleet_size, seed, mode)
                if path.exists() and not force:
                    print(f"skip existing {path.name}", flush=True)
                    continue
                print(
                    f"run N={fleet_size} seed={seed} mode={mode} events={len(events)}",
                    flush=True,
                )
                record = _run_mode(
                    fleet_size=fleet_size,
                    mode_name=mode,
                    config=configs[mode],
                    events=events,
                    expected_layout_digest=layout_digest,
                    initial_positions=positions,
                    run_seed=seed,
                    layout_seed=layout_seed,
                    duration_s=duration_s,
                    warmup_s=warmup_s,
                    sample_every_steps=sample_every_steps,
                )
                _write_record(path, record)
                print(
                    f"done {path.name}: work={record['full']['working_fraction']:.3f} "
                    f"active={record['full']['active_fraction']:.3f} "
                    f"wall={record['wall_time_s']:.1f}s",
                    flush=True,
                )
                _write_summary(output_dir)

    summary_path = _write_summary(output_dir)
    print(f"wrote {summary_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fleet-sizes",
        default=",".join(str(value) for value in CONFIG_PAIRS),
        help="Comma separated fleet sizes",
    )
    parser.add_argument("--seeds", default="42,43,44,45,46", help="Comma separated seeds")
    parser.add_argument("--output", type=Path, default=ROOT / "study_results" / "utilization_replay")
    parser.add_argument("--duration-s", type=float, default=None)
    parser.add_argument("--warmup-s", type=float, default=180.0)
    parser.add_argument("--sample-every-steps", type=int, default=10)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.sample_every_steps <= 0:
        parser.error("--sample-every-steps must be positive")
    if args.duration_s is not None and args.duration_s <= 0:
        parser.error("--duration-s must be positive")
    if args.warmup_s < 0:
        parser.error("--warmup-s must be nonnegative")

    run_study(
        fleet_sizes=_parse_int_list(args.fleet_sizes),
        seeds=_parse_int_list(args.seeds),
        output_dir=args.output,
        duration_override_s=args.duration_s,
        warmup_s=args.warmup_s,
        sample_every_steps=args.sample_every_steps,
        force=args.force,
    )


if __name__ == "__main__":
    main()
