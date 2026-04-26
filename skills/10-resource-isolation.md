---
type: skill
category: resource-isolation
priority: 10
keywords: [resource group, query queue, SQL blacklist, big query, circuit breaker, governance]
---

# 10 - Resource Isolation, Query Queue, and Query Governance

Investigation guide for resource groups, query queues, big-query circuit breakers, and SQL
blacklisting.

---

## 1. Resource Group Diagnostics

```sql
-- Check which resource group a query matched
EXPLAIN VERBOSE <SQL>;
-- Or check fe.audit.log for the resource_group field

-- Set resource group for session
SET resource_group = '<group_name>';
-- Or via hint
SELECT /*+ SET_VAR(resource_group = '<group_name>') */ * FROM tbl;
```

### Key points

- CPU limit is **soft** (proportional sharing); memory limit is **hard** (query fails if exceeded).
- `INSERT INTO SELECT`: only the SELECT part is limited by the resource group.
- Resource group settings apply **per BE node**, not globally.
- Queries matching no classifier fall back to `default_wg`.
- `default_wg` limits cannot be changed; create a general group as workaround.

---

## 2. Resource Group Monitoring Metrics

FE metrics (`fe_host:8030/metrics?type=json`):

- `starrocks_fe_query_resource_group` — query count per group.
- `starrocks_fe_query_resource_group_latency` — percentile latencies.
- `starrocks_fe_query_resource_group_err` — error count per group.

BE metrics (`be_host:8040/metrics?type=json`):

- `starrocks_be_resource_group_cpu_limit_ratio` — CPU allocation ratio.
- `starrocks_be_resource_group_mem_limit_bytes` — memory limit.

---

## 3. Query Queue

- Queue trigger: BE available memory times `query_queue_mem_used_pct_limit`.
- When `query_queue_max_queued_queries` is reached, query **fails immediately**.
- When `query_queue_concurrency_limit` is reached, query **waits in queue**.
- Disable queue for specific users:
  ```sql
  ALTER USER 'xxx' SET PROPERTIES ("session.enable_query_queue" = "false");
  ```

---

## 4. SQL Blacklist

Block dangerous SQL patterns using regex:

```sql
-- Enable SQL blacklist
ADMIN SET FRONTEND CONFIG ("enable_sql_blacklist" = "true");

-- Block SELECT without WHERE
ADD SQLBLACKLIST "select .* from [^w]*;";

-- Block count(*) on a specific table
ADD SQLBLACKLIST "select count\\\\(\\\\*\\\\) from user_profile";

-- View / delete rules
SHOW SQLBLACKLIST;
DELETE SQLBLACKLIST <id>;
```

---

## 5. Resource Group Configuration with Audit-Based Tuning

Create resource groups to isolate workloads and set circuit breakers:

```sql
CREATE RESOURCE GROUP rg_bi
TO (user='bi_user', role='bi_role')
PROPERTIES (
    "cpu_core_limit" = "10",
    "mem_limit" = "30%",
    "concurrency_limit" = "10",
    "big_query_cpu_second_limit" = "600",
    "big_query_scan_rows_limit" = "1000000000",
    "big_query_mem_limit" = "10737418240"
);
```

### Tuning parameters using audit log

| Parameter | Tuning Method |
|---|---|
| `cpu_core_limit` | `SELECT user, SUM(cpuCostNs)/1e9 AS cpu_sec FROM starrocks_audit_db__.starrocks_audit_tbl__ WHERE state IN ('EOF','OK') AND timestamp >= now() - INTERVAL 30 DAY GROUP BY user` then allocate proportionally |
| `concurrency_limit` | Analyze per-minute max concurrency per user; set 1.5x of P99 |
| `big_query_cpu_second_limit` | `SELECT percentile_approx(queryTime, 0.99)/1000 FROM audit WHERE user='X'` then set 2x of P99 |
| `big_query_scan_rows_limit` | `SELECT percentile_approx(scanRows, 0.99) FROM audit WHERE user='X'` then set 2x of P99 |
| `big_query_mem_limit` | `SELECT percentile_approx(memCostBytes, 0.99) FROM audit WHERE user='X'` then set 1.5-2x of P99 |

---

## 6. Disable Statistics Collection (Emergency)

```sql
ADMIN SET FRONTEND CONFIG("enable_statistic_collect" = "false");
ADMIN SET FRONTEND CONFIG("enable_statistic_collect_on_first_load" = "false");
SET GLOBAL analyze_mv = "";  -- v3.3+
```

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| Query keeps falling into `default_wg` | No classifier match | Add user/role classifier |
| Memory limit exceeded but CPU plenty | Memory limit is hard | Tune `big_query_mem_limit` per audit P99 |
| Queries fail at queue boundary | `query_queue_max_queued_queries` reached | Increase queue size or reduce ingest |
| Big query unbounded for one user | No `big_query_*` limit set | Set CPU/scan/mem big-query limits |

---

## Related Cases

- `case-002-rpc-failed-statistics` — statistics collection saturating brpc; emergency disable pattern
- `case-015-memory-volatility` — governance gap allowing session-level timeout override

---

## Resources

- [Resource Isolation FAQ](https://docs.starrocks.io/docs/faq/resource_isolation_faq/)
