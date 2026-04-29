---
type: skill
category: materialized-view
priority: 4
keywords: [MV refresh, MV timeout, MV inactive, query rewrite, sync MV, async MV]
---

# 04 - Materialized View Troubleshooting

Investigation guide for async MV refresh failures, refresh timeouts, MV inactivation,
query rewrite failures, and sync MV optimization.

---

## 1. Diagnostic Commands

For comprehensive MV diagnostic SQL queries, see [tools/03-mv-diagnostic-sql.md](../tools/03-mv-diagnostic-sql.md).

```sql
-- Check MV state (is_active, last_refresh_state, last_refresh_error_message)
SHOW MATERIALIZED VIEWS;

-- View refresh history
SELECT * FROM information_schema.task_runs WHERE task_name = 'mv-<mv_id>' \G

-- Monitor resource consumption during refresh
SHOW PROC '/current_queries' \G

-- Analyze refresh profile after completion
ANALYZE PROFILE FROM '<profile_id>';

-- Verify query rewriting (look for "SCAN [mv_name]" in output)
EXPLAIN LOGICAL SELECT ...;

-- Trace rewrite failures (v3.2+)
TRACE LOGS MV SELECT ...;
TRACE REASON MV SELECT ...;
```

---

## 2. Common Issues

### Refresh failure — memory exhaustion

```sql
-- Enable spill to disk
ALTER MATERIALIZED VIEW mv1 SET ('session.enable_spill' = 'true');
```

### Refresh timeout (default 5 min pre-v3.2, 1 hour v3.2+)

```sql
ALTER MATERIALIZED VIEW mv1 SET ('session.insert_timeout' = '4000');
```

### MV becomes inactive

```sql
ALTER MATERIALIZED VIEW mv1 ACTIVE;
-- If ineffective, drop and recreate
```

### Excessive resource usage — emergency stop

```sql
ALTER MATERIALIZED VIEW mv1 INACTIVE;
-- OR
CANCEL REFRESH MATERIALIZED VIEW mv1;
```

### Query rewrite not working — common causes

- Nested aggregation unsupported.
- Join + aggregation unsupported.
- MV is inactive or data is stale.
- Filtering columns not included in MV SELECT.

Fix staleness tolerance:

```sql
ALTER MATERIALIZED VIEW mv1 SET ('query_rewrite_consistency' = 'LOOSE');
ALTER MATERIALIZED VIEW mv1 SET ('mv_rewrite_staleness_second' = '5');
```

---

## 3. MV Resource Group

Default resource group `default_mv_wg` has `cpu_core_limit=1`. Assign a custom group for
heavy refreshes:

```sql
CREATE MATERIALIZED VIEW mv1 REFRESH MANUAL
PROPERTIES ("resource_group" = "rg_mv")
AS ...;
```

---

## 4. Sync Materialized View Optimization

### Supported Scenarios

Sync materialized views (on Duplicate/Aggregate models only) support:

- **Pre-aggregation**: `sum`, `min`, `max`, `count`, `bitmap_union`, `hll_union`.
- **Column reorder**: change sort key prefix for different query patterns.

### Verifying MV Hit

```sql
-- Check via EXPLAIN
EXPLAIN SELECT ... FROM table;
-- Look for "Rollup: <mv_name>" (not the base table name)
-- Check PREAGGREGATION: ON = storage layer returns pre-aggregated data
```

In Profile, check `OLAP_SCAN_NODE`:

- `Rollup: <mv_name>` confirms MV was used.
- Compare `BytesRead`, `RowsRead` before/after MV creation.

### Performance Impact Example

SSB 1TB benchmark: `SELECT date, SUM(qty) FROM lineorder_flat GROUP BY date`.

- Without MV: 27.61s (scanned 6.79GB, 1.4B rows).
- With MV: 0.96s (scanned 488KB, 100K rows) — about 29x speedup.

---

## 5. Operational Pitfalls

### Non-deterministic functions in MV definitions

Functions like `current_date()` cause invalid rewrite plans. Replace with stable expressions
or recreate the MV with a constant cutoff column.

### FE restart impact on schedule persistence

A daily FE restart can break MV schedule persistence — the scheduler re-registers tasks
with the wrong `initialDelay`, skipping the next scheduled run. Mitigation:

- Ensure FE uptime covers at least one full scheduling cycle.
- Increase `task_runs_concurrency` when async task queue grows large.
- Track this as a known limitation pending persistent scheduler metadata.

### S3 rate limiting during refresh

Symptom: refresh fails with `503: Please reduce your request rate`.
See `skills/06-shared-data.md` for rate-limit mitigation (`num_partitioned_prefix`, etc.).

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| Refresh times out at default | Pre-v3.2 default of 5 min | Set `session.insert_timeout` |
| MV inactivated unexpectedly | Base table schema change | `ALTER MATERIALIZED VIEW ... ACTIVE` |
| Query rewrite not used | Nested agg, missing filter columns, staleness | Set `LOOSE` consistency; rewrite the MV |
| Refresh hits OOM | Spill not enabled | Enable spill to disk |
| `SHOW TABLETS` fails inside MV refresh | Ephemeral role context missing | Run as a stable user/role |

---

## Related Cases

- `case-012-mv-refresh-failures` — multi-cause MV refresh investigation including S3 rate limiting

---

## Resources

- [Troubleshooting Asynchronous Materialized Views](https://docs.starrocks.io/docs/using_starrocks/async_mv/troubleshooting_asynchronous_materialized_views/)
