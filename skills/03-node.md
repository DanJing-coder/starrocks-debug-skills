---
type: skill
category: node
priority: 3
keywords: [BE crash, BE OOM, FE deadlock, FE Full GC, FE heap memory, memory tracker, lock ordering, DeadLockChecker, jstack, fair lock]
---

# 03 - Node Troubleshooting (BE Crash / OOM, FE Deadlock / GC)

Investigation guide for BE-level crashes and out-of-memory events, FE deadlocks,
Full GC pauses, and FE heap memory analysis.

---

## 1. BE OOM

### Standard Investigation

1. Check query memory usage: `SHOW PROC '/current_queries';`
2. Search BE logs for `large memory alloc` entries to identify memory-heavy queries.
3. Check for known memory tracking leak issues.
4. Review `mem_limit` and memory pool configurations.

```bash
# Per-module memory breakdown
curl -s http://<BE_IP>:<BE_HTTP_PORT>/mem_tracker
curl -s http://<BE_IP>:<BE_HTTP_PORT>/metrics | grep "^starrocks_be_.*_mem_bytes"

# tcmalloc status
curl -s http://<BE_IP>:<BE_HTTP_PORT>/memz

# Find memory-heavy queries in mem_tracker
curl -s http://<BE_IP>:<BE_HTTP_PORT>/mem_tracker | grep "query"
```

### Precisely Locate SQL Causing BE OOM

**Step 1**: Find the time window when BE memory spiked via monitoring. Usually 1-2 large queries
can fill memory.

**Step 2**: Search `be.WARNING` for `large memory alloc` entries during that time window:

```bash
grep "large memory alloc" be.WARNING
```

The stack trace shows the query_id and memory allocation details:

```
W20250405 00:34:30.142933 277491603341440 mem_hook.cpp:90] large memory alloc, query_id:53d22286-11ad-11f0-8b44-0acefe2dd437 instance: 53d22286-11ad-11f0-8b44-0acefe2dd43c acquire:1128011704 bytes, stack:
@          0x657fa48  starrocks::get_stack_trace[abi:cxx11]()
@          0x81e8bf8  malloc
@          0xd89c2ac  operator new(unsigned long)
@          0x544f5d4  void std::vector > >::_M_range_insert(...)
@          0x5472f10  starrocks::NullableColumn::append(...)
@          0x72b05d0  starrocks::JoinHashTable::append_chunk(...)
@          0x729a0dc  starrocks::HashJoinBuilder::append_chunk(...)
@          0x728cf58  starrocks::HashJoiner::append_chunk_to_ht(...)
@          0x7360f50  starrocks::pipeline::HashJoinBuildOperator::push_chunk(...)
@          0x735ad70  starrocks::pipeline::SpillableHashJoinBuildOperator::push_chunk(...)
...
```

**Step 3**: Use query_id to find the SQL statement in audit logs or `SHOW PROC '/current_queries'`.

### Find Top N Memory-Consuming SQL (BE)

**During incident**: Check `SHOW PROC '/current_queries'` for `memUsageBytes`.

**After incident**: Sort audit logs by `MemCostBytes`:

```bash
python3 analyze_logs.py "2025-04-15 00:00:00" "2025-04-15 01:00:00" "MemCostBytes" 3 fe.audit.log
```

---

## 2. BE Crash

1. Check core dump file and stack trace.
2. Check `dmesg` for OOM Killer activity.
3. Review `be.WARNING` / `be.ERROR` logs for the last entries before the crash.
4. Check fd limit: `ulimit -n` — increase if necessary.

```bash
dmesg | tail -100
cat /proc/<be_pid>/limits
```

---

## 3. FE Deadlock

### Symptoms

- Queries report `version does not exist` (already recycled on BE)
- Report timestamp has not updated for a long time
- System appears frozen, queries cannot acquire database locks

### Lock Architecture: Fair Lock Principle

StarRocks uses **fair locks** for database locks (`ReentrantReadWriteLock`). In fair mode, lock acquisition follows **first-in-first-out (FIFO)** order.

**Critical insight**: Read locks are NOT always shared. In FIFO order, if a write lock request is queued before read lock requests, those read locks must wait until the write lock is released—even if another thread currently holds a read lock.

Example scenario:
```
Thread1: holds read lock
Thread2: waiting for write lock (queued)
Thread3/4/5: waiting for read lock (queued after Thread2)
```

Thread3/4/5 cannot acquire read locks until Thread2 gets and releases the write lock. This causes read-read lock blocking—a common deadlock pattern in StarRocks.

### Common Deadlock Causes

