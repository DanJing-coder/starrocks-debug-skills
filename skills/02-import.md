---
type: skill
category: import
priority: 2
keywords: [import, broker load, stream load, routine load, RPC failed, publish timeout, primary key, flink connector, profile, reached timeout, slow import]
---

# 02 - Import Troubleshooting

Investigation guide for import slowness, timeouts, RPC failures, publish timeouts,
Primary Key model tuning, and load profile analysis.

---

## Terminology

| Term | Definition |
|---|---|
| Import Job | Continuous import operations: Routine Load Job, Pipe Job |
| Import Task | One-time import task corresponding to a transaction: Broker Load, Stream Load, Spark Load, Insert Into. Routine Load/Pipe internally generate continuous Import Tasks |

---

## 1. Import Observation

### Show Commands

| Command | Purpose |
|---|---|
| `SHOW ROUTINE LOAD` | View Routine Load job status |
| `SHOW PIPES` | View Pipe job status |
| `SHOW LOAD` | View Broker Load/Insert Into/Spark Load tasks (running + recently completed) |
| `SHOW ROUTINE LOAD TASK` | View Routine Load tasks |

### System Views

**information_schema.loads** — Contains all running and recently completed import tasks. Schema:

| Field | Description |
|---|---|
| ID | Global unique ID |
| LABEL | Import job label |
| PROFILE_ID | Profile ID for `ANALYZE PROFILE FROM 'profile_id'` (NULL if no profile) |
| DB_NAME / TABLE_NAME | Target database/table |
| USER / WAREHOUSE | Initiating user / warehouse |
| STATE | PENDING, BEGIN, QUEUEING, BEFORE_LOAD, LOADING, PREPARING, PREPARED, COMMITED, FINISHED, CANCELLED |
| PROGRESS | ETL and LOADING phase progress |
| TYPE | BROKER, INSERT, ROUTINE, STREAM |
| PRIORITY | HIGHEST, HIGH, NORMAL, LOW, LOWEST |
| SCAN_ROWS / SCAN_BYTES | Total scanned rows/bytes |
| FILTERED_ROWS / UNSELECTED_ROWS | Quality-filtered / WHERE-filtered rows |
| SINK_ROWS | Successfully imported rows |
| CREATE_TIME / LOAD_START_TIME / LOAD_COMMIT_TIME / LOAD_FINISH_TIME | Timestamps |
| ERROR_MSG | Error message (NULL if none) |
| TRACKING_SQL | Query for rejected records |
| REJECTED_RECORD_PATH | Path to quality-rejected records |

**runtime_details** (nested JSON):

| Field | Broker/Insert/Spark Load | Routine Load | Stream Load |
|---|---|---|---|
| load_id | Execution plan ID | — | — |
| txn_id | Transaction ID | — | — |
| etl_info | ETL details (Spark Load only) | — | — |
| unfinished_backends | Incomplete backend list | — | — |
| file_num / file_size / task_num | File count/size/subtasks | — | — |
| schedule_interval / wait_slot_time / check_offset_time | — | Routine Load scheduling | — |
| consume_time / plan_time / commit_publish_time | — | Routine Load timing | — |
| timeout / begin_txn_ms / plan_time_ms / receive_data_time_ms / commit_publish_time_ms / client_ip | — | — | Stream Load timing |

**_statistics_.loads_history** — Persists load history (default 3 months). Same schema as loads.

---

## 2. Import Pipeline Overview

The import pipeline has three phases: **Data Read → Data Write → Publish**.

### Data Write Process (Shared-Nothing / Replicated Storage)

```
OlapTableSink → BRPC tablet_writer_add_chunks → Primary Replica
                                                    ↓ async_delta_writer (memtable write)
                                                    ↓ memtable_flush (segment generation)
                                                    ↓ segment_replicate_sync (BRPC to secondary)
                                                    ↓
                                               Secondary Replica
                                                    ↓ segment_flush (disk persist)
```

### Thread Pool Configuration

