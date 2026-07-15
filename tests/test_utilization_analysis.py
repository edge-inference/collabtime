from __future__ import annotations

import unittest

import pandas as pd

from studies.analyze_utilization_replay import _flatten, validate_pairs


def _record(mode: str, stream_digest: str = "stream") -> dict:
    return {
        "fleet_size": 50,
        "mode": mode,
        "seed": 42,
        "duration_s": 100.0,
        "warmup_s": 20.0,
        "step_interval_ms": 100,
        "sample_every_steps": 10,
        "layout_digest": "layout",
        "stream_digest": stream_digest,
        "stream_event_count": 10,
        "tasks_created": 10,
        "tasks_completed": 8,
        "tasks_active_end": 2,
        "completion_rate": 0.8,
        "throughput_tps": 0.08,
        "average_completion_time_s": 50.0,
        "latency_p90_s": 70.0,
        "agent_work_fraction_final": 0.09,
        "offered_work_fraction_nominal": 0.09,
        "offered_work_fraction_realized": 0.09,
        "full": {
            "working_fraction": 0.0898,
            "navigating_fraction": 0.6002,
            "idle_fraction": 0.31,
            "active_fraction": 0.69,
            "mean_stuck_agents": 0.0,
            "sample_count": 100,
        },
        "post_warmup": {
            "working_fraction": 0.10,
            "navigating_fraction": 0.65,
            "idle_fraction": 0.25,
            "active_fraction": 0.75,
            "mean_stuck_agents": 0.0,
            "sample_count": 80,
        },
    }


class UtilizationAnalysisTest(unittest.TestCase):
    def test_completed_work_uses_discrete_work_state_duration(self):
        row = _flatten(_record("centralized"))

        self.assertAlmostEqual(0.072, row["completed_nominal_work_fraction"])
        self.assertAlmostEqual(0.07216, row["completed_work_state_fraction"])
        self.assertAlmostEqual(0.01784, row["incomplete_task_work_fraction"])

    def test_pair_validation_checks_replay_and_state_accounting(self):
        frame = pd.DataFrame(
            [_flatten(_record("centralized")), _flatten(_record("distributed"))]
        )

        validation = validate_pairs(frame)

        self.assertEqual(1, validation["pair_count"])
        self.assertEqual(0.0, validation["maximum_state_partition_error"])

    def test_pair_validation_rejects_different_task_streams(self):
        frame = pd.DataFrame(
            [
                _flatten(_record("centralized", stream_digest="first")),
                _flatten(_record("distributed", stream_digest="second")),
            ]
        )

        with self.assertRaisesRegex(ValueError, "unmatched stream_digest"):
            validate_pairs(frame)


if __name__ == "__main__":
    unittest.main()
