---
type: case
category: node
issue: memory-tracker-leak
keywords: [memory tracker, memory leak, INSERT slow, throttling]
---

# Case-007: Memory Tracking Leak Slowing Imports

## Environment

- StarRocks version: 3.3.9
- Architecture: shared-nothing

## Symptom

INSERT tasks continued running but were extremely slow. Progress counters barely moved.

## Investigation

Observed that query memory usage was at capacity. Suspected a known memory tracking leak.

## Root Cause

Known memory tracking leak (PR [#54242](https://github.com/StarRocks/starrocks/pull/54242)) —
the system incorrectly believed memory was exhausted, throttling import throughput.

## Resolution

- Upgrade to the version containing the fix. Memory usage dropped and import sink latency
  returned to normal.

## Lessons Learned

- "Memory at capacity" with healthy queries is a strong signal for a tracker leak rather
  than an actual workload problem.
- Treat the per-module memory tracker (`/mem_tracker`) as the authoritative source when
  diagnosing throttling.

## Related Skills

- `skills/03-node.md` — BE OOM and memory tracking leak section
- `skills/02-import.md` — write-slow diagnosis when memory throttling masquerades as a
  thread-pool issue