| Thread Pool | BE Config | Default | Queue Size | Dynamic |
|---|---|---|---|---|
| brpc | `brpc_num_threads` | #CPU cores | unlimited | No |
| async_delta_writer | `number_tablet_writer_threads` | 16 | 40960 | Yes |
| memtable_flush (shared-nothing) | `flush_thread_num_per_store` | 2 per disk | INT_MAX | Yes |
| memtable_flush (shared-data) | `lake_flush_thread_num_per_store` | 2 * #CPU cores | INT_MAX | Yes |
| segment_replicate_sync | `flush_thread_num_per_store` | 2 per disk | INT_MAX | Yes |
| segment_flush | `flush_thread_num_per_store` | 2 per disk | INT_MAX | Yes |

### BRPC Interfaces

| Interface | Direction | Purpose |
|---|---|---|
| tablet_writer_open | Coordinator → Primary/Secondary | Initialize tablet writer |
| tablet_writer_add_chunks | Coordinator → Primary | Send data to primary replica |
| tablet_writer_add_segment | Primary → Secondary | Sync segment to secondary |

---

## 3. Slow / Timed-Out Imports — Overall Approach

### Common Error Symptoms

| Symptom | Analysis |
|---|---|
| Import succeeds but takes too long | Read + Write + Publish overall slow |
| `Timeout by txn manager` | Read or Write slow |
| `[E1008]Reached timeout` | Write slow — storage layer causes brpc timeout between Coordinator BE and Executor BE |
| `publish timeout` | Publish slow — common with Primary Key tables |

### Using FE Transaction Logs to Identify Slow Phase

```bash
# Find write vs publish duration by label or txn_id
grep "<label_or_txn_id>" fe.log | grep "finishTransaction"
# Log shows: "write cost: 243ms ... publish total cost: 154ms"
```

### Using Profile to Identify Read vs Write

- High `OLAP_TABLE_SINK` time means write is slow.
- High `CONNECTOR_SCAN` / `FileScanNode` time means read is slow.
- For `INSERT INTO SELECT`, the SELECT portion itself may be complex.

---

## 4. Cluster Resource Monitoring

Before analyzing import-specific metrics, check overall cluster resources.

### CPU Monitoring

- Per-BE CPU usage
- v3.4+: CPU breakdown by task type

### IO Monitoring

- **Shared-nothing**: Local disk IO util
- **Shared-data**: Both local disk and S3 IO
  - Check fslib write IO metrics for S3 latency
- v3.4+: IO breakdown by task type

### Network Monitoring

- StarRocks network traffic metrics
- TCP connection health: queue overflow, packet loss, retransmission
- Install prometheus node_exporter for physical-level TCP monitoring

---

## 5. Write-Slow Diagnosis (Reached timeout / Timeout by txn manager)

### Step-by-Step Diagnosis

1. **Check cluster resources** — CPU, disk IO utilization, network bandwidth. If saturated, scale or reduce load.

2. **Check thread pool metrics** — For each pool, check if `active` ≈ `total` with non-zero `queue`. If so, increase pool size.

3. **Check per-pool latency metrics** — Each pool has `pending` (queue wait) and `execute` (processing) metrics.

4. **For async_delta_writer**: if `execute` is high, check sub-metrics:
   - `wait_flush` (memtable flush slow)
   - `wait_replica` (replica sync slow)
   - `pk_preload` (PK index rebuild slow)
   - `txn_commit` (metadata persistence slow)

5. **For memtable_flush**: if `io` metric is high, check disk util or S3 latency.

6. **If metrics insufficient**: use storage-layer Profile (v3.4+: auto-logged on timeout; v3.5+: auto-reported to FE) or Stack Trace.

### BRPC Monitoring

| Metric | Meaning |
|---|---|
| `total` / `used` | Total/in-use threads. If close, BRPC is busy |
| `latency-avg` / `latency-99` | Interface latency. High P99 = server-side processing slow |
| `Brpc Processing Requests` | In-flight RPC count. Zero during timeout = network/BRPC issue |

Key interfaces: `tablet_writer_open`, `tablet_writer_add_chunks`, `tablet_writer_add_segment`

### Async Delta Writer Monitoring

