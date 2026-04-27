---
type: skill
category: node
priority: 3
keywords: [BE crash, BE OOM, FE deadlock, FE Full GC, FE heap memory, memory tracker]
---

# 03 - Node Troubleshooting (BE Crash / OOM, FE Deadlock / GC)

Investigation guide for BE-level crashes and out-of-memory events, FE deadlocks,
Full GC pauses, and FE heap memory analysis.

---

## 1. BE OOM

1. Check query memory usage: `SHOW PROC '/current_queries';`
2. Search BE logs for `PeakMemoryUsage` to find high-memory queries.
3. Check for known memory tracking leak issues.
4. Review `mem_limit` and memory pool configurations.

```bash
# Per-module memory breakdown
curl -s http://<BE_IP>:<BE_HTTP_PORT>/mem_tracker
curl -s http://<BE_IP>:<BE_HTTP_PORT>/metrics | grep "^starrocks_be_.*_mem_bytes"

# tcmalloc status
curl -s http://<BE_IP>:<BE_HTTP_PORT>/memz

# Find high-memory queries in BE log
grep "PeakMemoryUsage" be.INFO | sort -t= -k2 -h
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

Symptoms: queries report `version does not exist` (already recycled on BE);
Report timestamp has not updated for a long time.

Investigation:

```bash
jstack <fe_pid> > /tmp/fe_jstack.log
# Search for BLOCKED or TIMED_WAITING threads
grep -A 20 "BLOCKED\|TIMED_WAITING" /tmp/fe_jstack.log
```

Common pattern: `ReportHandler` blocked on `LockManager.lock` for the database lock,
preventing tablet report processing. BE recycles old versions while FE is unaware.

Action: capture multiple jstack dumps, restart FE, submit to engineering for code analysis.

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

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| BE OOM during ingestion | Memory tracker leak; oversized PK index in memory | Upgrade to fixed version; enable persistent index |
| BE crashed without OOM in dmesg | Internal segfault; check core dump | Capture stack; submit to engineering |
| FE Full GC every minute | Heap too small or memory leak | Increase `-Xmx`; check Memory Usage Tracker |
| `version does not exist` errors | FE deadlock blocking tablet report | jstack + restart FE |
| FE OOM after long uptime | Slow leak in metadata or task scheduler | Capture allocation profile; report to engineering |

---

## Related Cases

- `case-003-fe-deadlock` — LockManager deadlock blocking ReportHandler
- `case-007-memory-tracking-leak` — known memory tracker leak slowing imports
- `case-008-be-oom` — publish timeout caused by BE OOM cascade

---

## Resources

- [FE Memory FAQ](https://docs.starrocks.io/docs/faq/fe_mem_faq/)
