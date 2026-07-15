#!/usr/bin/env python3
"""Analyze paired utilization replay records and calculate confidence intervals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from config import TASK_WORK_DURATION_S, TASK_WORK_DURATION_STEPS


plt.rcParams.update(
    {
        "font.family": "Nimbus Roman",
        "font.serif": ["Nimbus Roman", "Times", "Times New Roman"],
        "font.sans-serif": ["Nimbus Roman", "Times", "Times New Roman"],
        "font.size": 10,
        "axes.labelsize": 10,
        "axes.titlesize": 10.5,
        "legend.fontsize": 9,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "axes.grid": False,
        "axes.spines.top": True,
        "axes.spines.right": True,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


STATE_METRICS = (
    "full_working_fraction",
    "full_navigating_fraction",
    "full_idle_fraction",
    "full_active_fraction",
    "post_warmup_working_fraction",
    "post_warmup_navigating_fraction",
    "post_warmup_idle_fraction",
    "post_warmup_active_fraction",
)

OUTCOME_METRICS = (
    "agent_work_fraction_final",
    "completion_rate",
    "throughput_tps",
    "average_completion_time_s",
    "latency_p90_s",
)


def _flatten(record: dict) -> dict:
    row = {key: value for key, value in record.items() if key not in {"full", "post_warmup"}}
    for window in ("full", "post_warmup"):
        for key, value in record[window].items():
            row[f"{window}_{key}"] = value
    row["completed_nominal_work_fraction"] = (
        row["throughput_tps"] * TASK_WORK_DURATION_S / row["fleet_size"]
    )
    row["configured_arrival_rate_tps"] = (
        row["offered_work_fraction_nominal"]
        * row["fleet_size"]
        / TASK_WORK_DURATION_S
    )
    row["realized_arrival_rate_tps"] = row["stream_event_count"] / row["duration_s"]
    row["arrival_rate_per_robot"] = (
        row["configured_arrival_rate_tps"] / row["fleet_size"]
    )
    row["tasks_active_end_per_robot"] = row["tasks_active_end"] / row["fleet_size"]
    row["arrival_completion_gap_tps"] = (
        row["realized_arrival_rate_tps"] - row["throughput_tps"]
    )
    work_state_duration_s = (
        (TASK_WORK_DURATION_STEPS + 1) * row["step_interval_ms"] / 1000.0
    )
    row["completed_work_state_fraction"] = (
        row["throughput_tps"] * work_state_duration_s / row["fleet_size"]
    )
    row["incomplete_task_work_fraction"] = (
        row["agent_work_fraction_final"] - row["completed_work_state_fraction"]
    )
    return row


def load_records(roots: Iterable[Path]) -> pd.DataFrame:
    paths: list[Path] = []
    for root in roots:
        paths.extend(root.rglob("raw/N*_seed*_*.json"))
    if not paths:
        raise ValueError("no raw utilization replay records found")
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(paths)]
    frame = pd.DataFrame(_flatten(record) for record in records)
    return frame.sort_values(["fleet_size", "seed", "mode"]).reset_index(drop=True)


def validate_pairs(frame: pd.DataFrame) -> dict:
    failures: list[str] = []
    for (fleet_size, seed), pair in frame.groupby(["fleet_size", "seed"]):
        modes = set(pair["mode"])
        if len(pair) != 2 or modes != {"centralized", "distributed"}:
            failures.append(
                f"N={fleet_size}, seed={seed}: records={len(pair)}, modes={sorted(modes)}"
            )
            continue
        for key in (
            "stream_digest",
            "layout_digest",
            "stream_event_count",
            "tasks_created",
            "duration_s",
            "warmup_s",
            "step_interval_ms",
            "sample_every_steps",
        ):
            if pair[key].nunique() != 1:
                failures.append(f"N={fleet_size}, seed={seed}: unmatched {key}")

    expected_seeds = set(frame["seed"].unique())
    for fleet_size, group in frame.groupby("fleet_size"):
        actual_seeds = set(group["seed"].unique())
        if actual_seeds != expected_seeds:
            failures.append(
                f"N={fleet_size}: seeds={sorted(actual_seeds)}, expected={sorted(expected_seeds)}"
            )
        for key in (
            "configured_arrival_rate_tps",
            "offered_work_fraction_nominal",
            "duration_s",
            "warmup_s",
            "step_interval_ms",
            "sample_every_steps",
        ):
            if group[key].nunique() != 1:
                failures.append(f"N={fleet_size}: inconsistent {key}")

    creation_error = np.abs(frame["tasks_created"] - frame["stream_event_count"])
    active_task_error = np.abs(
        frame["tasks_active_end"] - (frame["tasks_created"] - frame["tasks_completed"])
    )
    partition_errors = []
    for window in ("full", "post_warmup"):
        partition_errors.append(
            np.abs(
                frame[f"{window}_working_fraction"]
                + frame[f"{window}_navigating_fraction"]
                + frame[f"{window}_idle_fraction"]
                - 1.0
            )
        )
    maximum_partition_error = float(pd.concat(partition_errors).max())
    if int(creation_error.max()) != 0:
        failures.append("one or more runs did not create every replayed task")
    if int(active_task_error.max()) != 0:
        failures.append("one or more runs have inconsistent final task accounting")
    if maximum_partition_error > 1e-12:
        failures.append(
            f"state fractions do not form a partition (maximum error {maximum_partition_error})"
        )
    if float(frame["incomplete_task_work_fraction"].min()) < -1e-12:
        failures.append("completed tasks account for more work time than the state counters")

    if failures:
        raise ValueError("paired-design validation failed:\n" + "\n".join(failures))

    sampling_difference = np.abs(
        frame["agent_work_fraction_final"] - frame["full_working_fraction"]
    )
    return {
        "pair_count": int(frame.groupby(["fleet_size", "seed"]).ngroups),
        "record_count": int(len(frame)),
        "fleet_sizes": sorted(int(value) for value in frame["fleet_size"].unique()),
        "seeds": sorted(int(value) for value in frame["seed"].unique()),
        "all_stream_digests_paired": True,
        "all_layout_digests_paired": True,
        "all_created_task_counts_paired": True,
        "maximum_state_partition_error": maximum_partition_error,
        "maximum_sampled_vs_counter_work_fraction_difference": float(
            sampling_difference.max()
        ),
        "maximum_incomplete_task_work_fraction": float(
            frame["incomplete_task_work_fraction"].max()
        ),
    }


def _estimate(values: pd.Series) -> dict:
    clean = values.dropna().astype(float)
    count = len(clean)
    mean = float(clean.mean()) if count else float("nan")
    standard_deviation = float(clean.std(ddof=1)) if count > 1 else 0.0
    if count > 1:
        half_width = float(stats.t.ppf(0.975, count - 1) * standard_deviation / np.sqrt(count))
    else:
        half_width = 0.0
    return {
        "n": count,
        "mean": mean,
        "standard_deviation": standard_deviation,
        "ci95_half_width": half_width,
        "ci95_low": mean - half_width,
        "ci95_high": mean + half_width,
    }


def summarize_groups(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    metrics = STATE_METRICS + OUTCOME_METRICS + (
        "tasks_active_end",
        "tasks_active_end_per_robot",
        "arrival_completion_gap_tps",
        "offered_work_fraction_nominal",
        "offered_work_fraction_realized",
        "completed_nominal_work_fraction",
        "completed_work_state_fraction",
        "incomplete_task_work_fraction",
    )
    for (fleet_size, mode), group in frame.groupby(["fleet_size", "mode"]):
        for metric in metrics:
            rows.append(
                {
                    "fleet_size": int(fleet_size),
                    "mode": mode,
                    "metric": metric,
                    **_estimate(group[metric]),
                }
            )
    return pd.DataFrame(rows).sort_values(["fleet_size", "mode", "metric"])


def summarize_paired_differences(frame: pd.DataFrame) -> pd.DataFrame:
    metrics = STATE_METRICS + OUTCOME_METRICS
    rows = []
    for fleet_size, group in frame.groupby("fleet_size"):
        for metric in metrics:
            pivot = group.pivot(index="seed", columns="mode", values=metric)
            difference = pivot["distributed"] - pivot["centralized"]
            rows.append(
                {
                    "fleet_size": int(fleet_size),
                    "metric": metric,
                    "difference": "distributed_minus_centralized",
                    **_estimate(difference),
                }
            )
    return pd.DataFrame(rows).sort_values(["fleet_size", "metric"])


def write_state_table(group_summary: pd.DataFrame, path: Path) -> None:
    selected = group_summary[
        group_summary["metric"].isin(
            {
                "full_working_fraction",
                "full_navigating_fraction",
                "full_idle_fraction",
                "full_active_fraction",
            }
        )
    ].copy()
    selected["state"] = selected["metric"].str.removeprefix("full_").str.removesuffix("_fraction")
    selected[
        [
            "fleet_size",
            "mode",
            "state",
            "n",
            "mean",
            "standard_deviation",
            "ci95_low",
            "ci95_high",
        ]
    ].to_csv(path, index=False)


def write_load_schedule(frame: pd.DataFrame, path: Path) -> None:
    rows = []
    for fleet_size, group in frame.groupby("fleet_size"):
        rows.append(
            {
                "fleet_size": int(fleet_size),
                "configured_arrival_rate_tps": float(
                    group["configured_arrival_rate_tps"].iloc[0]
                ),
                "arrival_rate_per_robot": float(group["arrival_rate_per_robot"].iloc[0]),
                "nominal_offered_work_fraction": float(
                    group["offered_work_fraction_nominal"].iloc[0]
                ),
                "mean_realized_arrival_rate_tps": float(
                    group.groupby("seed")["realized_arrival_rate_tps"].first().mean()
                ),
            }
        )
    pd.DataFrame(rows).sort_values("fleet_size").to_csv(path, index=False)


def _metric_rows(summary: pd.DataFrame, metric: str, mode: str) -> pd.DataFrame:
    return summary[(summary["metric"] == metric) & (summary["mode"] == mode)].sort_values(
        "fleet_size"
    )


def plot_state_fractions(group_summary: pd.DataFrame, path: Path) -> None:
    styles = {
        "distributed": {"color": "#1f4e79", "marker": "o", "label": "Distributed"},
        "centralized": {"color": "#b23a48", "marker": "s", "label": "Centralized"},
    }
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.2), constrained_layout=True)
    for mode, style in styles.items():
        for ax, metric, ylabel in (
            (axes[0], "agent_work_fraction_final", "Work state fraction"),
            (axes[1], "full_active_fraction", "Active robot fraction"),
        ):
            rows = _metric_rows(group_summary, metric, mode)
            ax.errorbar(
                rows["fleet_size"],
                rows["mean"],
                yerr=rows["ci95_half_width"],
                color=style["color"],
                marker=style["marker"],
                linewidth=1.6,
                capsize=3,
                label=style["label"],
            )
            ax.set_xlabel("Fleet size $N$")
            ax.set_ylabel(ylabel)
            ax.set_ylim(0, 1)
    axes[0].legend(frameon=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_scaling_summary(group_summary: pd.DataFrame, path: Path) -> None:
    styles = {
        "distributed": {
            "color": "#1f4e79",
            "marker": "o",
            "linestyle": "-",
            "label": "Distributed (CollabTime)",
        },
        "centralized": {
            "color": "#b23a48",
            "marker": "s",
            "linestyle": "--",
            "label": "Centralized",
        },
    }
    panels = (
        ("completion_rate", "Completion fraction (%)", 100.0, (0, 100)),
        ("throughput_tps", "Throughput (tasks/s)", 1.0, None),
        (
            "average_completion_time_s",
            "Mean latency of completed tasks (s)",
            1.0,
            None,
        ),
        ("agent_work_fraction_final", "Work state fraction (%)", 100.0, (0, 100)),
    )
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.2), constrained_layout=True)
    for ax, (metric, ylabel, scale, ylim) in zip(axes.ravel(), panels):
        for mode, style in styles.items():
            rows = _metric_rows(group_summary, metric, mode)
            ax.errorbar(
                rows["fleet_size"],
                rows["mean"] * scale,
                yerr=rows["ci95_half_width"] * scale,
                color=style["color"],
                marker=style["marker"],
                linestyle=style["linestyle"],
                linewidth=1.6,
                markersize=5,
                capsize=3,
                label=style["label"],
            )
        ax.set_xlabel("Fleet size $N$")
        ax.set_ylabel(ylabel)
        ax.set_xlim(35, 815)
        if ylim is not None:
            ax.set_ylim(*ylim)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=2,
        bbox_to_anchor=(0.5, 1.04),
        frameon=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.with_suffix(".png"), dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_state_decomposition(group_summary: pd.DataFrame, path: Path) -> None:
    states = (
        ("full_working_fraction", "Work", "#2f6f4e", "o"),
        ("full_navigating_fraction", "Navigation", "#1f4e79", "s"),
        ("full_idle_fraction", "Idle", "#666666", "^"),
    )
    modes = (("distributed", "Distributed (CollabTime)"), ("centralized", "Centralized"))
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9), constrained_layout=True)
    for ax, (mode, title) in zip(axes, modes):
        for metric, label, color, marker in states:
            rows = _metric_rows(group_summary, metric, mode)
            ax.errorbar(
                rows["fleet_size"],
                rows["mean"] * 100.0,
                yerr=rows["ci95_half_width"] * 100.0,
                color=color,
                marker=marker,
                linewidth=1.5,
                markersize=4.5,
                capsize=3,
                label=label,
            )
        ax.set_title(title)
        ax.set_xlabel("Fleet size $N$")
        ax.set_ylabel("Robot state fraction (%)")
        ax.set_xlim(35, 815)
        ax.set_ylim(0, 100)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=3,
        bbox_to_anchor=(0.5, 1.10),
        frameon=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.with_suffix(".png"), dpi=180, bbox_inches="tight")
    plt.close(fig)


def analyze(roots: Iterable[Path], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = load_records(roots)
    validation = validate_pairs(frame)
    group_summary = summarize_groups(frame)
    paired = summarize_paired_differences(frame)

    frame.to_csv(output_dir / "combined_runs.csv", index=False)
    group_summary.to_csv(output_dir / "group_summary.csv", index=False)
    paired.to_csv(output_dir / "paired_differences.csv", index=False)
    write_state_table(group_summary, output_dir / "state_summary.csv")
    write_load_schedule(frame, output_dir / "load_schedule.csv")
    plot_state_fractions(group_summary, output_dir / "state_fractions.png")
    plot_scaling_summary(group_summary, output_dir / "scaling_summary.pdf")
    plot_state_decomposition(group_summary, output_dir / "state_decomposition.pdf")

    (output_dir / "validation.json").write_text(
        json.dumps(validation, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(validation, indent=2))
    print(f"wrote analysis to {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.roots, args.output)


if __name__ == "__main__":
    main()
