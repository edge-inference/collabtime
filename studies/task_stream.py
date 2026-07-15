"""Generate and verify exogenous task streams for paired experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import random
from typing import Iterable, Sequence


@dataclass(frozen=True)
class TaskEvent:
    sequence: int
    arrival_time_s: float
    location: int

    @classmethod
    def from_dict(cls, value: dict) -> "TaskEvent":
        return cls(
            sequence=int(value["sequence"]),
            arrival_time_s=float(value["arrival_time_s"]),
            location=int(value["location"]),
        )


def generate_task_stream(
    arrival_rate: float,
    duration_s: float,
    candidate_nodes: Sequence[int],
    seed: int,
) -> tuple[TaskEvent, ...]:
    """Generate Poisson arrival times and independent task locations."""
    if arrival_rate < 0:
        raise ValueError("arrival_rate must be nonnegative")
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")

    nodes = tuple(sorted({int(node) for node in candidate_nodes}))
    if arrival_rate > 0 and not nodes:
        raise ValueError("candidate_nodes must not be empty for a nonzero arrival rate")
    if arrival_rate == 0:
        return ()

    arrival_rng = random.Random(int(seed))
    location_rng = random.Random(int(seed) ^ 0x9E3779B97F4A7C15)
    events: list[TaskEvent] = []
    arrival_time_s = arrival_rng.expovariate(arrival_rate)

    while arrival_time_s <= duration_s:
        events.append(
            TaskEvent(
                sequence=len(events),
                arrival_time_s=arrival_time_s,
                location=location_rng.choice(nodes),
            )
        )
        arrival_time_s += arrival_rng.expovariate(arrival_rate)

    return tuple(events)


def task_stream_digest(events: Iterable[TaskEvent]) -> str:
    """Return a stable digest over sequence, arrival time, and location."""
    payload = [asdict(event) for event in events]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_task_stream(path, events: Sequence[TaskEvent], metadata: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": dict(metadata),
        "digest": task_stream_digest(events),
        "events": [asdict(event) for event in events],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_task_stream(path) -> tuple[dict, tuple[TaskEvent, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    events = tuple(TaskEvent.from_dict(value) for value in payload["events"])
    digest = task_stream_digest(events)
    if digest != payload.get("digest"):
        raise ValueError(f"task stream digest mismatch for {path}")
    return dict(payload.get("metadata", {})), events
