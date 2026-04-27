---
type: skill
category: high-concurrency
priority: 9
keywords: [high QPS, connection pool, PreparedStatement, query cache, pipeline_dop, primary key, short circuit]
---

# 09 - High-Concurrency Best Practices

Investigation and tuning guide for high-QPS workloads: data modeling, primary-key
optimization, query cache, pipeline parallelism, connection pooling, and emergency
load disabling.

---

## 1. Data Modeling for High QPS

**Partition + Sort Key + Bucket Key synergy:**

- **Partition key**: always use a time column; ensures partition pruning via `WHERE event_time >= ...`.
- **Sort key**: put highest-frequency equality filter columns first (e.g., `user_id`).
- **Bucket key**: use the query's ID column as bucket key for bucket pruning
  (`WHERE order_id = 12345` scans only one tablet).

---

## 2. Primary Key Model Optimizations

- **Persistent primary key index** (v3.1+): `"enable_persistent_index" = "true"` — moves index from memory to SSD.
- **Hybrid row-column storage**: `"storage_type" = "column_with_row"` — adds row store for single-row point queries.
- **Short-circuit read**: `SET enable_short_circuit = true` — bypasses execution engine for PK point queries.
  Verify with `EXPLAIN`: look for `Short Circuit Scan: true`.

---

## 3. Query Cache

Cache intermediate aggregation results per-tablet to skip repeated scans:

```sql
SET [GLOBAL] enable_query_cache = true;
-- Or per-query:
SELECT /*+ SET_VAR(enable_query_cache=true) */ ...
```

**BE config**: `query_cache_capacity` (default 512MB), `query_cache_entry_max_bytes`,
`query_cache_entry_max_rows`.

**Limitations**: not effective with Shuffle before aggregation, high-cardinality `GROUP BY`,
or low cache hit rates.

**Monitoring**: `http://<be_host>:<be_http_port>/api/query_cache/stat` or Prometheus metric
`starrocks_be_query_cache_hit_ratio`.

---

## 4. Architecture Tuning

- **FE load balancing**: deploy 3+ FEs behind Nginx/HAProxy TCP load balancer on port 9030.
- **`pipeline_dop = 1`**: critical for high QPS. Reduces CPU scheduling overhead by running
  each query single-threaded. System QPS increases several times.
  ```sql
  SET GLOBAL pipeline_dop = 1;
  ```
- **Connection pools**: mandatory. Use HikariCP or Druid.
- **PreparedStatement**: use `useServerPrepStmts=true` in JDBC URL to cache execution plans
  in FE, skipping SQL parsing overhead.
  ```
  jdbc:mysql://<fe_ip>:9030/<db>?useServerPrepStmts=true
  ```

---

## 5. Pipeline Parallelism Reference

**Queries (pipeline engine enabled):**

- `< 2.3`: Pipeline not available; parallelism controlled by `parallel_fragment_exec_instance_num`.
- `2.3`: when `pipeline_dop = 0`, system auto-tunes; when `pipeline_dop != 0`, both
  `parallel_fragment_exec_instance_num` and `pipeline_dop` take effect.
- `>= 2.4`: `parallel_fragment_exec_instance_num` forced to 1; `pipeline_dop = 0` auto-sets to `vCPUs/2`.

**INSERT INTO (pipeline engine):**

- `2.4`: only uses pipeline when `parallel_fragment_exec_instance_num = 1`; forces `pipeline_dop = 1`.
- `2.5+`: `enable_adaptive_sink_dop = true` uses `pipeline_dop` session variable; `false` uses
  `parallel_fragment_exec_instance_num`.

**High-concurrency tuning**: set parallelism to 1 (`pipeline_dop = 1`); increase
`max_user_connections` (default 100, set to 1000+).

---

## 6. Memory Volatility — Hidden Session Overrides

Symptom: BE memory drops sharply across the cluster, some BEs OOM-restart, query failure
spikes, but the documented `query_timeout` policy looks fine.

Investigation pattern:

1. Sort "All Queries" by execution time — look for outliers running for hours.
2. Verify session-level overrides: search FE logs for `query_timeout` keyword.
3. Common hidden override: a business client setting `query_timeout = 30000` at session level,
   letting unbounded queries run.

Mitigation:

- Identify and kill the offending long-running queries.
- Enforce timeout governance via resource groups with `big_query_cpu_second_limit`.
- Add SQL blacklist rules for queries without `WHERE` conditions.

See `case-015-memory-volatility` for the full investigation.

---

## 7. Emergency Load Disable

When imports cause memory/IO saturation and you need immediate relief:

```sql
-- WARNING: This stops ALL imports. Communicate clearly before executing.
ADMIN SET FRONTEND CONFIG ("disable_load_job" = "true");

-- To re-enable:
ADMIN SET FRONTEND CONFIG ("disable_load_job" = "false");
```

Also, find the source:

```bash
# Check if query or import is causing the issue
# If import: check compaction, reduce concurrency
# Temporary: set max_compaction_concurrency=1, observe memory
```

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| QPS plateaus far below expected | Default `pipeline_dop` too high for short queries | `SET GLOBAL pipeline_dop = 1` |
| `reach limit of connections` | `max_user_connections` default 100 | `ALTER USER ... SET PROPERTIES ('max_user_connections'='1000')` |
| Memory volatility despite `query_timeout` | Session-level override on a few clients | Resource-group governance + audit |
| Cache hit ratio < 10% | Workload not cache-friendly | High-cardinality GROUP BY or pre-shuffle workloads can't use cache |
| Connection storm on cold start | No connection pool | Use HikariCP/Druid; PreparedStatement |

---

## Related Cases

- `case-015-memory-volatility` — session-level timeout override case study

---

## Resources

- [Query cache documentation](https://docs.starrocks.io/docs/using_starrocks/query_cache/)
- [Primary key model documentation](https://docs.starrocks.io/docs/table_design/table_types/primary_key_table/)