| Metric | Meaning | Analysis |
|---|---|---|
| `pending` | Queue wait time | High = pool size insufficient |
| `execute` | Task execution time | Contains wait_flush + wait_replica |
| `wait_flush` | Wait for memtable flush | High → analyze memtable_flush |
| `wait_replica` | Wait for replica sync | High → analyze segment_replicate_sync |
| `pk_preload` | PK index rebuild/preload | High → set `skip_pk_preload = true` |
| `txn_commit` | Txn metadata persistence | High → check rocksdb write latency |

**RocksDB bottleneck (shared-nothing)**:
- Check `starrocks_be_meta_request_duration{type="write"}`
- Check rocksdb logs for `Stalling writes`
- Increase rocksdb write buffer size

**S3 bottleneck (shared-data)**:
- Check fslib write IO metrics

### Memtable Flush Monitoring

| Metric | Meaning |
|---|---|---|
| `pending` | Queue wait time |
| `execute` | Total flush time |
| `io` | IO portion of flush |
| `rate` | Flush rate (tasks/sec) |
| `memory-size` / `disk-size` | Data volume flushed |

Analysis:
- If `io` is high proportion of `execute` → disk or S3 is bottleneck
- `memory-size / disk-size` = compression ratio
- Low `rate` with high `size` = large imports

### Segment Replicate Sync Monitoring (Shared-Nothing Only)

| Metric | Meaning |
|---|---|---|
| `pending` | Queue wait time |
| `execute` | Sync time (includes waiting for secondary commit) |

Analysis:
- High `execute` → check BRPC `tablet_writer_add_segment` latency
- If BRPC latency high → secondary replica segment_flush slow
- If BRPC latency low → BRPC or network issue

### Segment Flush Monitoring (Shared-Nothing Only)

| Metric | Meaning |
|---|---|---|
| `pending` | Queue wait time |
| `execute` | Total flush time |
| `io` | IO portion |
| `rate` / `size` | Flush rate/volume |

---

## 6. Read-Slow Diagnosis

| Import Type | Common Causes | Solutions |
|---|---|---|
| Stream Load | HTTP client to StarRocks network slow; JSON format with large batches | Reduce batch size; try CSV format |
| Routine Load | Small batch size; few Kafka partitions | Increase `max_routine_load_batch_size` and `routine_load_task_consume_second`; add Kafka partitions |
| Broker Load | Many small files; slow file storage | Consolidate files; check storage performance |
| INSERT INTO | Complex SELECT query | Optimize query |

---

## 7. Publish Timeout

Common with Primary Key tables.

### Investigation

