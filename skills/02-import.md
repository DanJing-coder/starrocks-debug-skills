---
type: skill
category: import
priority: 2
keywords: [import, broker load, stream load, routine load, RPC failed, publish timeout, primary key, flink connector, profile]
---

# 02 - Import Troubleshooting

Investigation guide for import slowness, timeouts, RPC failures, publish timeouts,
Primary Key model tuning, and load profile analysis.

---

## 1. Slow / Timed-Out Imports — Overall Approach

The import pipeline has three phases: **Data Read -> Data Write -> Publish**.
Identify which phase is slow.

### Common error symptoms

| Symptom | Analysis |
|---|---|
| Import succeeds but takes too long | Read + Write + Publish overall slow |
| `Timeout by txn manager` | Read or Write slow |
| `[E1008]Reached timeout` | Write slow — storage layer causes brpc timeout between Coordinator BE and Executor BE |
| `publish timeout` | Publish slow — common with Primary Key tables |

### Using FE Transaction logs to identify slow phase

```bash
# Find write vs publish duration by label or txn_id
grep "<label_or_txn_id>" fe.log | grep "finishTransaction"
# Log shows: "write cost: 243ms ... publish total cost: 154ms"
```

### Using Profile to identify read vs write

- High `OLAP_TABLE_SINK` time means write is slow.
- High `CONNECTOR_SCAN` / `FileScanNode` time means read is slow.
- For `INSERT INTO SELECT`, the SELECT portion itself may be complex.

---

## 2. Write-Slow Diagnosis (Reached timeout / Timeout by txn manager)

The data write path involves these thread pools in sequence — check each for backlog:

| Thread Pool | Config | Default | Purpose |
|---|---|---|---|
| `brpc` | `brpc_num_threads` | #CPU cores | Receives data from Coordinator BE |
| `async_delta_writer` | `number_tablet_writer_threads` | 16 | Writes data to memtable, handles commit |
| `memtable_flush` | `flush_thread_num_per_store` | 2 per disk | Flushes memtable to segment files |
| `segment_replicate` | `flush_thread_num_per_store` | 2 per disk | Syncs segments to secondary replicas (shared-nothing only) |
| `segment_flush` | `flush_thread_num_per_store` | 2 per disk | Persists segments on secondary replicas (shared-nothing only) |

### Step-by-step diagnosis

1. Check cluster resources — CPU, disk IO utilization, network bandwidth. If resources are saturated, scale or reduce load.
2. Check thread pool metrics — for each pool above, check if `active` is approximately equal to `total` with non-zero `queue`. If so, increase pool size.
3. Check per-pool latency metrics — each pool has `pending` (queue wait time) and `execute` (processing time) metrics.
4. For `async_delta_writer`: if `execute` is high, check sub-metrics: `wait_flush` (memtable flush slow), `wait_replica` (replica sync slow), `pk_preload` (PK index rebuild slow), `txn_commit` (metadata persistence slow).
5. For `memtable_flush`: if `io` metric is high, check disk util or S3 latency.
6. If metrics are insufficient: use storage-layer Profile (v3.4+: auto-logged on timeout; v3.5+: auto-reported to FE) or Stack Trace.

**PK-specific: `skip_pk_preload`** — if `pk_preload` metric is high (common during clone/node decommission),
set BE config `skip_pk_preload = true` to skip PK index rebuild during import.

**RocksDB bottleneck (shared-nothing)**: if `txn_commit` is high, check
`starrocks_be_meta_request_duration{type="write"}` and rocksdb logs for `Stalling writes`.
Increase rocksdb write buffer size.

---

## 3. Read-Slow Diagnosis

| Import Type | Common Causes |
|---|---|
| Stream Load | Network slow between client and StarRocks; JSON format with large batches (try CSV or reduce batch size) |
| Routine Load | Small batch size (increase `max_routine_load_batch_size` and `routine_load_task_consume_second`); too few Kafka partitions |
| Broker Load | Too many small files; slow file storage |
| INSERT INTO | Complex query in SELECT |

---

## 4. Publish Timeout

Common with Primary Key tables. Investigation:

