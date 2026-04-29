---
type: skill
category: compaction
priority: 12
keywords: [compaction, too many versions, compaction score, base compaction, cumulative compaction, rowset, version count, primary key compaction]
---

# 12 - Shared-Nothing Compaction Troubleshooting

Investigation guide for compaction issues in shared-nothing architecture, including
too many versions, high compaction score, query slowdown, and resource saturation.

---

## 1. Background

StarRocks storage engine uses an LSM-like data structure. For each tablet:
- New data writes to memory, then flushes to disk as immutable rowsets
- Each rowset has a version range (start_version, end_version)
- Compaction merges small rowsets into larger ones to improve query performance

**Compaction Types**:
- **Cumulative Compaction**: Merges recent rowsets into larger ones (lighter operation)
- **Base Compaction**: Merges cumulative rowsets into base rowset (version 0, heavier operation)
- **Update Compaction**: For Primary Key tables, different scoring mechanism

**Cumulative Point**: Boundary between base and cumulative compaction.
- Base compaction works on rowsets before cumulative point
- Cumulative compaction works on rowsets after cumulative point

---

## 2. Common Symptoms

| Symptom | Typical Cause |
|---|---|
| Import fails with `too many versions` | Import frequency too high; compaction can't keep up |
| Query fails or returns no results | Version accumulation blocking reads |
| High CPU, high P99 latency, queries hang | Compaction consuming resources; merge overhead |
| Compaction score stuck high (>50) | Unmerged versions accumulating |
| High resource usage (CPU/IO/Memory) | Compaction backlog from import burst |

Score below 50 is considered healthy.

---

## 3. Diagnostic Commands

### Check Compaction Score

**Enterprise Edition Metrics**:
- `fe_all_be_max_compaction_score` — overall score
- `be_max_base_compaction_score` — base compaction score
- `be_max_cumulative_compaction_score` — cumulative compaction score

**Community Edition Grafana**: Monitor title "BE Max Compaction Score", metric `starrocks_fe_tablet_max_compaction_score`

**Via BE Log** (score > 50 tablets):
```bash
grep -E 'compaction.*score=[5-9]{2,}' be.INFO* | tail -100

# Example output:
# I0226 22:34:10.025243 27375 tablet_manager.cpp:739] Found the best tablet to compact. 
# compaction_type=cumulative tablet_id=132561 highest_score=59
# compaction_type=base tablet_id=238743 highest_score=34
# compaction_type=update tablet_id=864228 highest_score=19
```

Compaction types in log:
- `cumulative` — non-Primary Key cumulative
- `base` — non-Primary Key base
- `update` — Primary Key (score can be very large due to different calculation)

### Check Compaction Status

**Note**: Run these commands on Leader FE.

```sql
-- Get tablet info (db, table, partition)
SHOW TABLET <tablet_id>;

-- Execute the detailcmd from above result to see full tablet details
-- Example: SHOW PROC '/dbs/10089/10092/10094';

-- Check VersionCount trend across 3 replicas
-- Compaction working => VersionCount decreasing

-- Access CompactionStatus URL from detail output
-- Shows last compaction time and current compaction info
```

---

## 4. Manual Compaction Trigger

### Primary Key Tables

**Method 1: Single tablet via curl**:
```bash
curl -XPOST '<be_ip>:<be_port>/api/compact?compaction_type=update&tablet_id=<tablet_id>&rowset_ids=1,2,3'
```

**Method 2: Partition-level (v2.5.6+)**:
```sql
-- Run on specific BE (backend_id from SHOW BACKENDS)
ADMIN EXECUTE ON <backend_id> '
  StorageEngine.submit_manual_compaction_task_for_partition(<partition_id>, <max_bytes>)
  System.print(StorageEngine.get_manual_compaction_status())
';

-- Example:
ADMIN EXECUTE ON 10002 '
  StorageEngine.submit_manual_compaction_task_for_partition(10089, 1000000)
  System.print(StorageEngine.get_manual_compaction_status())
';

-- Check status:
ADMIN EXECUTE ON 10002 'System.print(StorageEngine.get_manual_compaction_status())';
```

