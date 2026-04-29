---
type: skill
category: query
priority: 1
keywords: [query hang, slow query, profile, scan, join, data skew, runtime filter, low cardinality]
---

# 01 - Query Troubleshooting

Investigation guide for query hangs, slow queries, profile analysis, scan performance,
join performance, and bug localization.

---

## 1. Query Hangs at Client

Follow these steps in order. Confirm each before moving to the next.

### Step 1: Did the FE receive the request?

Search FE logs for `register query id`:

```bash
grep "register query id" fe.log
```

If the target query ID is found, FE received the request — skip to Step 3.

### Step 2: Check network connection queues

If FE didn't receive the request, check for accept queue overflow:

```bash
netstat -s | grep -i LISTEN
netstat -s | grep TCPBacklogDrop
cat /proc/sys/net/ipv4/tcp_abort_on_overflow
```

Fix:
- Set `tcp_abort_on_overflow` to 1
- Increase `somaxconn` (at least 1024)
- Adjust FE parameters: `mysql_nio_backlog_num`, `http_backlog_num`, `thrift_backlog_num` (must be greater than or equal to `somaxconn`)
- Restart FE

### Step 3: Did the BE receive the request?

Search BE logs for `Prepare(): query_id=<target_query_id>`.
If found, skip to Step 6. Otherwise continue to Step 4.

### Step 4: Is the FE stuck on a lock?

Capture FE stack trace with jstack and search for `ConnectProcessor`:

```bash
jstack <fe_pid> > /tmp/fe_jstack_$(date +%s).log
grep -A 30 "ConnectProcessor" /tmp/fe_jstack_*.log
```

- Multiple threads waiting on the same lock means a slow thread (high probability)
- Two threads waiting on each other means deadlock (low probability)

Action: capture multiple jstack dumps, then restart FE.

### Step 5: Is the FE stuck in Full GC?

Check `fe.gc.log` around the problem timestamp. Review GC monitoring dashboards.
Action: tune GC parameters and restart FE.

### Step 6: Where is the BE stuck?

Use pstack / strace to identify the blocking point:

```bash
pstack <be_pid> > /tmp/be_pstack_$(date +%s).log
```

### Step 7: Is the execution thread pool exhausted?

Quick validation: run `select 1 + 1;` (generates a union node with no Scan).
If it returns normally, the execution pool is not full; the issue is likely in the Scan thread pool.

### Step 8: Are large queries saturating BE resources?

Check:
- BE CPU / memory / IO utilization is very high
- `SHOW PROC '/current_queries';` shows many long-running queries
- `query_timeout` is set too large (several minutes or more)

Action: `KILL` slow queries or restart the overloaded BE node.

---

## 2. Slow Query Investigation

1. Profile first — compare operator-level timings, focus on row counts and time distribution.
2. Check tablet versions — version accumulation from imports slows down scans.
3. Low-cardinality optimization disabled — if expressions plus AGG exist but expression time is unchanged, low-cardinality optimization may be inactive.
4. Lock contention — if expressions are extremely slow and more parallelism doesn't help, suspect lock issues.
5. CPU contention — check if heavy import workloads are competing with queries.

### Finding Large / High-Memory Queries

```bash
# Find slowest queries in audit log
grep 'slow_query' fe.audit.log | cut -d '=' -f 6 | cut -d '|' -f 1 | sort -g

# Find large memory allocations in BE log (query_id included)
grep "large memory alloc" be.WARNING
# Trace: query_id -> find SQL in fe.audit.log

# Or use analyze_logs.py for TOP N memory consumers
python3 analyze_logs.py "2025-04-15 00:00:00" "2025-04-15 01:00:00" "MemCostBytes" 3 fe.audit.log
```

### Profile Time Discrepancy Analysis

When total Profile time significantly exceeds BE Active time:

1. Check `fe.warn.log` for retry logs.
2. Primary Key model (older versions): lock acquisition timeout — look for long gap between prepare and open.
3. Optimizer too slow — verify with `explain`; or jstack to see if stuck in plan generation.
4. Import lock interference — import holds DB lock, blocking query lock acquisition.
5. FE Full GC — check `fe.gc.log` timestamps.

---

## 3. Scan Performance Analysis

### Profile OLAP_SCAN_NODE Analysis

Enable profile reporting, then analyze the OLAP_SCAN_NODE:

```sql
SET is_report_success = true;
-- Run query, then check profile on FE master HTTP UI: http://<fe_ip>:8030 -> Queries -> Profile
```

