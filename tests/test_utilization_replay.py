from __future__ import annotations

import logging
from pathlib import Path
import tempfile
import unittest

from studies.task_stream import (
    TaskEvent,
    generate_task_stream,
    read_task_stream,
    task_stream_digest,
    write_task_stream,
)
from studies.utilization_replay import (
    ReplayWarehouseModel,
    _build_warehouse,
    _candidate_nodes,
    _layout_digest,
    _state_fractions,
)


class TaskStreamTest(unittest.TestCase):
    def test_generation_is_deterministic_and_bounded(self):
        first = generate_task_stream(2.0, 10.0, [9, 4, 7], seed=42)
        second = generate_task_stream(2.0, 10.0, [7, 9, 4], seed=42)
        other = generate_task_stream(2.0, 10.0, [4, 7, 9], seed=43)

        self.assertEqual(first, second)
        self.assertNotEqual(task_stream_digest(first), task_stream_digest(other))
        self.assertTrue(all(0 < event.arrival_time_s <= 10.0 for event in first))
        self.assertTrue(all(event.location in {4, 7, 9} for event in first))
        self.assertEqual(list(range(len(first))), [event.sequence for event in first])

    def test_round_trip_checks_digest(self):
        events = generate_task_stream(1.0, 4.0, [1, 2], seed=11)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            write_task_stream(path, events, {"fleet_size": 2})
            metadata, loaded = read_task_stream(path)
        self.assertEqual({"fleet_size": 2}, metadata)
        self.assertEqual(events, loaded)


class StateAccountingTest(unittest.TestCase):
    def test_state_fractions_form_a_partition(self):
        rows = [
            {
                "step": 0,
                "utilization_working": 0.25,
                "utilization_active": 0.75,
                "num_stuck_agents": 1,
            },
            {
                "step": 10,
                "utilization_working": 0.50,
                "utilization_active": 1.00,
                "num_stuck_agents": 3,
            },
        ]
        fractions = _state_fractions(rows, min_time_s=0.0, step_duration_s=0.1)
        self.assertAlmostEqual(0.375, fractions["working_fraction"])
        self.assertAlmostEqual(0.5, fractions["navigating_fraction"])
        self.assertAlmostEqual(0.125, fractions["idle_fraction"])
        self.assertAlmostEqual(
            1.0,
            fractions["working_fraction"]
            + fractions["navigating_fraction"]
            + fractions["idle_fraction"],
        )


class ReplayIntegrationTest(unittest.TestCase):
    def test_paired_modes_replay_same_events_and_layout(self):
        config = {"warehouse": {"size": [20, 15]}}
        layout_seed = 10020
        reference = _build_warehouse(config, layout_seed)
        events = (
            TaskEvent(sequence=0, arrival_time_s=0.1, location=_candidate_nodes(reference)[0]),
            TaskEvent(sequence=1, arrival_time_s=0.3, location=_candidate_nodes(reference)[-1]),
        )
        positions = [
            node
            for node, node_type in reference.node_types.items()
            if node_type == "staging"
        ][:2]
        expected_layout = _layout_digest(reference)
        replay_digests = []

        logger = logging.getLogger("replay-integration-test")
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.ERROR)

        for mode in ("p2p", "centralized"):
            warehouse = _build_warehouse(config, layout_seed)
            self.assertEqual(expected_layout, _layout_digest(warehouse))
            model = ReplayWarehouseModel(
                n_agents=2,
                warehouse_graph=warehouse,
                agent_positions=positions,
                task_arrival_rate=1.0,
                task_types=["pickup"],
                task_priorities=[1],
                step_duration_s=0.1,
                mode=mode,
                use_spatial_hash=False,
                parallel_gossip=False,
                parallel_agents=False,
                use_cython=True,
                centralized_replicas=1,
                seed=7,
                logger=logger,
                task_stream=events,
            )
            try:
                for _ in range(4):
                    model.step()
                self.assertEqual(2, model.task_counter)
                replay_digests.append(task_stream_digest(model.replayed_events))
            finally:
                model.cleanup_shm()

        self.assertEqual([task_stream_digest(events)] * 2, replay_digests)


if __name__ == "__main__":
    unittest.main()
