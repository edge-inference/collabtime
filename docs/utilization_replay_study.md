# Warehouse Work State Fraction Audit and Paired Replay Study

## Purpose

This study addresses two questions raised about Figure 4.4 of the thesis:

1. What does the reported robot utilization metric measure?
2. Why does that metric decrease as fleet size increases?

It also tests whether the centralized and distributed results persist when both
architectures receive exactly the same exogenous workload.

## Metric audit

The implementation increments `steps_working` only while an agent is in the
`WORKING` state and reports

\[
U_{\mathrm{work}} = \frac{1}{NT}
\sum_{i=1}^{N} T_{i,\mathrm{WORKING}}.
\]

Navigation, blocking during navigation, task selection, and idle time are not
in the numerator. The reported value is therefore a work state fraction, not a
measure of the complete interval for which a robot is assigned to a task.

The simulator has three timed states: `IDLE`, `NAVIGATING`, and `WORKING`.
Task claim and completion are transition operations. For the state samples used
in this study,

\[
U_{\mathrm{work}} + U_{\mathrm{navigation}} + U_{\mathrm{idle}} = 1.
\]

The final work state fraction uses every simulation step. The navigation and
idle decomposition is sampled once per simulated second. Across the completed
runs, the maximum difference between the sampled work fraction and the exact
counter is 0.00056.

At a 100 ms step, the 450 step station timer changes the robot to idle on the
following transition step. A completed task therefore contributes 451 recorded
work samples, or 45.1 s. The accounting check uses 45.1 s, while the offered
demand calculation below uses the configured nominal duration of 45 s.

The reported completion statistic is the fraction of tasks arriving during the
900 s run that finish by its endpoint. Mean latency is conditional on
completion because unfinished tasks have no observed completion time. The two
statistics must therefore be interpreted together when a queue remains at the
end of a run.

## Configured load

Fleet size, layout dimensions, and arrival rate change together. This is a
joint fleet and load sweep rather than a strong or weak scaling experiment.

| Robots | Layout | Arrival rate (tasks/s) | Tasks/s/robot | Nominal station work fraction |
|---:|:---:|---:|---:|---:|
| 50 | 40 x 30 | 1.00 | 0.0200 | 0.900 |
| 100 | 55 x 40 | 1.75 | 0.0175 | 0.788 |
| 200 | 70 x 55 | 3.00 | 0.0150 | 0.675 |
| 300 | 80 x 65 | 4.00 | 0.0133 | 0.600 |
| 500 | 95 x 80 | 5.00 | 0.0100 | 0.450 |
| 600 | 105 x 85 | 5.50 | 0.0092 | 0.413 |
| 700 | 110 x 90 | 6.00 | 0.0086 | 0.386 |
| 800 | 115 x 95 | 6.50 | 0.0081 | 0.366 |

The last column is \(\lambda\tau_{\mathrm{work}}/N\) for the nominal 45 s
station duration. It decreases by construction. The repository documentation
is inconsistent about the intended target: `experiments/configs.md` states
approximately 40%, while `docs/scaling_parameters_table.md` states
approximately 75%. Neither document provides a calibration procedure against a
measured utilization statistic. The thesis should report the actual schedule
instead of claiming calibration to a target utilization.

## Why the archived comparison needed a replay check

The archived sweep used one configured seed. That did not guarantee identical
experimental conditions:

- warehouse generation used an unseeded shuffle before model construction;
- task locations were selected only from stations unoccupied at the arrival
  instant;
- agent activation and Poisson arrivals shared random state.

Consequently, architecture behavior could affect later task locations and
random draws. The archived curves remain useful descriptive runs, but they are
not an event for event paired comparison.

## Controlled study design

The replay study uses the warehouse implementation at commit
`329ab7daed9c4d726b1af77de17c5cb7738c2e24` with the following controls:

- fleet sizes 50, 100, 200, 300, 500, 600, 700, and 800;
- five independent task traces, using seeds 42 through 46;
- 900 simulated seconds and a 100 ms simulation step;
- a fixed layout for each fleet size;
- identical initial robot positions within each architecture pair;
- identical task arrival times and task locations within each pair;
- task locations drawn independently of robot occupancy;
- tasks retained at busy stations rather than suppressed;
- centralized and distributed execution order alternated by seed parity;
- full run state fractions and a sensitivity window after 180 s;
- 95% Student $t$ confidence intervals over replication means;
- paired confidence intervals for distributed minus centralized differences.

SHA-256 digests cover every task trace and layout. The analyzer rejects a pair
if its modes differ in stream digest, layout digest, event count, duration, or
sampling configuration. It also verifies task accounting and the state
partition.

## Results

Values below are replication means plus or minus the 95% Student t confidence
interval half width across five task traces. Mean latency includes completed
tasks only.

