# M294 – CI runtime study (Source release gate, attempt 1 of each run; GitHub jobs API step timestamps)

Columns: SHA, leg, conclusion, job wall time, 'Real Qt system libraries' step, 'Locked runtime and verification tools' (pip) step, 'Verify exact source, dependencies, tests and wheel' step (collection + pytest [+ coverage on 3.12] + packaging/post-test gates).
Cancellations below 15 min are superseded runs (a newer push cancelled them), not timeouts.

```
07a0f8b 3.11 success 33m Real_Qt_sy=10s Locked_run=13s Verify_exa=1957s
35d3bc6 3.11 cancelled 7m Real_Qt_sy=10s Locked_run=20s Verify_exa=385s
42eb03d 3.11 cancelled 5m Real_Qt_sy=12s Locked_run=19s Verify_exa=264s
4eae8f5 3.11 success 35m Real_Qt_sy=26s Locked_run=15s Verify_exa=2046s
649e33d 3.11 success 39m Real_Qt_sy=245s Locked_run=16s Verify_exa=2117s
7fe52ff 3.11 cancelled 12m Real_Qt_sy=28s Locked_run=15s Verify_exa=660s
8a76829 3.11 cancelled 1m Real_Qt_sy=10s Locked_run=21s Verify_exa=57s
ac7657b 3.11 success 37m Real_Qt_sy=31s Locked_run=15s Verify_exa=2165s
b21782b 3.11 success 35m Real_Qt_sy=36s Locked_run=16s Verify_exa=2062s
b6a6a33 3.11 success 36m Real_Qt_sy=31s Locked_run=16s Verify_exa=2128s
b8b2c3a 3.11 failure 50m Real_Qt_sy=11s Locked_run=22s Verify_exa=2985s
db0cba3 3.11 success 39m Real_Qt_sy=210s Locked_run=15s Verify_exa=2156s
07a0f8b 3.12 cancelled 60m Real_Qt_sy=13s Locked_run=25s Verify_exa=3567s
35d3bc6 3.12 cancelled 7m Real_Qt_sy=28s Locked_run=17s Verify_exa=357s
42eb03d 3.12 cancelled 5m Real_Qt_sy=11s Locked_run=24s Verify_exa=263s
4eae8f5 3.12 success 45m Real_Qt_sy=34s Locked_run=17s Verify_exa=2656s
649e33d 3.12 success 46m Real_Qt_sy=52s Locked_run=17s Verify_exa=2699s
7fe52ff 3.12 cancelled 12m Real_Qt_sy=29s Locked_run=17s Verify_exa=654s
8a76829 3.12 cancelled 1m Real_Qt_sy=11s Locked_run=23s Verify_exa=51s
ac7657b 3.12 success 46m Real_Qt_sy=27s Locked_run=18s Verify_exa=2720s
b21782b 3.12 success 45m Real_Qt_sy=28s Locked_run=17s Verify_exa=2661s
b6a6a33 3.12 success 47m Real_Qt_sy=17s Locked_run=16s Verify_exa=2788s
b8b2c3a 3.12 failure 46m Real_Qt_sy=29s Locked_run=17s Verify_exa=2739s
db0cba3 3.12 success 49m Real_Qt_sy=215s Locked_run=18s Verify_exa=2745s
07a0f8b 3.13 success 52m Real_Qt_sy=11s Locked_run=24s Verify_exa=3076s
35d3bc6 3.13 cancelled 7m Real_Qt_sy=12s Locked_run=18s Verify_exa=385s
42eb03d 3.13 cancelled 5m Real_Qt_sy=32s Locked_run=17s Verify_exa=236s
4eae8f5 3.13 success 35m Real_Qt_sy=23s Locked_run=16s Verify_exa=2052s
649e33d 3.13 success 40m Real_Qt_sy=193s Locked_run=16s Verify_exa=2190s
7fe52ff 3.13 cancelled 12m Real_Qt_sy=14s Locked_run=20s Verify_exa=678s
8a76829 3.13 cancelled 1m Real_Qt_sy=26s Locked_run=17s Verify_exa=42s
ac7657b 3.13 success 40m Real_Qt_sy=13s Locked_run=18s Verify_exa=2402s
b21782b 3.13 success 40m Real_Qt_sy=16s Locked_run=21s Verify_exa=2383s
b6a6a33 3.13 success 37m Real_Qt_sy=27s Locked_run=17s Verify_exa=2156s
b8b2c3a 3.13 failure 37m Real_Qt_sy=31s Locked_run=17s Verify_exa=2156s
db0cba3 3.13 success 50m Real_Qt_sy=17s Locked_run=24s Verify_exa=2995s
```

## Findings

* Dependency installation is 13–25 s and the Qt system packages take 10–245 s (apt mirror variance). The `Verify` step dominates every leg.
* Successful 3.12 coverage `Verify` steps take **2,656–2,788 s (44.3–46.5 min)** over six SHAs, `649e33d` … `b6a6a33`. Whole jobs take 45–49 min.
* The only 3.12 timeout attempts are on `07a0f8b` (attempt 1: `Verify` was still running at 3,567 s when the job was killed; attempt 2 the same) and on the re-run of `4eae8f5` at 14:05 UTC (see `m261-m290-evidence/m290_ci_leg_timing_ab.txt`). All three ran on 2026-11-21 between 11:45 and 15:05 UTC.
* 3.13 rose to 50–52 min in the same window (`db0cba3` earlier, then `07a0f8b`), then returned to 37 min on `b6a6a33` (15:10 UTC).
* Coverage overhead: 3.12 (coverage) vs 3.11 (no coverage) `Verify` on the same SHA is +576 to +660 s (≈ +28–31 %). Example: b6a6a33 2,788 s vs 2,128 s.
* The local 3.11 run (2-core sandbox) takes 2,691 s for pytest alone. Local coverage overhead on the four M272/M273/M286 test files is 73 s → 158 s.
* Per-test timing on the hosted runners cannot be obtained from the sandbox (job logs are blocked). The cause of the 11:45–15:05 slowdown is **unknown**.

## Decision (M294)

**No CI redesign in this mission.**

* With successful 3.12 jobs at 45–49 min against a 60-minute limit, there are 11–15 min of headroom.
* The timeouts were confined to one afternoon window, and the same code passed in 47 min immediately afterwards.
* Splitting coverage across jobs would add `coverage combine`, artifact transfer and exact-SHA binding across jobs. That is a release-gate design change with its own failure modes, and the evidence does not justify it now.

Reconsider the split if successful 3.12 runs exceed 52 min (85 % of the limit) on two separate days. The design must keep the whole test scope, the `.coveragerc`/floor configuration, a fail-closed combine step (a missing shard fails the gate), and exact-SHA binding of every shard.

The 60-minute job limit and the 900 s per-test watchdog are unchanged.
