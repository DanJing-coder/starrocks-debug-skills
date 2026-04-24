---
name: starrocks-debug
description: >
  StarRocks cluster diagnostics and troubleshooting skill. Covers slow queries, query hangs,
  import failures/timeouts, BE crash/OOM, FE deadlocks/GC, RPC timeouts, compaction anomalies,
  data lake external table errors, and more. Use this skill whenever the user mentions debug, troubleshoot,
  diagnose, root cause analysis, error analysis, slow query, import failure, OOM, crash, rpc failed,
  timeout, compaction score, tablet error, query hang, publish timeout, jstack, pstack, profile analysis,
  on-call issues, or production incidents. Even if the user only vaguely describes a StarRocks anomaly
  (e.g. "the cluster is slow", "some tasks are failing", "a node went down"), this skill should be
  triggered to provide systematic troubleshooting guidance.
---

# StarRocks Diagnostics & Troubleshooting Skill

## Core Principles

1. **Restore service in 10 minutes, identify root cause within hours** — Stop the bleeding first, then investigate.
2. **Top-down, layer by layer** — Start from the symptom and narrow down: Client → FE → BE/CN → Storage/Network.
3. **Data-driven decisions** — Every step must be backed by logs, metrics, profiles, or stack traces.
4. **Document the investigation** — Preserve log snippets, outputs, and parameter changes for post-mortem.

---

## Pre-Investigation Checklist

- **Cluster version** (StarRocks version)
- **Deployment architecture** (shared-data vs. shared-nothing, node count)
- **Symptom details** (full error message, timestamp, reproducibility)
- **Recent changes** (upgrades, parameter tuning, schema changes)
- **Monitoring snapshots** (CPU/memory/IO/network metrics)

---

## Problem Routing

| Symptom Category | Keywords | Index |
|---|---|---|
| Query issues | hang, slow, profile, scan, join, skew | [skills/_index.md](skills/_index.md) → 01-query |
| Import issues | timeout, RPC failed, publish, broker load | [skills/_index.md](skills/_index.md) → 02-import |
| Node issues | crash, OOM, deadlock, GC | [skills/_index.md](skills/_index.md) → 03-node |
| Materialized view | refresh, timeout, rewrite | [skills/_index.md](skills/_index.md) → 04-materialized-view |
| Data lake | HMS, Kerberos, external table | [skills/_index.md](skills/_index.md) → 05-data-lake |
| Shared-data | DataCache, S3, leader switch | [skills/_index.md](skills/_index.md) → 06-shared-data |
| Tablet | health, balance, skew, compaction | [skills/_index.md](skills/_index.md) → 07-tablet |
| Deployment | startup, port, BDB, JDK | [skills/_index.md](skills/_index.md) → 08-deployment |
| High concurrency | QPS, connection pool, cache | [skills/_index.md](skills/_index.md) → 09-high-concurrency |
| Resource isolation | resource group, queue, blacklist | [skills/_index.md](skills/_index.md) → 10-resource-isolation |

---

## Quick Diagnosis Commands

```sql
-- Cluster status
SHOW BACKENDS;
SHOW FRONTENDS;
SHOW PROC '/current_queries';
SHOW LOAD;
```

```bash
# Log search
grep "<query_id>" fe.log
grep "<instance_id>" be.INFO
grep -E "ERROR|WARN" fe.log | tail -100
```

```bash
# Stack trace
jstack <fe_pid> > /tmp/fe_jstack.log
pstack <be_pid> > /tmp/be_pstack.log
```

---

## Emergency Mitigation

```sql
-- Disable statistics collection
ADMIN SET FRONTEND CONFIG("enable_statistic_collect"="false");

-- Increase RPC timeout
ADMIN SET FRONTEND CONFIG("brpc_send_plan_fragment_timeout_ms"="180000");

-- Disable all imports
ADMIN SET FRONTEND CONFIG("disable_load_job"="true");
```

---

## Investigation Patterns

1. **Log trace chain**: label → txn_id → query_id → instance_id → thread_id
2. **Stack comparison**: Multiple jstack/pstack — unchanged threads = blocked
3. **Binary exclusion**: Disable features one at a time via session variables
4. **Monitoring correlation**: Correlate timestamp with Grafana metrics
5. **Cache invalidation**: "file not found" but file exists → suspect cache

---

## Resources

- [Skills Index](skills/_index.md) — Troubleshooting guides per category
- [Cases Index](cases/_index.md) — Real-world case studies
- [Tools Index](tools/_index.md) — Diagnostic utilities
- [CONTRIBUTING.md](CONTRIBUTING.md) — How to add new content