| Robots | Central completion (%) | Distributed completion (%) | Central throughput (tasks/s) | Distributed throughput (tasks/s) | Central mean latency (s) | Distributed mean latency (s) |
|---:|---:|---:|---:|---:|---:|---:|
| 50 | 86.2 $\pm$ 2.0 | 80.5 $\pm$ 2.8 | 0.86 $\pm$ 0.03 | 0.80 $\pm$ 0.02 | 111.5 $\pm$ 9.6 | 132.1 $\pm$ 9.3 |
| 100 | 88.1 $\pm$ 1.4 | 83.3 $\pm$ 1.0 | 1.55 $\pm$ 0.05 | 1.47 $\pm$ 0.04 | 112.5 $\pm$ 4.9 | 128.5 $\pm$ 5.1 |
| 200 | 85.8 $\pm$ 1.5 | 86.0 $\pm$ 1.5 | 2.59 $\pm$ 0.07 | 2.60 $\pm$ 0.05 | 127.3 $\pm$ 5.2 | 128.7 $\pm$ 5.2 |
| 300 | 80.5 $\pm$ 1.9 | 87.0 $\pm$ 0.8 | 3.23 $\pm$ 0.11 | 3.49 $\pm$ 0.05 | 154.6 $\pm$ 5.7 | 128.5 $\pm$ 3.6 |
| 500 | 71.1 $\pm$ 2.4 | 86.4 $\pm$ 1.0 | 3.55 $\pm$ 0.13 | 4.31 $\pm$ 0.05 | 220.2 $\pm$ 3.9 | 133.2 $\pm$ 1.5 |
| 600 | 68.9 $\pm$ 1.2 | 84.9 $\pm$ 1.3 | 3.79 $\pm$ 0.06 | 4.66 $\pm$ 0.09 | 231.2 $\pm$ 8.3 | 138.8 $\pm$ 3.2 |
| 700 | 62.6 $\pm$ 1.9 | 84.7 $\pm$ 1.3 | 3.76 $\pm$ 0.09 | 5.08 $\pm$ 0.11 | 258.0 $\pm$ 9.6 | 144.4 $\pm$ 2.4 |
| 800 | 54.5 $\pm$ 2.8 | 84.3 $\pm$ 1.4 | 3.54 $\pm$ 0.16 | 5.47 $\pm$ 0.12 | 280.9 $\pm$ 5.4 | 147.5 $\pm$ 1.8 |

The state decomposition confirms that the declining work fraction is not a
corresponding increase in idle time. These values use the once per second state
samples, for which work, navigation, and idle form a partition.

| Robots | Central work (%) | Distributed work (%) | Distributed navigation (%) | Distributed idle (%) |
|---:|---:|---:|---:|---:|
| 50 | 79.3 $\pm$ 2.6 | 74.1 $\pm$ 1.3 | 23.1 $\pm$ 1.5 | 2.8 $\pm$ 0.4 |
| 100 | 71.8 $\pm$ 2.6 | 68.1 $\pm$ 1.5 | 28.8 $\pm$ 1.7 | 3.2 $\pm$ 0.2 |
| 200 | 60.0 $\pm$ 1.8 | 60.3 $\pm$ 1.2 | 35.8 $\pm$ 1.3 | 3.8 $\pm$ 0.1 |
| 300 | 50.2 $\pm$ 1.1 | 54.1 $\pm$ 0.8 | 41.5 $\pm$ 0.8 | 4.4 $\pm$ 0.2 |
| 500 | 32.7 $\pm$ 1.3 | 40.3 $\pm$ 0.5 | 53.6 $\pm$ 0.5 | 6.1 $\pm$ 0.6 |
| 600 | 29.3 $\pm$ 0.7 | 36.5 $\pm$ 0.6 | 56.8 $\pm$ 0.4 | 6.7 $\pm$ 0.6 |
| 700 | 25.1 $\pm$ 0.7 | 34.3 $\pm$ 0.7 | 58.4 $\pm$ 0.6 | 7.2 $\pm$ 0.5 |
| 800 | 21.3 $\pm$ 0.8 | 32.3 $\pm$ 0.6 | 59.9 $\pm$ 1.0 | 7.8 $\pm$ 0.7 |

The paired differences below are distributed minus centralized. Brackets give
the paired 95% confidence interval. A negative latency difference favors the
distributed architecture.