Parameters:
- `backend_id`: Get from `SHOW BACKENDS`
- `partition_id`: Get from `SHOW PARTITIONS FROM db.table_name`
- `max_bytes`: Rowsets smaller than this threshold will be compacted

### Non-Primary Key Tables

```bash
# Cumulative compaction on single tablet
curl -XPOST <be_ip>:<be_http_port>/api/compact?compaction_type=cumulative\&tablet_id=<tablet_id>

# Base compaction on single tablet
curl -XPOST <be_ip>:<be_http_port>/api/compact?compaction_type=base\&tablet_id=<tablet_id>

# Example (tablet_id=12345):
curl -XPOST 172.11.12.14:8030/api/compact?compaction_type=cumulative\&tablet_id=12345
```

---

## 5. Key Configuration Parameters

### Dynamic vs Static Parameters

- **Dynamic**: Modify online, persists until next BE restart. For permanent changes, add to `be.conf`.
- **Static**: Must modify `be.conf` and restart BE.

### Dynamic Parameter Modification

**v3.2+** (via SQL):
```sql
UPDATE information_schema.be_configs SET value = 8 WHERE name = "max_compaction_concurrency";

SELECT * FROM information_schema.be_configs WHERE name = "max_compaction_concurrency";
```

**v2.5+** (via curl, run on each BE):
```bash
# Modify parameter
curl -XPOST http://<BE_IP>:<BE_HTTP_PORT>/api/update_config?max_compaction_concurrency=8

# Check parameter value
curl http://<BE_IP>:<BE_HTTP_PORT>/varz | grep max_compaction_concurrency
```

### Critical Parameters

| Parameter | Default | Description | Dynamic |
|---|---|---|---|
| `max_compaction_concurrency` | -1 | Total compaction threads = (cumulative + base threads) * disk_num | Yes (v2.5+) |
| `base_compaction_check_interval_seconds` | 60 | Base compaction thread poll interval | Yes (v2.5+) |
| `min_base_compaction_num_singleton_deltas` | 5 | Minimum segments to trigger base compaction | Yes (v2.5+) |
| `max_base_compaction_num_singleton_deltas` | 100 | Maximum segments per base compaction | Yes (v2.5+) |
| `base_compaction_num_threads_per_disk` | 1 | Base compaction threads per disk | No (static) |
| `base_cumulative_delta_ratio` | 0.3 | Cumulative/Base file size ratio threshold | Yes (v2.5+) |
| `base_compaction_interval_seconds_since_last_operation` | 86400 | Time since last base compaction (trigger condition) | Yes (v2.5+) |
| `cumulative_compaction_check_interval_seconds` | 1 | Cumulative compaction poll interval | Yes (v2.5+) |
| `min_cumulative_compaction_num_singleton_deltas` | 5 | Minimum segments to trigger cumulative | Yes (v2.5+) |
| `max_cumulative_compaction_num_singleton_deltas` | 1000 | Maximum segments per cumulative compaction | Yes (v2.5+) |
| `cumulative_compaction_num_threads_per_disk` | 1 | Cumulative threads per disk | No (static) |
| `max_compaction_candidate_num` | 40960 | Max candidate tablets (too large = high memory/CPU) | Yes (v2.5+) |
| `update_compaction_check_interval_seconds` | 10 | Primary Key compaction check interval | Yes (v2.5+) |
| `update_compaction_num_threads_per_disk` | 1 | Primary Key threads per disk | Yes (can only increase, not decrease dynamically) |
| `update_compaction_per_tablet_min_interval_seconds` | 120 | Min interval between Primary Key tablet compactions | Yes (v2.5+) |
| `max_update_compaction_num_singleton_deltas` | 1000 | Max rowsets per Primary Key compaction | Yes (v2.5+) |
| `update_compaction_size_threshold` | 268435456 | PK compaction score normalization factor | Yes (v2.5+) |
| `update_compaction_result_bytes` | 1073741824 | Max result size per PK compaction | Yes (v2.5+) |
| `tablet_max_versions` | 1000 | Max unmerged versions per tablet | Yes (v2.3+) |