| Type | Description | Example |
|---|---|---|
| **Inconsistent lock ordering** | Multiple database locks acquired in different order by different threads | Thread A: lock(db1) → lock(db2), Thread B: lock(db2) → lock(db1) |
| **Cross-lock ordering** | Different lock types (TabletInvertedIndex vs Database) acquired inconsistently | ReportHandler holds TabletInvertedIndex, waits for Database; DynamicPartitionThread holds Database, waits for TabletInvertedIndex |
| **Lock upgrade deadlock** | Thread holding read lock attempts to acquire write lock | TabletScheduler holds read lock, then tries write lock |
| **Shared thread pool exhaustion** | Thread pool full of tasks waiting for nested async operations | Hive meta cache: pool full of `loadPartitionStats` waiting for `getPartition` |
| **Long lock hold time** | Lock held during slow operations (complex plan, external system access) | Plan execution blocking; JDBC catalog downloading jars inside lock |

### Historical Deadlock Fixes

| PR | Issue | Fix |
|---|---|---|
| [#29432](https://github.com/StarRocks/starrocks/pull/29432) | Multi-database query lock ordering | Sort databases alphabetically before locking |
| [#29360](https://github.com/StarRocks/starrocks/pull/29360) | Database lock ordering inconsistency | Standardize lock acquisition order |
| [#30703](https://github.com/StarRocks/starrocks/pull/30703) | TabletInvertedIndex vs Database lock | Remove db lock check in tabletReport |
| [#32803](https://github.com/StarRocks/starrocks/pull/32803) | MV refresh lock ordering | Move SQL planning outside database lock |
| [#34237](https://github.com/StarRocks/starrocks/pull/34237) | TabletScheduler lock upgrade | Remove db lock when deleting CLONE replica |
| [#35736](https://github.com/StarRocks/starrocks/pull/35736) | MV nested lock issue | Plan execution moved outside database lock |
| [#15619](https://github.com/StarRocks/starrocks/pull/15619) | Long plan execution | Remove database lock requirement for planning |
| [#34272](https://github.com/StarRocks/starrocks/pull/34272) | External system access in lock | JDBC jar download outside lock |

---

### Investigation Methods

#### Method 1: jstack + top -Hp Analysis

**Step 1**: Capture jstack and top output

```bash
jstack -l <fe_pid> > jstack.txt
top -Hp <fe_pid> > top_output.txt
```

**Step 2**: Search for blocked threads

```bash
grep "parking to wait for" jstack.txt
```

Find threads waiting for locks. The output shows the lock address (e.g., `0x0000000753f065a0`).

**Step 3**: Find the lock holder

Search for the lock address in `Locked ownable synchronizers` section:

```bash
grep -A 5 "Locked ownable synchronizers" jstack.txt | grep "0x0000000753f065a0"
```

**Step 4**: Identify long-running threads

Convert thread ID from `top -Hp` to hex (e.g., 19700 → 0x4cf4), then search jstack:

```bash
printf "%x\n" 19700  # Output: 4cf4
grep "nid=0x4cf4" jstack.txt
```

---

#### Method 2: DeadLockChecker (Built-in Detection)

**Version requirements**: 2.5.15+, 3.0.9+, 3.1.6+, 3.2.0+

**Step 1**: Search fe.log for deadlock detection output

```bash
# Version 3.3+
grep "LockManager" fe.log

# Version 3.2 and earlier
grep "DeadlockChecker" fe.log
```

**Step 2**: Parse the JSON output

The DeadLockChecker outputs structured JSON with:
- `lockDbName`: Database name
- `lockState`: `readLocked` or `writeLocked`
- `slowReadLockCount`: Number of long-held read locks (threshold: `slow_lock_threshold_ms`, default 3000ms)
- `lockHoldTime`: Write lock hold duration (ms)
- `threadInfo`: Stack trace of lock holder
- `lockWaiters`: Threads waiting for this lock

**Step 3**: Identify circular wait

Match `threadInfo` thread IDs against other locks' `lockWaiters`. If thread A appears in lock B's waiters while thread B appears in lock A's waiters → circular wait detected.

Example:
```json
[
  {
    "lockDbName": "db_coinbon_app",
    "lockState": "readLocked",
    "threadInfo": "dump thread: thrift-server-pool-832912, id: 2553542...",
    "lockWaiters": [{"threadId": 2551355, "threadName": "pool-21-thread-1240"}]
  },
  {
    "lockDbName": "dws",
    "lockState": "readLocked",
    "threadInfo": "dump thread: pool-21-thread-1240, id: 2551355...",
    "lockWaiters": [{"threadId": 2553542, "threadName": "thrift-server-pool-832912"}]
  }
]
```

Thread 2553542 holds `db_coinbon_app`, waits for `dws`. Thread 2551355 holds `dws`, waits for `db_coinbon_app`. → **Circular deadlock**.

---

### Quick Actions

1. Capture multiple jstack dumps for analysis
2. Restart FE to restore service
3. Identify deadlock pattern from jstack/DeadLockChecker output
4. Check version against historical fixes table
5. Submit findings to engineering for code-level fix

```bash
# Quick jstack capture
jstack <fe_pid> > /tmp/fe_jstack.log
# Search for blocked threads
grep -A 20 "BLOCKED\|TIMED_WAITING" /tmp/fe_jstack.log
```

---

## 4. FE Memory Issues

1. Check `fe.gc.log` for Full GC frequency and pause duration.
2. Use Memory Allocated Profile flame graphs for analysis.
3. Enable profiler in FE config:
   ```
   proc_profile_cpu_enable = true
   proc_profile_collect_interval_s = 10
   ```
4. Review MemoryUsageTracker logs for per-module memory breakdown.

---

## 5. FE Heap Memory Troubleshooting

### Sudden Heap Memory Surge

**v3.3.6+**: memory profiles auto-generated as `.tgz` HTML flame graphs in `fe/log/proc_profile/`.

**v3.3.5 and below** — enable in `fe.conf`:

```
proc_profile_cpu_enable = false
proc_profile_collect_interval_s = 300
```

Or run a profiler script under the `fe` directory:

```bash
#!/bin/bash
mkdir -p mem_alloc_log
while true; do
    current_time=$(date +'%Y-%m-%d-%H-%M-%S')
    file_name="mem_alloc_log/alloc-profile-${current_time}.html"
    ./bin/profiler.sh -e alloc --alloc 2m -d 300 -f "$file_name" $(cat bin/fe.pid)
done
```

### Slow Memory Growth (Potential Leak)

v3.3.7+ includes **Memory Usage Tracker** — logs per-module memory consumption to identify
accumulation sources.

### FE OOM Quick Fixes

- Increase JVM heap in `fe.conf` (`-Xmx`).
- Add `-XX:-OmitStackTraceInFastThrow` for full stack traces on NullPointerException.
- Check `fe.gc.log` for Full GC patterns.
- Planner timeout (`planner use long time`): spread load across FEs or increase heap to 16GB+.

### Precisely Locate SQL Causing FE OOM

When FE shuts down due to OOM, it prints currently running queries. Search `fe.WARNING` for:

```bash
grep "FE ShutDown! Running Query" fe.WARNING
```

The output shows running queries with their `QueryFEAllocatedMemory` to identify the memory-heavy one.

### Find Top N Memory-Consuming SQL (FE)

**After incident**: Sort audit logs by `QueryFEAllocatedMemory`:

```bash
python3 analyze_logs.py "2025-04-15 00:00:00" "2025-04-15 01:00:00" "QueryFEAllocatedMemory" 3 fe.audit.log
```

**During incident**: Use `SHOW PROC '/current_queries'` to view current queries' FE memory usage.

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| BE OOM during ingestion | Memory tracker leak; oversized PK index in memory | Upgrade to fixed version; enable persistent index |
| BE crashed without OOM in dmesg | Internal segfault; check core dump | Capture stack; submit to engineering |
| FE Full GC every minute | Heap too small or memory leak | Increase `-Xmx`; check Memory Usage Tracker |
| `version does not exist` errors | FE deadlock blocking tablet report | jstack + restart FE; check DeadLockChecker output |
| FE deadlock - circular wait | Inconsistent database lock ordering | Check version against historical fixes (#29432, #29360) |
| FE deadlock - cross-lock | TabletInvertedIndex vs Database lock ordering | Upgrade to version with fix (#30703) |
| FE deadlock - lock upgrade | Thread holds read lock, tries write lock | Check TabletScheduler fixes (#34237) |
| FE deadlock - thread pool | Shared pool exhausted by nested async tasks | Check Hive meta cache handling |
| FE OOM after long uptime | Slow leak in metadata or task scheduler | Capture allocation profile; report to engineering |

---

## Related Cases

- `case-003-fe-deadlock` — LockManager deadlock blocking ReportHandler
- `case-007-memory-tracking-leak` — known memory tracker leak slowing imports
- `case-008-be-oom` — publish timeout caused by BE OOM cascade

---

## Resources

- [FE Memory FAQ](https://docs.starrocks.io/docs/faq/fe_mem_faq/)