| Robots | Completion difference (percentage points) | Throughput difference (tasks/s) | Mean latency difference (s) |
|---:|---:|---:|---:|
| 50 | -5.7 [-6.8, -4.5] | -0.06 [-0.07, -0.04] | 20.6 [15.1, 26.2] |
| 100 | -4.8 [-6.7, -2.9] | -0.08 [-0.12, -0.05] | 16.0 [10.5, 21.6] |
| 200 | 0.3 [-1.1, 1.6] | 0.01 [-0.03, 0.05] | 1.4 [-6.3, 9.0] |
| 300 | 6.5 [4.3, 8.6] | 0.26 [0.17, 0.34] | -26.2 [-34.9, -17.4] |
| 500 | 15.3 [13.6, 17.1] | 0.76 [0.68, 0.85] | -87.1 [-90.5, -83.6] |
| 600 | 15.9 [14.5, 17.4] | 0.88 [0.79, 0.96] | -92.4 [-100.0, -84.8] |
| 700 | 22.1 [19.1, 25.1] | 1.33 [1.14, 1.51] | -113.6 [-121.9, -105.3] |
| 800 | 29.8 [26.0, 33.6] | 1.94 [1.68, 2.20] | -133.4 [-140.0, -126.8] |

At 50 and 100 robots, all three paired intervals favor centralized
coordination. At 200 robots, all include zero. From 300 robots onward, all
exclude zero in favor of distributed coordination. For this workload and
layout schedule, the observed performance ordering therefore reverses between
200 and 300 robots.

## Interpretation

The decrease in work state fraction is not evidence that most robots are idle.
Two mechanisms explain it:

1. The configured station work demand per robot decreases from 0.900 to 0.366.
2. Navigation occupies a larger share of robot time in the larger and denser
   layouts.

Because station duration is fixed, the work state fraction is largely
determined by completed throughput per robot:

\[
U_{\mathrm{work}} \approx \frac{X\tau_{\mathrm{work}}}{N},
\]

with a residual from tasks still in `WORKING` at the run boundary. It is not an
independent measure of architecture efficiency. Completion fraction, throughput,
latency, and the full state decomposition are needed to interpret it.

## Relation to established terminology

Queueing utilization denotes the long run fraction of time that a resource is
busy. In robotic mobile fulfillment analysis, Lamballais, Roy, and de Koster
define robot utilization over the interval in which a robot is assigned to an
order, which includes travel. The thesis metric covers only station work and
therefore requires the narrower name *work state fraction*.

References:

- M. Harchol-Balter, *Performance Modeling and Design of Computer Systems*,
  Cambridge University Press, 2013.
- T. Lamballais, D. Roy, and M. B. M. de Koster, "Estimating Performance in a
  Robotic Mobile Fulfillment System," *European Journal of Operational
  Research*, 256(3), 2017. <https://doi.org/10.1016/j.ejor.2016.06.063>
- P. Glasserman and D. D. Yao, "Some Guidelines and Guarantees for Common Random Numbers,"
  *Management Science*, 38(6), 1992. <https://doi.org/10.1287/mnsc.38.6.884>
- C. S. M. Currie and R. C. H. Cheng, "A Practical Introduction to Analysis of
  Simulation Output Data," *Winter Simulation Conference*, 2016.
  <https://doi.org/10.1109/WSC.2016.7822084>

## Scope and limitations

- Five traces quantify task stream variation, but each fleet size uses one
  layout. The results do not establish invariance across warehouse geometries.
- The 180 s sensitivity window is not a formal steady state detection result.
  The thesis should treat the primary 900 s runs as finite horizon experiments.
- Fleet size, layout, and arrival rate vary jointly. The study does not isolate
  the causal effect of fleet size alone.
- The simulator abstracts perception, physical dynamics, and station
  processing variability.

These limits bound the conclusions to the metric interpretation and tested
configuration; they do not establish general warehouse capacity or steady
state behavior.

## Reproduction

Study implementation commits on branch `study/utilization-replay`:

- `194f57c`: exogenous task trace generation and paired replay runner;
- `c8836d7`: validation, confidence intervals, tables, and plots;
- `53671d0`: final backlog accounting;
- `97ce773`: explicit plot metric definitions;
- `952d7bf`: opaque figure export for portable rendering.

The approved figure and corresponding thesis interpretation were integrated in
`gatech_thesis` commit `ff23bca`.

The curated study record is versioned with the repository at:

`results/studies/warehouse-utilization-replay-20260715`

It retains the exact replay traces, seed metadata, raw run summaries,
aggregate CSV tables, and validation metadata. Generated plots and transient
logs are omitted because they can be regenerated from these retained inputs.

The final analysis command is:

```bash
python -m studies.analyze_utilization_replay \
  results/studies/warehouse-utilization-replay-20260715 \
  --output results/studies/warehouse-utilization-replay-20260715/analysis
```

The analyzer validated 40 pairs and 80 records. Every pair has matching task
stream, layout, and created task counts. The maximum state partition error is
$1.11\times10^{-16}$, consistent with floating point roundoff. The analysis
directory contains the combined run data, group summaries, paired differences,
load schedule, validation record, and vector figures.