---

## 6. Issue: Too Many Versions

### Error Messages

**v2.5 and earlier**:
```
Too many versions. tablet_id: {}, version_count: {}, limit: {}
```

**v2.5+**:
```
Failed to load data into tablet {}, because of too many versions, current/limit: {}/{}.
```

### Diagnostic Steps

**Step 1: Identify the table**
```sql
-- Get table info from tablet_id (run on Leader FE)
SHOW TABLET <tablet_id>;

-- Execute detailcmd to see full tablet details
-- Check VersionCount across 3 replicas

-- Access CompactionStatus URL to see last compaction time
```

VersionCount interpretation:
- ~1000-2000: Short burst of imports or peak period
- Thousands to tens of thousands: Likely batch single-row DELETE statements

**Step 2: Check import pattern**
- Are there many single-row INSERT or DELETE statements?
- Routine Load: Is `max_batch_interval` set too small?
- Flink: Are parallelism/instance count too high?
- Stream Load: Is concurrency too high (e.g., DataX)?
- CloudCanal: Is sync interval too small?

**Step 3: Determine error frequency**

**Occasional errors with low version count**:
Temporary fix — increase `tablet_max_versions`:
```bash
# v2.3+ (run on each BE)
curl -XPOST http://<be_host>:<http_port>/api/update_config?tablet_max_versions=3000

# v3.2+ (via SQL)
UPDATE information_schema.be_configs SET value = 3000 WHERE name = "tablet_max_versions";

# Persist in be.conf
tablet_max_versions = 3000
```

**Frequent errors**:
Compaction cannot keep up. Need parameter tuning.

### Resolution: Tune Compaction

**Non-Primary Key tables**:
```bash
# Static parameters (add to be.conf on all BEs, then restart)
cumulative_compaction_num_threads_per_disk = 4   # default 1
base_compaction_num_threads_per_disk = 2         # default 1

# Dynamic parameters (v2.5+)
curl -XPOST http://<be_host>:<http_port>/api/update_config?cumulative_compaction_check_interval_seconds=2
curl -XPOST http://<be_host>:<http_port>/api/update_config?base_compaction_check_interval_seconds=10
curl -XPOST http://<be_host>:<http_port>/api/update_config?max_compaction_concurrency=10

# v3.2+ via SQL
UPDATE information_schema.be_configs SET value = 2 WHERE name = "cumulative_compaction_check_interval_seconds";
UPDATE information_schema.be_configs SET value = 10 WHERE name = "base_compaction_check_interval_seconds";
```

**Primary Key tables**:
```bash
# Dynamic (can only increase, not decrease)
curl -XPOST http://<be_host>:<http_port>/api/update_config?update_compaction_num_threads_per_disk=2
curl -XPOST http://<be_host>:<http_port>/api/update_config?update_compaction_check_interval_seconds=10

# v3.2+
UPDATE information_schema.be_configs SET value = 2 WHERE name = "update_compaction_num_threads_per_disk";
UPDATE information_schema.be_configs SET value = 10 WHERE name = "update_compaction_check_interval_seconds";
```

### Resolution: Reduce Import Frequency

**Routine Load**:
```sql
ALTER ROUTINE LOAD FOR <job_name>
PROPERTIES
(
  "max_batch_interval" = "60",     -- default 10, increase to reduce frequency
  "desired_concurrent_number" = "5"  -- reduce parallelism
);
```

**Flink Connector**:
- Reduce task parallelism/instance count
- For `at-least-once`: increase `sink.buffer-flush.maxbytes`, `sink.buffer-flush.maxrows`, `sink.buffer-flush.interval-ms`
- For `exactly-once`: increase Flink checkpoint interval

| Parameter | Default | Description |
|---|---|---|
| `sink.buffer-flush.maxbytes` | 94MB (90M) | Memory buffer threshold for flush |
| `sink.buffer-flush.maxrows` | 500000 | Row count threshold for flush |
| `sink.buffer-flush.interval-ms` | 300000 | Flush interval (ms) |