1. **Check publish thread pool** — `transaction_publish_version_worker_count` (default: #CPU cores). Monitor `starrocks_be_publish_version_queue_count` (shared-nothing) or `lake_publish_tablet_version_queuing_count` (shared-data).

2. **PK sync publish** — If `enable_sync_publish` is on, check BE logs for `apply_rowset_commit finish` latency.

3. **Check compaction score** — Rising score indicates compaction lag.

4. **Check clone tasks** — May interfere with publish.

5. **For shared-data** — Check remote storage (S3/HDFS) latency.

---

## 8. Broker Load Task Backlog

### Investigation

1. Check `async_load_task_pool_size` (loading thread pool).
2. Check if long-running stuck tasks are filling the pool.
3. Trace through FE logs: `label → txn_id → query_id → instance_id → BE thread ID`.
4. Search BE logs for `ReportExecStatus` failures — failed status reporting causes task state loss.

---

## 9. Reached Timeout — Auto-Diagnostics (v3.4+)

### v3.4: Automatic Profile Capture

Starting from v3.4, `Reached timeout` automatically captures storage-layer profiles in BE logs:

```bash
# Search BE log on the timeout-reporting node
grep "profile=" be.WARNING
# Example: tablet writer add chunk timeout. txn_id=1691, cost=16728ms, timeout=16500ms, profile=xxx
```

### v3.5: Profile Upload + Stack Trace

```bash
# Stack trace search in BE logs
grep "diagnose stack trace, id:" be.INFO
# Extract the id, then:
grep "DIAGNOSE <id> -" be.INFO > stack_trace.log
```

### Key BE Configs for Auto-Diagnostics

| Config | Default | Purpose |
|---|---|---|
| `load_rpc_slow_log_frequency_threshold_seconds` | 60 | Profile log frequency |
| `load_diagnose_rpc_timeout_profile_threshold_ms` | 60000 | FE profile upload frequency |
| `load_diagnose_rpc_timeout_stack_trace_threshold_ms` | 600000 | Stack trace capture threshold |
| `diagnose_stack_trace_interval_ms` | 1800000 | Minimum interval between stack traces |

### Common Reached Timeout Root Causes

| Cause | Mitigation |
|---|---|
| async_delta_writer or segment_replicate pool stuck (bug) | Restart BE |
| BRPC overcrowded on replica sync | Tune BRPC params; reduce timeout for faster failure |
| PK index rebuild during clone/decommission | Set `skip_pk_preload = true` |
| HDD disk IO saturation | Add nodes or switch to SSD |
| S3 write latency spikes (shared-data) | Check fslib metrics |
| PK compaction commit holds lock | Set `skip_pk_preload = true` |

---

## 10. Load Profile Analysis

### Enabling Load Profile

**Session Variable (Broker Load / INSERT INTO):**
```sql
SET enable_profile = true;
-- Auto-enable for long imports (>60s)
SET big_query_profile_threshold = 60s;
```

**Runtime Profile:**
```sql
-- Report profile during execution (default 30s interval)
SET runtime_profile_report_interval = 60;
```

**Table Property (Stream Load / Routine Load):**
```sql
ALTER TABLE <table_name> SET ("enable_load_profile" = "true");
```

**Sampling for High-QPS Stream Load:**
```sql
-- Collect profile every N seconds (default 0)
ADMIN SET FRONTEND CONFIG ("load_profile_collect_interval_second" = "30");
-- Only collect for imports exceeding threshold (default 0)
ADMIN SET FRONTEND CONFIG ("stream_load_profile_collect_threshold_second" = "10");
```

### Viewing Profiles

```sql
SHOW PROFILELIST;
ANALYZE PROFILE FROM '<profile_id>';
```

### OlapTableSink Profile Metrics

| Metric | Meaning |
|---|---|---|
| `IndexNum` | Number of synchronous material views |
| `ReplicatedStorage` | Single leader replication enabled |
| `TxnID` | Transaction ID |
| `RowsRead` / `RowsFiltered` / `RowsReturned` | Row counts from upstream, filtered, written |
| `RpcClientSideTime` | Client-side RPC total time |
| `RpcServerSideTime` | Server-side RPC processing time |
| `PrepareDataTime` | Format conversion + quality check |
| `SendDataTime` | Serialization + compression + send |

**Analysis:**
- `PushChunkNum` Max/Min variance large → data skew, potential write bottleneck
- `RpcClientSideTime` >> `RpcServerSideTime` → network or RPC framework bottleneck, consider compression
- `RpcServerSideTime` high → analyze LoadChannel Profile

### LoadChannel Profile Metrics

| Metric | Meaning |
|---|---|---|
| `Address` | BE host |
| `LoadMemoryLimit` | Import memory limit |
| `PeakMemoryUsage` | Peak memory usage |
| `OpenCount` / `OpenTime` | Channel open count/time (sink concurrency) |
| `AddChunkCount` / `AddRowNum` / `AddChunkTime` | Chunk/row counts, add chunk time |
| `WaitFlushTime` | Wait for memtable flush |
| `WaitWriterTime` | Wait for async delta writer |
| `WaitReplicaTime` | Wait for replica sync |
| `PrimaryTabletsNum` / `SecondaryTabletsNum` | Primary/secondary tablet counts |

**Analysis:**
- `WaitFlushTime` high → increase `flush_thread_num_per_store`
- `WaitWriterTime` high → increase `number_tablet_writer_threads`
- `WaitReplicaTime` high → replica sync slow (shared-nothing)

---

## 11. Primary Key Model Import Tuning

### Key BE Parameters

| Config | Default | Purpose |
|---|---|---|
| `load_process_max_memory_limit_bytes` | 100G | Upper bound for import memory |
| `load_process_max_memory_limit_percent` | 30% | Actual limit = `mem_limit * 90% * 30%` |
| `update_cache_expire_sec` | — | PK cache expiration |
| `update_memory_limit_percent` | — | PK update memory limit |

**PK-specific mitigation:**
- Set `skip_pk_preload = true` to skip PK index rebuild during import (common during clone/decommission)
- Enable persistent index to offload PK index from memory

**Session variable:** `load_mem_limit = 0` (default, no per-task limit; too small causes excessive small files)

---

## 12. Flink Connector Import Issues

Import frequency governed by:
- `sink.buffer-flush.max-bytes`
- `sink.buffer-flush.max-rows`
- `sink.buffer-flush.interval-ms`
- `checkpoint-interval`

For high-throughput Flink ingestion, **Flink CPU utilization** is often the bottleneck, not StarRocks.

---

## 13. RPC Failed

Complex problem involving network, statistics collection, and brpc connections.

### Quick Mitigation

```sql
-- Increase RPC timeout
ADMIN SET FRONTEND CONFIG("brpc_send_plan_fragment_timeout_ms" = "180000");

-- If statistics collection suspected, disable and restart FE:
ADMIN SET FRONTEND CONFIG("enable_collect_full_statistic" = "false");
ADMIN SET FRONTEND CONFIG("enable_statistic_collect" = "false");
ADMIN SET FRONTEND CONFIG("enable_statistic_collect_on_first_load" = "false");
```

### Deep Investigation

1. Check brpc latency metrics:
   ```bash
   curl -s http://<be_ip>:8060/vars | grep exec_
   ```
2. Inspect TCP connection state:
   ```bash
   netstat -na | grep 8060
   ```
3. Capture jstack / pstack to analyze blocking points.
4. Capture tcpdump for network-layer analysis.
5. Review FE runtime parameter `brpc_connection_pool_size`.

### Statistics Collection Tuning

| Config | Suggestion |
|---|---|
| `statistic_collect_interval_sec` | Increase to 1200+ |
| `statistic_collect_concurrency` | Reduce to 1 |
| `statistic_max_full_collect_data_size` | Threshold for sampling |

---

## 14. Common Operational SQL

### Per-Minute Import Throughput

```sql
-- Overall
SELECT date_trunc('minute', load_finish_time) AS t,
       count(*) AS tpm, sum(SCAN_BYTES) AS scan_bytes, sum(sink_rows) AS sink_rows
FROM _statistics_.loads_history
GROUP BY t ORDER BY t DESC LIMIT 10;

-- Per table
SELECT date_trunc('minute', load_finish_time) AS t,
       count(*) AS tpm, sum(SCAN_BYTES) AS scan_bytes, sum(sink_rows) AS sink_rows
FROM _statistics_.loads_history
WHERE table_name = 't'
GROUP BY t ORDER BY t DESC LIMIT 10;
```

### Rowset / Segment Accumulation

```sql
-- Check rowset/segment count (high values need compaction tuning)
SELECT * FROM information_schema.be_tablets t
JOIN information_schema.tables_config c ON t.table_id = c.table_id
ORDER BY num_rowset DESC LIMIT 5;

SELECT * FROM information_schema.be_tablets t
JOIN information_schema.tables_config c ON t.table_id = c.table_id
ORDER BY num_segment DESC LIMIT 5;
```

- RowsetNum > 100 → imports too frequent, reduce frequency or increase compaction threads
- SegmentNum > 100 → single import produces many segments, increase compaction threads or use random distribution

### Data Skew Detection

```sql
-- Node-level skew
SELECT tbt.be_id, sum(tbt.DATA_SIZE)
FROM information_schema.tables_config tb
JOIN information_schema.be_tablets tbt ON tb.TABLE_ID = tbt.TABLE_ID
GROUP BY be_id;

-- Tablet-level skew per partition
SELECT tablet_id, t.data_size, num_row, visible_version, num_version, num_rowset, num_segment, PARTITION_NAME
FROM information_schema.partitions_meta m
JOIN information_schema.be_tablets t ON t.partition_id = m.partition_id
WHERE m.partition_name = 'att' AND m.table_name = 'att'
ORDER BY t.data_size DESC;
```

If partition skewed → use high-cardinality column as distribute key or random distribution.

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
- [Query Profile Structure](https://docs.starrocks.io/docs/administration/query_profile/)