---
type: tool
category: diagnostic-commands
keywords: [grep, jstack, pstack, profile, brpc, tcpdump, schema change, routine load, tablet, checkpoint]
---

# 01 - Diagnostic Commands Quick Reference

A copy-paste-ready toolkit for the most common StarRocks debugging tasks.

---

## 1. Log Search

```bash
# Search FE for a specific query
grep "<query_id>" fe.log

# Search BE for a specific instance
grep "<instance_id>" be.INFO

# Search for errors
grep -i "error\|exception\|fail" fe.WARN | tail -100

# Search for import errors by label/txn_id
grep "<label_or_txn_id>" fe.INFO
```

---

## 2. Profile Collection

```bash
# Fetch profile via HTTP API
curl --location-trusted -u root: \
  "http://<MASTER_FE_IP>:<FE_HTTP_PORT>/query_profile?query_id=<query_id>" > profile.txt

# Find query ID from audit log
grep "QueryId" fe.audit.log | grep "<sql_keyword>"
```

```sql
-- List recent profiles (v3.0+)
SHOW PROFILELIST LIMIT 20;

-- Get connection ID for profile tracking
SELECT connection_id();
```

---

## 3. Stack Trace Capture

```bash
# FE Java stack (capture multiple times for comparison)
jstack <fe_pid> > /tmp/fe_jstack_$(date +%s).log

# BE C++ stack
pstack <be_pid> > /tmp/be_pstack_$(date +%s).log

# BE CPU profiling via pprof (60s flame graph)
pprof --svg http://<be_ip>:8060/pprof/profile?seconds=60 > cpu_profile.svg
```

---

## 4. Network Diagnostics

```bash
# Check brpc port connection state
netstat -na | grep 8060

# Check brpc latency metrics
curl -s http://<be_ip>:8060/vars | grep exec_

# Packet capture
tcpdump -i <interface> host <target_ip> and port 8060 -w /tmp/dump.pcap
```

---

## 5. Memory Diagnostics

```bash
# BE per-module memory breakdown
curl -s http://<BE_IP>:<BE_HTTP_PORT>/mem_tracker
curl -s http://<BE_IP>:<BE_HTTP_PORT>/metrics | grep "^starrocks_be_.*_mem_bytes"

# Check tcmalloc status
curl -s http://<BE_IP>:<BE_HTTP_PORT>/memz

# Find high-memory queries via mem_tracker or large memory alloc log
curl -s http://<BE_IP>:<BE_HTTP_PORT>/mem_tracker | grep "query"

# Find large memory allocations (OOM investigation)
grep "large memory alloc" be.WARNING
```

### Audit Log Analysis for TOP N Memory Queries

Use `analyze_logs.py` to find queries with highest memory consumption:

```bash
# Find top 3 BE memory consumers
python3 analyze_logs.py "2025-04-15 00:00:00" "2025-04-15 01:00:00" "MemCostBytes" 3 fe.audit.log

# Find top 3 FE memory consumers
python3 analyze_logs.py "2025-04-15 00:00:00" "2025-04-15 01:00:00" "QueryFEAllocatedMemory" 3 fe.audit.log

# Find top 3 CPU-intensive queries
python3 analyze_logs.py "2025-04-15 00:00:00" "2025-04-15 01:00:00" "CpuCostNs" 3 fe.audit.log

# Find top 3 scan-heavy queries
python3 analyze_logs.py "2025-04-15 00:00:00" "2025-04-15 01:00:00" "ScanBytes" 3 fe.audit.log
```

Available sort fields: `CpuCostNs`, `ScanBytes`, `MemCostBytes`, `QueryFEAllocatedMemory`.

---

## 6. CPU and IO Diagnostics

```bash
# CPU diagnostics — perf top for hotspots
perf top -p <be_pid>

# IO diagnostics — check disk utilization
iostat -x 1 10

# BCC tools for latency analysis
yum install bcc-tools.x86_64
offwaketime -f -U -p <be_pid>

# Check kernel network parameters
sysctl -a | grep tcp

# Check fd limit
ulimit -n
cat /proc/<be_pid>/limits

# Check dmesg (OOM Killer, etc.)
dmesg | tail -100
```

---

## 7. Schema Change Troubleshooting

