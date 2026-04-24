---
type: readme
description: StarRocks cluster diagnostics and troubleshooting skill
---

# starrocks-debug

StarRocks cluster diagnostics and troubleshooting skill.

## Overview

This skill systematizes troubleshooting experience to help provide structured investigation guidance for cluster issues, covering common production problems with complete investigation paths from symptom to root cause.

## Coverage

| Category | Typical Issues |
|---|---|
| Query issues | Query hang, slow queries, profile analysis, scan performance, join optimization, data skew |
| Import issues | Slow/timed-out imports, Broker Load backlog, RPC Failed, Publish Timeout, Primary Key tuning |
| Materialized views | Refresh failures, timeouts, inactive state, query rewrite failures |
| Node issues | BE Crash, BE OOM, FE deadlock, FE Full GC, memory volatility |
| Query governance | SQL blacklist, resource groups, big query circuit breaking |
| Resource isolation | Resource groups, query queues, concurrency limits, memory limits |
| Data lake issues | HMS connection, Kerberos, HDFS/S3 access errors, external table errors |
| Shared-data issues | DataCache corruption, S3 rate limiting, FE leader switch bugs |
| Tablet governance | Tablet health/balance, bucket optimization, data skew |
| Deployment issues | FE/BE startup failures, port conflicts, BDB conflicts |
| High concurrency | Primary key optimization, Query Cache, pipeline_dop, connection pooling |

## File Structure

```
starrocks_debug_skills/
├── README.md           # This file
├── LICENSE             # Apache 2.0
├── SKILL.md            # Main skill entry point
├── CONTRIBUTING.md     # How to add content
├── skills/
│   └── _index.md       # Skills index + templates
├── cases/
│   ├── _index.md       # Cases index + templates
│   └── <category>/     # Case subdirectories
└── tools/
    └── _index.md       # Tools index + templates
```

## Core Methodology

**"Restore in 10 minutes, root-cause within hours"**

1. **Top-down investigation** — Client → FE → BE → Storage/Network
2. **Data-driven** — Backed by logs, metrics, stack traces
3. **Mitigate first** — Service recovery via parameter tuning
4. **Binary exclusion** — Disable features via session variables

## Trigger Conditions

Triggered when conversation contains:
- Investigation terms: debug, troubleshoot, diagnose, root cause
- Symptoms: slow query, import failure, OOM, crash, timeout, hang
- Tool terms: jstack, pstack, profile, Grafana

## Maintenance

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add:
- New skills → `skills/<number>-<category>.md`
- New cases → `cases/<category>/case-<number>-<name>.md`
- New tools → `tools/<number>-<name>.md`