Key metrics in OLAP_SCAN_NODE to check:

| Metric | Meaning |
|---|---|
| `BytesRead` | Data volume read from tablets. Too large or too small suggests tablet sizing issues. |
| `RowsReturned` | Rows returned after filtering. If BytesRead is large but RowsReturned is small, consider making filter columns sort keys. |
| `RowsReturnedRate` | Per-node return rate. If one node is significantly slower, check disk I/O, CPU, or memory on that node. |
| `TabletCount` | Number of tablets scanned. Related to bucket settings — too many or too few indicates misconfiguration. |
| `MERGE (aggr/union/sort)` | If MERGE time is high, the bottleneck is in rowset merging. Common for Aggregate/Unique tables with insufficient compaction. |
| `IOTime` | Disk I/O time. Correlates with MERGE and data volume. |
| `PushdownPredicates` | Number of predicates pushed down to storage layer. |
| `RawRowsRead` | Total raw rows read before filtering. |
| `ZoneMapIndexFilterRows` / `BloomFilterFilterRows` / `BitmapIndexFilterRows` | Rows filtered by indexes. Low values suggest missing or ineffective indexes. |
| `PredFilter` / `PredFilterRows` | Rows filtered by predicates at storage layer. |

### Data Skew Detection

Compare `Active` times across multiple OLAP_SCAN_NODE (id=X) instances in the profile.
If one instance takes 10x longer than others, data skew is likely:

```
OLAP_SCAN_NODE (id=0):(Active: 4m50s)  <- skewed
OLAP_SCAN_NODE (id=0):(Active: 250ms)
OLAP_SCAN_NODE (id=0):(Active: 131ms)
```

Diagnosis steps:

1. Run `SHOW TABLET FROM <table>` and check `DataSize` distribution across tablets.
2. Use a tablet health analysis tool (see `tools/01-diagnostic-commands.md`).
3. Check standard deviation — if abnormally high, the bucket key selection is poor.

Fix: change the bucket key to a column with higher cardinality and more even distribution.
Use `ALTER TABLE ... DISTRIBUTED BY HASH(new_key)` (v3.3+).

### Predicate Pushdown Failures

If partition/bucket pruning or predicate pushdown is not working, check:

1. Type mismatch — filter column type doesn't match the table column type.
2. Functions on the left side — e.g., `WHERE date_format(dt, '%Y%m') = '202301'` prevents pushdown; use `WHERE dt BETWEEN '2023-01-01' AND '2023-01-31'` instead.

---

## 4. Join Performance Analysis

### Join Types

| Join Type | Mechanism | When Used |
|---|---|---|
| Broadcast Join | Right table sent to all left table nodes | Right table is small |
| Shuffle Join | Both tables shuffled by join key | Both tables are large |
| Colocate Join | Local join, no network transfer | Tables share colocate group with same bucket key |
| Bucket Shuffle Join | Only right table shuffled to left table nodes | Join column is left table's bucket key |
| Replicated Join | Right table replicated on every BE | Right table replica count equals BE count |

### Diagnosing Join Bottlenecks

In the profile, check `HASH_JOIN_NODE`:

- `BuildTime`: time to build hash table from right table. If high, right table may be too large.
- `ProbeTime`: time to probe hash table. If high, left table may be too large or hash collisions.
- `BuildRows`: row count in hash table. If very large, consider using Shuffle instead of Broadcast.

Common issues:

1. Large table on right side with Broadcast — EXCHANGE node time is huge. Use `[broadcast]` hint to swap tables, or `[shuffle]` hint.
2. Two similar-sized tables using Broadcast — try `[shuffle]` hint.
3. Missing statistics — check with `SELECT * FROM _statistics_.table_statistic_v1 WHERE table_name LIKE '%table_name'`. If empty, run `ANALYZE TABLE`.

### Join Hints

```sql
-- Force broadcast (put small table on right)
SELECT a.x, b.y FROM large_table a JOIN [broadcast] small_table b ON a.id = b.id;

-- Force shuffle join
SELECT a.x, b.y FROM table_a a JOIN [shuffle] table_b b ON a.id = b.id;

-- Colocate join (requires same colocate_with group and same bucket key)
CREATE TABLE t1 (...) DISTRIBUTED BY HASH(id) PROPERTIES ("colocate_with" = "group1");
CREATE TABLE t2 (...) DISTRIBUTED BY HASH(id) PROPERTIES ("colocate_with" = "group1");
```