```sql
-- Check ongoing schema change
SHOW ALTER TABLE COLUMN WHERE TableName = "<table>" ORDER BY CreateTime DESC LIMIT 1;

-- Check materialized view creation progress
SHOW ALTER MATERIALIZED VIEW FROM <db_name>;

-- Cancel MV creation
CANCEL ALTER MATERIALIZED VIEW FROM <db_name>.<view_name>;

-- Check table status (NORMAL / SCHEMA_CHANGE)
SHOW PROC "/dbs/<db_id>";
```

Schema change failures: search BE logs for `failed to process the version`,
`failed to process the schema change`, `fail to execute schema change`,
`fail to convert rowset`, or `Fail to link`.

Speed up schema change: increase `alter_tablet_worker_count` (default 3),
increase `memory_limitation_per_thread_for_schema_change` (default 2G).

---

## 8. Routine Load Tuning

```sql
-- Check routine load task status
SHOW ROUTINE LOAD TASK WHERE JobName = "<job_name>";
SHOW ROUTINE LOAD FOR <job_name>;

-- Check for "too many versions" (import too fast)
-- In BE log: grep "too many versions" be.INFO
-- Via SQL:
SELECT * FROM information_schema.be_tablets ORDER BY NUM_VERSION DESC LIMIT 10;
```

### Key parameters

- FE: `max_routine_load_task_num_per_be` (must be less than `routine_load_thread_pool_size`),
  `max_routine_load_task_concurrent_num` (default 5).
- BE: `max_consumer_num_per_group` (default 3), `routine_load_thread_pool_size` (default 10).
- Routine Load: `desired_concurrent_number` (default 3).

**Effective parallelism** = `min(desired_concurrent_number, kafka_partitions, max_routine_load_task_concurrent_num, be_count)`.

---

## 9. Tablet Management

```sql
-- View tablet distribution
SHOW TABLET FROM <table_name>;
SHOW TABLET <tablet_id>;

-- Check inconsistent replicas
SHOW PROC "/statistic/<db_id>";

-- View tablet compaction history
SHOW PROC '/cluster_balance/history_tablets';

-- Mark tablet as bad (triggers re-replication)
ADMIN SET REPLICA STATUS PROPERTIES("tablet_id" = "<id>", "backend_id" = "<be_id>", "status" = "bad");
```

Replica health: `SHOW TABLET` and compare `VERSION`, `LstFailedVersion`, `LstSuccessVersion`
across replicas. `VersionCount` greater than 500 continuously means compaction cannot keep up.

---

## 10. Cluster Status

```sql
-- View BE status
SHOW BACKENDS;

-- View currently running queries
SHOW PROC '/current_queries';

-- View import tasks
SHOW LOAD;

-- View statistics collection status
SHOW ANALYZE STATUS;

-- Dynamically modify BE parameters
UPDATE information_schema.be_configs SET value = '<new_value>' WHERE name = '<param_name>';

-- Dynamically modify FE parameters
ADMIN SET FRONTEND CONFIG("<param_name>" = "<value>");

-- Speed up tablet balancing
ADMIN SET FRONTEND CONFIG("schedule_slot_num_per_path" = "10");

-- Check data distribution across nodes
SELECT host_name() AS h, count(*) FROM <db>.<table> GROUP BY h;
```

### FE Leader Switch

```
# Manual leader switch (when needed)
# java -jar fe/lib/<je_jar> DbGroupAdmin \
#   -helperHosts <fe_master_ip>:<edit_log_port> \
#   -groupName PALO_JOURNAL_GROUP \
#   -transferMaster -force <node_name> 5000
#
# JE JAR:
#   <= 2.5  ->  je-7.3.7.jar
#   >= 3.0  ->  starrocks-bdb-je-18.3.16.jar
```

### Stream Load State

```
# When commit succeeded but data is not yet visible (high-throughput cluster):
# curl -s --location-trusted -u root: \
#   http://<fe_ip>:<fe_port>/api/<db>/get_load_state?label=<label>
```

---

## 11. Checkpoint Troubleshooting

```bash
# Check checkpoint status
grep "checkpoint" fe.log | tail -20

# If checkpoint fails and the image is too old, check:
#   1. Disk space on FE metadata directory
#   2. FE logs for checkpoint exceptions
#   3. BDB-JE log cleaner status
```