1. Check publish thread pool — `transaction_publish_version_worker_count` (default: #CPU cores). Monitor `starrocks_be_publish_version_queue_count` (shared-nothing) or `lake_publish_tablet_version_queuing_count` (shared-data).
2. PK sync publish — if `enable_sync_publish` is on, check BE logs for `apply_rowset_commit finish` to analyze apply latency.
3. Check if compaction score is continuously rising.
4. Check if clone tasks are interfering with publish.
5. For shared-data: check remote storage (S3/HDFS) latency.

---

## 5. Broker Load Task Backlog

Investigation approach:

1. Check `async_load_task_pool_size` (loading thread pool size).
2. Check if long-running stuck tasks are filling the pool.
3. Trace through FE logs: `label -> txn_id -> query_id -> instance_id -> BE thread ID`.
4. Search BE logs for `ReportExecStatus` failures — failed status reporting causes task state to be lost.

---

## 6. Reached Timeout — Auto-Diagnostics (v3.4+)

Starting from v3.4, `Reached timeout` automatically captures storage-layer profiles in BE logs:

```bash
# Search BE log on the timeout-reporting node
grep "profile=" be.WARNING
# Example: tablet writer add chunk timeout. txn_id=1691, cost=16728ms, timeout=16500ms, profile=xxx
```

Starting from v3.5, profiles are auto-reported to FE and stack traces are captured:

```bash
# Stack trace search in BE logs
grep "diagnose stack trace, id:" be.INFO
# Extract the id, then:
grep "DIAGNOSE <id> -" be.INFO > stack_trace.log
```

### Key BE configs for auto-diagnostics

- `load_rpc_slow_log_frequency_threshold_seconds` (default 60) — controls profile log frequency
- `load_diagnose_rpc_timeout_profile_threshold_ms` (default 60000) — controls FE profile upload frequency
- `load_diagnose_rpc_timeout_stack_trace_threshold_ms` (default 600000) — controls stack trace capture
- `diagnose_stack_trace_interval_ms` (default 1800000) — minimum interval between stack traces

### Common Reached timeout root causes

- `async_delta_writer` or `segment_replicate` pool stuck (possibly bug) -> restart BE
- BRPC overcrowded on replica sync -> tune BRPC params, reduce timeout for faster failure
- PK index rebuild during clone/decommission blocks writes -> set `skip_pk_preload = true`
- HDD disk IO saturation -> add nodes or switch to SSD
- S3 write latency spikes (shared-data) -> check fslib metrics
- PK compaction commit holds lock -> `skip_pk_preload = true`

---

## 7. Primary Key Model Import Tuning

Key BE parameters for Primary Key tables:

- `load_process_max_memory_limit_bytes` (default 100G) — upper bound for import memory.
- `load_process_max_memory_limit_percent` (default 30%) — actual limit = `mem_limit * 90% * 30%`.
- `update_cache_expire_sec`, `update_memory_limit_percent` — tune when PK import hits memory limits.
- Enable persistent index to offload PK index from memory (may slow initial load slightly).

Session variable: `load_mem_limit = 0` (default, no per-task limit; setting too small causes excessive small files).

---

## 8. Flink Connector Import Issues

Non-exactly-once import frequency is governed by:
`sink.buffer-flush.max-bytes`, `sink.buffer-flush.max-rows`, `sink.buffer-flush.interval-ms`,
`checkpoint-interval`.

For high-throughput Flink ingestion, check Flink CPU utilization — it is often the bottleneck,
not StarRocks.

---

## 9. RPC Failed

This is a complex problem class potentially involving network, statistics collection,
and brpc connections.

### Quick mitigation

```sql
-- Increase RPC timeout
ADMIN SET FRONTEND CONFIG("brpc_send_plan_fragment_timeout_ms"="180000");

-- If statistics collection is suspected, disable it and restart FE:
ADMIN SET FRONTEND CONFIG("enable_collect_full_statistic"="false");
ADMIN SET FRONTEND CONFIG("enable_statistic_collect"="false");
ADMIN SET FRONTEND CONFIG("enable_statistic_collect_on_first_load"="false");
```

### Deep investigation

1. Check brpc latency metrics:
   ```bash
   curl -s http://<be_ip>:8060/vars | grep exec_
   ```
2. Inspect TCP connection state:
   ```bash
   netstat -na | grep 8060
   ```
3. Capture jstack / pstack to analyze blocking points.
4. Capture tcpdump if needed for network-layer analysis.
5. Review FE runtime parameter `brpc_connection_pool_size`.

### Statistics collection tuning parameters

- `statistic_collect_interval_sec` — collection interval (increase to 1200+).
- `statistic_collect_concurrency` — collection parallelism (reduce to 1).
- `statistic_max_full_collect_data_size` — threshold for switching to sampling.

---

## 10. Import Profile Analysis (Advanced)

### Enabling Load Profiles

```sql
-- For Broker Load / INSERT INTO (session-level)
SET enable_profile = true;

-- Auto-enable for long-running imports (>60s)
SET big_query_profile_threshold = 60s;

-- For Stream Load / Routine Load (table-level)
ALTER TABLE <table_name> SET ("enable_load_profile" = "true");

-- View and analyze profiles
SHOW PROFILELIST;
ANALYZE PROFILE FROM '<profile_id>';
```

### Key OlapTableSink Metrics

| Metric | What it tells you |
|---|---|
| `RpcClientSideTime` | Total client-side RPC time |
| `RpcServerSideTime` | Server-side processing time |
| `PrepareDataTime` | Format conversion + quality check |
| `SendDataTime` | Serialization + compression + send |
| `PushChunkNum` variance | Large variance means data skew |

If `RpcClientSideTime` is much greater than `RpcServerSideTime`, network or RPC framework
is the bottleneck.

### Key LoadChannel Metrics

| Metric | What it tells you |
|---|---|
| `WaitFlushTime` | High means insufficient flush threads (`flush_thread_num_per_store`) |
| `WaitWriterTime` | High means async delta writer backlog |
| `WaitReplicaTime` | High means replica synchronization slow |
| `PeakMemoryUsage` | Per-channel peak memory |

### Import Health Monitoring SQL

```sql
-- Throughput per minute (last 10 minutes)
SELECT date_trunc('minute', load_finish_time) AS t,
       count(*) AS tpm, sum(SCAN_BYTES) AS scan_bytes, sum(sink_rows) AS sink_rows
FROM _statistics_.loads_history
GROUP BY t ORDER BY t DESC LIMIT 10;

-- Rowset / Segment accumulation check (high values means needs compaction tuning)
SELECT * FROM information_schema.be_tablets t
JOIN information_schema.tables_config c ON t.table_id = c.table_id
ORDER BY num_rowset DESC LIMIT 5;

-- Data skew detection (node-level)
SELECT tbt.be_id, sum(tbt.DATA_SIZE)
FROM information_schema.tables_config tb
JOIN information_schema.be_tablets tbt ON tb.TABLE_ID = tbt.TABLE_ID
GROUP BY be_id;
```

### Import Thread Pool Monitoring (Grafana)

Four key thread pools: `async_delta_writer`, `memtable_flush`, `segment_replicate_sync`,
`segment_flush`.

Per pool: check `pending` duration trend (increasing means backlog), `rate` (throughput),
`util` (pool utilization).

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| Broker Load tasks queue forever | `async_load_task_pool_size` too small or stuck tasks | Increase pool size; trace stuck task by label |
| `Reached timeout` on Stream Load | brpc / async_delta_writer pool stuck | Restart BE; tune brpc threads |
| `publish timeout` on PK table | Compaction lagging or PK index rebuild | Tune compaction; `skip_pk_preload = true` |
| RPC Failed during nightly batch | Statistics collection saturating brpc | Disable full statistics; reduce concurrency |
| Routine Load not keeping up | Small batch, few Kafka partitions | Increase batch size; add Kafka partitions |

---

## Related Cases

- `case-001-broker-load-backlog` — task pool saturation root cause
- `case-002-rpc-failed-statistics` — statistics collection starving RPC
- `case-007-memory-tracking-leak` — slow imports caused by memory tracker leak
- `case-009-stream-load-stuck` — tablet meta cache bug

---

## Resources

- [Loading Troubleshooting](https://docs.starrocks.io/docs/loading/loading_introduction/troubleshooting_loading/)