### RuntimeFilter

RuntimeFilter pre-filters left table data before the join. Check OLAP_SCAN_NODE for `JoinRuntimeFilter*` metrics:

- `JoinRuntimeFilterEvaluate`: number of RuntimeFilters applied.
- `JoinRuntimeFilterInputRows` / `OutputRows`: rows before/after filter. Large reduction means the filter is effective.
- `JoinRuntimeFilterTime`: time spent on RuntimeFilter evaluation.

If RuntimeFilter is not taking effect, check whether statistics are collected and CBO is enabled.

### Best Practices

- Use `INT`, `DATE` types for join keys (faster than VARCHAR).
- Add WHERE filters before joins to reduce data volume.
- Use Colocate Join for large table joins when possible.
- Ensure statistics are collected for CBO optimizer.

---

## 5. Query Bug Localization (Engineer-Level)

### General Approach

1. Try to reproduce — collect core stack trace, `EXPLAIN COSTS`, statistics (Query Dump), Profile.
2. If not reproducible — reason from stack traces; diff code changes between versions; suspect immature features first.

### Quick Exclusion Switches

Disable features via session variables to narrow scope:

| Feature | How to disable |
|---|---|
| Low-cardinality optimization | `SET cbo_enable_low_cardinality_optimize = false;` |
| Pipeline engine | `SET enable_pipeline_engine = false;` |
| Expression pushdown to storage | `SET enable_column_expr_predicate = false;` |
| Replication Join | `SET cbo_enable_replicated_join = false;` |
| Local Runtime Filter | `SET hash_join_push_down_right_table = 0;` |
| Global Runtime Filter | `SET enable_global_runtime_filter = false;` |
| Streaming pre-aggregation | `SET streaming_preaggregation_mode = force_preaggregation;` |
| Concurrent plan serialization | `SET enable_plan_serialize_concurrently = false;` |

### Common Bug Causes by Module

**Optimizer**: Nullable info incorrect, Cast type mismatch, predicate lost or pushed incorrectly,
Limit lost, single-phase aggregation used incorrectly, Decimal V3 bugs, View-to-SQL conversion issues.

**Scheduler**: Related to Bucket Shuffle Join / Colocate Join / Replication Join — disable
these and verify with Broadcast/Shuffle Join.

**Executor — Scan**: Delete handling errors, ZoneMap filtering errors, Char type
storage/compute length mismatch, Chunk size exceeds limit.

**Executor — Aggregate**: Streaming processing errors (check `convert_to_serialize_format`),
Nullable signature mismatch.

**Executor — Join**: Runtime Filter processing errors, Hash Distribution issues
(symptom: unstable results).

### 9-Setting Crash Quick Disable

When queries crash the BE (v3.5+), use binary exclusion to isolate the culprit:

```sql
SET disable_join_reorder = true;
SET enable_global_runtime_filter = false;
SET enable_query_cache = false;
SET cbo_enable_low_cardinality_optimize = false;
SET cbo_cte_reuse_rate = 0;
SET enable_filter_unused_columns_in_scan_stage = false;
SET GLOBAL enable_pipeline_event_scheduler = false;
SET GLOBAL enable_push_down_pre_agg_with_rank = false;
SET GLOBAL enable_partition_hash_join = false;
-- For materialized view issues:
SET enable_sync_materialized_view_rewrite = false;
```

Collect for engineering: table DDL, `EXPLAIN COSTS` plan, query dump.

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| Scan node slow on a single instance | Data skew on a hot bucket key | Re-bucket with higher cardinality column |
| MERGE phase dominates scan time | Too many rowsets per tablet | Tune compaction; reduce import frequency |
| Broadcast join blows up memory | Right table too large | Use `[shuffle]` hint |
| RuntimeFilter not active | Missing statistics or CBO disabled | `ANALYZE TABLE`; enable CBO |
| `version does not exist` mid-query | FE deadlock blocked tablet report; BE recycled versions | Capture jstack, restart FE |

---

## Related Cases

- `case-014-scan-skew` — bucket key optimization on aggregate model
- `case-015-memory-volatility` — session-level timeout override
- `case-003-fe-deadlock` — FE LockManager deadlock causing version-not-found

---

## Resources

- [SQL FAQ](https://docs.starrocks.io/docs/faq/Sql_faq/)
- [Query Cache documentation](https://docs.starrocks.io/docs/using_starrocks/query_cache/)
