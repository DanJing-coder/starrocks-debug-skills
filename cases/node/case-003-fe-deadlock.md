---
type: case
category: node
issue: fe-deadlock
keywords: [FE deadlock, LockManager, ReportHandler, version not found, jstack]
---

# Case-003: FE Deadlock Causing "Version Not Found" Errors (LockManager Deadlock)

## Environment

- StarRocks version: 3.3.11
- Architecture: shared-nothing

## Symptom

Queries reported `version does not exist` — versions had already been recycled on BE.
FE Report timestamps had not updated for a long time.

## Investigation

1. **Suspected FE deadlock**: Report timestamp stagnation is a classic indicator.
2. **Captured jstack**:
   ```bash
   jstack <fe_pid> > /tmp/fe_jstack.log
   ```
3. **Found deadlock**:
   ```
   "ReportHandler" #207 daemon prio=5 ... in Object.wait()
     java.lang.Thread.State: TIMED_WAITING (on object monitor)
       at com.starrocks.common.util.concurrent.lock.LockManager.lock(LockManager.java:105)
       at com.starrocks.common.util.concurrent.lock.Locker.lockDatabase(Locker.java:119)
       at com.starrocks.server.LocalMetastore.getPartitionIdToStorageMediumMap(...)
       at com.starrocks.leader.ReportHandler.tabletReport(...)
   ```

## Root Cause

FE LockManager deadlock — the `ReportHandler` thread couldn't acquire the DB lock,
blocking tablet report processing. BE recycled old versions while FE was unaware.

## Resolution

### Short-term

- Restart FE to recover.

### Long-term

- Preserve jstack dumps and escalate to engineering for code-level fix.

## Lessons Learned

- A stale Report timestamp is the canonical FE-deadlock signal — check it first when
  queries report `version does not exist`.
- Always capture multiple jstack snapshots before restart so engineering can analyze
  the lock graph.

## Related Skills

- `skills/03-node.md` — FE deadlock diagnostic flow
- `skills/01-query.md` — `version does not exist` symptom mapping
