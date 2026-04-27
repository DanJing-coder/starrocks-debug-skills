---
type: case
category: node
issue: be-oom
keywords: [BE OOM, publish timeout, pstack, cluster recovery]
---

# Case-008: Publish Timeout Cascade Caused by BE OOM

## Environment

- StarRocks version: 3.3.16
- Architecture: shared-nothing

## Symptom

Cluster experienced widespread publish timeouts.

## Investigation

1. Ran `pstack` on some nodes for diagnostics.
2. The nodes that did **not** have pstack running experienced OOM.
3. Approximately 30 minutes after the OOM events, all committed tasks were automatically
   consumed and the cluster recovered.

## Root Cause

BE node OOM caused publish processing to completely stall, blocking all publish operations
for affected tables.

## Resolution

- Restart OOM'd nodes to recover.
- Investigate the root cause of OOM (large queries or memory leaks) and address upstream.

## Lessons Learned

- Cluster-wide publish timeouts often originate from a small number of OOM'd BEs — start
  by listing process-start times for all BEs.
- Recovery is typically automatic once OOM'd nodes restart, but the underlying memory
  pressure must still be diagnosed.

## Related Skills

- `skills/03-node.md` — BE OOM and crash investigation
- `skills/02-import.md` — publish timeout diagnosis