---

## 7. Issue: DELETE-Induced Version Accumulation

DELETE triggers base compaction, which is expensive and more likely to cause backlog.

### Diagnosis

```bash
# Check tablet compaction status for DELETE markers
# (via CompactionStatus URL from SHOW TABLET)

# Count DELETE statements in audit log
grep -i 'delete from <table_name>' fe.audit.log | wc -l
```

### Recovery Options

**Option 1: Force delete table (fast recovery)**
```sql
-- Force delete to prevent FE metadata lingering
DROP TABLE <table_name> FORCE;

-- Note: Ensure data is backed up elsewhere or can be re-imported
-- If query still works: INSERT INTO new_table SELECT * FROM old_table
```

**Option 2: Tune compaction parameters**
- Requires BE restart for static parameters
- Expect short-term CPU/IO increase

**Option 3: Wait for background compaction**
- Monitor compaction progress via CompactionStatus URL

---

## 8. Issue: Query Slowdown or Failure

### Single Table Query Slow

Excessive versions require multi-version merge during query.

Check during slowdown period:
- Many INSERT statements?
- Import frequency/concurrency changes?
- Many DELETE statements?

### Multi-Table Query Slow (Case Example)

**Symptoms**: CPU saturated, compaction score >50K, P99 5min, `SELECT 1` hangs for 10s

**Analysis**:
- DELETE task triggered at 1AM, sending 8500+ single-row DELETE statements over 14 hours
- Table VersionCount reached 35K+
- Compaction threads (`compact_pool`) and query threads (`pip_wg_executor`) competing for CPU

**Resolution**:
1. Stop DELETE task
2. `DROP TABLE ... FORCE`
3. Compaction score drops, P99 drops, CPU drops, queries resume

---

## 9. Issue: High Compaction Resource Usage

### Diagnosis

```bash
# Check compaction thread CPU usage
top -Hp <be_pid>
# Look for threads named "compact_pool"

# Check IO usage
iotop
```

### Mitigation

**Control concurrency**:
```sql
-- v3.2+
UPDATE information_schema.be_configs SET value = 4 WHERE name = "max_compaction_concurrency";
```

**Raise trigger threshold** (trade-off: more rowsets retained, may impact query):
```sql
UPDATE information_schema.be_configs SET value = 10 WHERE name = "min_cumulative_compaction_num_singleton_deltas";
```

**Periodic base compaction impact**:
- Base compaction triggered by `base_compaction_interval_seconds_since_last_operation` can consume resources
- Check log for `force` flag in compaction task
- v2.5.8 has optimizations

### Large Tablet Cluster Upgrade to v2.5

**Issue**: Compaction threads saturate IO after upgrade

**Root cause**: Old version scheduling inefficient for large tablet counts; previous thread config or many disks lead to high concurrency.

**Fix**:
```sql
-- Control concurrency
UPDATE information_schema.be_configs SET value = 8 WHERE name = "max_compaction_concurrency";

-- Prevent long-uncompacted tablets triggering simultaneously
UPDATE information_schema.be_configs SET value = 172800 WHERE name = "base_compaction_interval_seconds_since_last_operation";
```

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| `too many versions` import error | Compaction lag | Tune threads; reduce import frequency; increase `tablet_max_versions` (temporary) |
| Query fails on high-version tablet | Merge overhead too large | Reduce import frequency; manual compaction |
| Compaction score stuck >50 | Unmerged versions accumulating | Check import pattern; tune compaction |
| High CPU from compaction | Thread count too high; DELETE burst | Reduce `max_compaction_concurrency`; stop DELETE task |
| IO saturated after v2.5 upgrade | Scheduling efficiency change | Control `max_compaction_concurrency` |
| Primary Key score very large | Different scoring mechanism | Normal; tune `update_compaction_*` parameters |

---

## Related Cases

- `case-014-scan-skew` — MERGE phase bottleneck from version accumulation
- `case-003-fe-deadlock` — Version-not-found during query

---

## Resources

- [Compaction mechanism documentation](https://docs.starrocks.io/docs/administration/management/compaction/)