---

## 12. Materialized View Diagnostics

For comprehensive MV diagnostic SQL queries, see [tools/03-mv-diagnostic-sql.md](03-mv-diagnostic-sql.md).

Quick reference:

```sql
-- Check MV state
SHOW MATERIALIZED VIEWS;

-- View refresh history
SELECT * FROM information_schema.task_runs WHERE task_name = 'mv-<mv_id>' \G

-- Find currently RUNNING MV tasks
SELECT TASK_NAME, CREATE_TIME, FINISH_TIME, STATE 
FROM information_schema.task_runs WHERE STATE = 'RUNNING';
```

---

## 13. Common Operational Issues

| Issue | Solution |
|---|---|
| `reach limit of connections` | `ALTER USER 'x' SET PROPERTIES ('max_user_connections'='1000');` Check load balancers; reduce `wait_timeout`. |
| `tcmalloc: large alloc` in BE log | Large memory allocation; find `query_id` in `be.INFO` to locate SQL. |
| Tablet scheduling slow on new nodes | `ADMIN SET FRONTEND CONFIG("schedule_slot_num_per_path"="8");` and `ADMIN SET FRONTEND CONFIG("max_scheduling_tablets"="1000");`. |
| `Fail to get master client from cache` | FE-BE communication failure; check IP/port connectivity. |
| `tablet migrate failed` | Check `storage_medium` mismatch: `ALTER TABLE db.tbl MODIFY PARTITION (*) SET("storage_medium"="HDD");`. |
| High-concurrency slowdown | Set BE parameter `brpc_connection_type = pooled`; restart BE. |
| `too many open files` | Check `cat /proc/$pid/limits`; increase fd limits. |
| BE fails to start with "lock file" error | Previous process still running; kill daemon and restart. |

---

## 14. BE Decommission Checklist

Before decommissioning a BE node, verify:

1. No colocate tables affected.
2. No single-replica tables.
3. No unhealthy replicas in the cluster.
4. Cluster IO pressure is manageable.
5. No ongoing schema change operations.
6. Import pressure is acceptable.
7. No known balance bugs.

---

## 15. FE-BE Heartbeat

FE sends heartbeat to BE every 5 seconds (`Config.heartbeat_timeout_second`). If 3
consecutive heartbeats fail (`Config.heartbeat_retry_times`), BE is marked `not alive`.
After a 60-second delay (`Config.tablet_repair_delay_factor_second`), tablet replication
begins. If the BE recovers, its replicas are deleted.

---

## 16. SQL Troubleshooting Toolkit

```sql
-- Query plan analysis
EXPLAIN COSTS <SQL>;
EXPLAIN VERBOSE <SQL>;

-- Query dump for offline analysis
-- wget --post-file query.sql http://<fe>:<http_port>/api/query_dump?db=<db> -O dump.json

-- Data skew check
ADMIN SHOW REPLICA DISTRIBUTION FROM <table>;

-- Unknown errors: disable features one by one
SET disable_join_reorder = true;
SET enable_global_runtime_filter = false;
SET enable_query_cache = false;
SET cbo_enable_low_cardinality_optimize = false;
```

---

## 17. Disable Statistics Collection (Emergency)

```sql
ADMIN SET FRONTEND CONFIG("enable_statistic_collect" = "false");
ADMIN SET FRONTEND CONFIG("enable_statistic_collect_on_first_load" = "false");
SET GLOBAL analyze_mv = "";  -- v3.3+
```

---

## Usage

This document is intended for quick copy-paste during live debugging. Pair it with the
relevant skill file for context:

- For query / scan / join issues, see `skills/01-query.md`.
- For import / RPC / publish issues, see `skills/02-import.md`.
- For BE OOM / crash / FE deadlock, see `skills/03-node.md`.
- For MV refresh failures / rewrite issues, see `skills/04-materialized-view.md`.
- For shared-data and DataCache issues, see `skills/06-shared-data.md`.

If your environment exposes MCP tools for log search, metric queries, or remote command
execution, use them in place of `grep`/`curl` against individual hosts. The patterns above
remain the same; only the transport changes.
