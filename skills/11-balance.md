---
type: skill
category: balance
priority: 11
keywords: [balance, tablet scheduler, clone, repair, decommission, colocate, replica missing, disk balance]
---

# 11 - Balance & Tablet Scheduler Troubleshooting

Investigation guide for tablet scheduling, cluster balance, replica repair, and
decommission issues.

---

## 1. Observability Commands

### Cluster Statistics

```sql
-- View database-level tablet statistics
SHOW PROC "/statistic";

-- Check unhealthy tablets in a specific database
SHOW PROC "/statistic/<db_id>";
```

| Column | Description |
|---|---|
| UnhealthyTabletNum | Tablets with missing replicas, incomplete versions, colocate mismatch, location mismatch |
| InconsistentTabletNum | Tablets with inconsistent data across replicas |
| CloningTabletNum | Tablets currently in clone process |
| ErrorStateTabletNum | Tablets in error state (PK tables only) |

### Cluster Balance Overview

```sql
-- View balance summary
SHOW PROC "/cluster_balance";
```

| Item | Description |
|---|---|
| cluster_load_stat | Load status by disk medium type |
| working_slots | Available/total working slots per BE path |
| sched_stat | Scheduler statistics (snapshot every 20s) |
| priority_repair | Tablets needing priority repair |
| pending_tablets | Tablets waiting for scheduling |
| running_tablets | Tablets currently being processed |
| history_tablets | Recently completed tablets (max 1000) |

### Scheduler Statistics (3.5+)

```sql
-- Detailed scheduling stats with Increase column
SHOW PROC "/cluster_balance/sched_stat";
```

Key metrics by category:

| Category | Metric | Description |
|---|---|---|
| Tablet checker | num of tablet check round | Total rounds executed (paused if pending/running exceeds limit) |
| Tablet scheduler | num of tablet being scheduled succeeded | Successful schedules |
| Clone task | num of clone task succeeded/failed/timeout | Clone task outcomes |
| Unhealthy type | num of replica missing error | Missing replica clone tasks |
| Unhealthy type | num of replica version missing error | Missing version clone tasks |
| Balance | num of balance scheduled | Balance clone tasks |
| Colocate | num of colocate replica mismatch/redundant | Colocate balance tasks |

### Load Statistics

```sql
-- BE disk usage and replica count by medium type
SHOW PROC "/cluster_balance/cluster_load_stat/HDD";
SHOW PROC "/cluster_balance/cluster_load_stat/SSD";

-- BE path slot usage
SHOW PROC "/cluster_balance/working_slots";
```

### Tablet Queue Inspection

```sql
-- View pending, running, history tablets
SHOW PROC "/cluster_balance/pending_tablets";
SHOW PROC "/cluster_balance/running_tablets";
SHOW PROC "/cluster_balance/history_tablets";
```

History tablet columns include: TabletId, Type, Status, State, Priority, SrcBe/DestBe, Timeout, Rate, ErrMsg.

### Balance Status (3.5+)

```sql
-- Balance overview by type
SHOW PROC "/cluster_balance/balance_stat";
```

Balance types: `inter-node disk usage`, `inter-node tablet distribution`, `intra-node disk usage`, `intra-node tablet distribution`, `colocation group`, `label-aware location`.

System prioritizes inter-node balance before intra-node balance.

---

## 2. System Tables & Metrics

### FE Tablet Schedules Table

```sql
-- Query clone task history by table
SELECT * FROM information_schema.fe_tablet_schedules
WHERE table_id = <table_id>;
```

Contains pending, running, and history tasks with: TABLET_ID, TYPE, STATE, SCHEDULE_REASON, PRIORITY, VISIBLE_VERSION, CLONE_BYTES, CLONE_DURATION, FAILED_SCHEDULE_COUNT, FAILED_RUNNING_COUNT, MSG.

### BE Tablets Table

```sql
SELECT * FROM information_schema.be_tablets LIMIT 10;
```

Shows: BE_ID, TABLE_ID, TABLET_ID, NUM_VERSION, NUM_ROW, DATA_SIZE, INDEX_MEM, STATE, TYPE, DATA_DIR, MEDIUM_TYPE.

### Partitions Meta (Tablet Balance)

```sql
-- Find partitions with unbalanced tablet distribution (3.5+)
SELECT * FROM information_schema.partitions_meta WHERE tablet_balanced = 0;
```

### Metrics (3.5+)

FE metrics:
- `starrocks_fe_scheduled_tablet_num` — tablets being scheduled
- `starrocks_fe_scheduled_pending_tablet_num{type="BALANCE/REPAIR"}` — pending by type
- `starrocks_fe_scheduled_running_tablet_num{type="BALANCE/REPAIR"}` — running by type
- `starrocks_fe_clone_task_total/success` — clone task counters
- `starrocks_fe_clone_task_copy_duration_ms/bytes{type="INTER_NODE/INTRA_NODE"}` — clone performance

BE metrics:
- `starrocks_be_clone_task_copy_bytes/duration_ms{type="INTER_NODE/INTRA_NODE"}`
- `starrocks_be_engine_requests_total{status="failed",type="clone"}`

---

## 3. Management Commands

### Replica Status

```sql
-- Mark replica as bad (triggers repair)
ADMIN SET REPLICA STATUS PROPERTIES("tablet_id" = "10003", "backend_id" = "10001", "status" = "bad");

-- Restore replica status
ADMIN SET REPLICA STATUS PROPERTIES("tablet_id" = "10003", "backend_id" = "10001", "status" = "ok");
```

### Priority Repair

```sql
-- High-priority repair for table/partition
ADMIN REPAIR TABLE tbl1;
ADMIN REPAIR TABLE tbl1 PARTITION (p1, p2);

-- Cancel repair
ADMIN CANCEL REPAIR TABLE tbl1;
```

### Queue Cleanup

```sql
-- Clear all pending/running tasks
ALTER SYSTEM CLEAN TABLET SCHEDULER QUEUE;
```

---

## 4. Configuration Reference

### FE Configuration

| Type | Config | Default | Description |
|---|---|---|---|
| Common | tablet_sched_slot_num_per_path | 8 | Slots per BE path for clone tasks |
| Common | tablet_sched_max_scheduling_tablets | 1000 | Max concurrent scheduling tablets |
| Common | tablet_sched_max_not_be_scheduled_interval_ms | 15min | Time before priority upgrade |
| Common | tablet_sched_min_clone_task_timeout_sec | 3min | Min clone timeout |
| Common | tablet_sched_max_clone_task_timeout_sec | 2hr | Max clone timeout |
| Balance | tablet_sched_disable_balance | false | Disable non-colocate balance |
| Balance | tablet_sched_disable_colocate_balance | false | Disable colocate balance |
| Balance | tablet_sched_max_balancing_tablets | 500 | Max tablets in balance |
| Balance | tablet_sched_balance_load_score_threshold | 0.1 | Load difference threshold to trigger balance |
| Balance | tablet_sched_balance_load_disk_safe_threshold | 0.5 | Max disk usage threshold for balance |
| Repair | tablet_sched_checker_interval_seconds | 20s | Tablet check interval |
| Repair | tablet_sched_be_down_tolerate_time_s | 15min | BE down tolerance before repair |
| Repair | tablet_sched_colocate_be_down_tolerate_time_s | 12hr | BE down tolerance for colocate repair |
| Repair | tablet_sched_repair_delay_factor_second | 60s | Repair delay (HIGH=60s, NORMAL=120s, LOW=180s) |

### BE Configuration

| Config | Default | Description |
|---|---|---|
| parallel_clone_task_per_path | 8 | Clone threads per path (8 * disk count) |

---

## 5. Troubleshooting Scenarios

### Scenario A: Check Balance Status

1. **3.5+ version**:
   ```sql
   SHOW PROC "/cluster_balance/balance_stat";
   SHOW PROC "/cluster_balance/cluster_load_stat";
   ```

   - `ClusterDiskBalanceStat` shows max/min disk usage and affected BEs
   - `BackendDiskBalanceStat` shows intra-node disk imbalance with paths

2. **Pre-3.5 version**:
   ```sql
   -- Disk usage check (max-min > 0.1 indicates imbalance)
   SHOW BACKENDS;
   SHOW PROC "/cluster_balance/cluster_load_stat/HDD";

   -- Tablet distribution check (max-min > 1 indicates imbalance)
   SELECT partition_id, max_cnt, min_cnt
   FROM (
     SELECT partition_id, MAX(cnt) AS max_cnt, MIN(cnt) AS min_cnt
     FROM (
       SELECT partition_id, be_id, COUNT(*) AS cnt
       FROM information_schema.be_tablets
       GROUP BY partition_id, be_id
     ) AS be_tablet_count
     GROUP BY partition_id
   ) AS partition_stats
   WHERE (max_cnt - min_cnt) > 1;
   ```

### Scenario B: Balance Too Slow

1. Check clone task status:
   ```sql
   SHOW PROC "/statistic";       -- CloningTablets
   SHOW PROC "/cluster_balance";  -- pending_tablets, running_tablets
   SHOW PROC "/cluster_balance/working_slots";  -- slot usage
   ```

2. If clone tasks are low, increase:
   ```sql
   -- FE
   ADMIN SET FRONTEND CONFIG ("tablet_sched_slot_num_per_path" = "16");
   ADMIN SET FRONTEND CONFIG ("tablet_sched_max_scheduling_tablets" = "2000");
   ADMIN SET FRONTEND CONFIG ("tablet_sched_max_balancing_tablets" = "1000");

   -- BE (edit be.conf)
   parallel_clone_task_per_path = 16
   ```

### Scenario C: Balance Too Active (Impacts Other Tasks)

1. Reduce configuration:
   ```sql
   ADMIN SET FRONTEND CONFIG ("tablet_sched_slot_num_per_path" = "4");
   ADMIN SET FRONTEND CONFIG ("tablet_sched_max_balancing_tablets" = "200");
   ```

2. Clear queue:
   ```sql
   ALTER SYSTEM CLEAN TABLET SCHEDULER QUEUE;
   ```

### Scenario D: Decommission BE Stuck

Common causes:
- 3 BEs remaining with tables having 3 replicas
- Tables in FE recycle bin
- Statistics system tables with 3 replicas

1. Check FE leader log:
   ```log
   backend 29194 lefts 1056 replicas to decommission(show up to 20): [28515, ...]
   ```

2. If tablet info shows null db/table/partition, may be in recycle bin:
   ```sql
   ADMIN SET FRONTEND CONFIG ("catalog_trash_expire_second" = "60");
   ```

3. Check tables with >2 replicas:
   ```sql
   SELECT db_name, table_name, partition_name
   FROM information_schema.partitions_meta
   WHERE replication_num > 2;
   ```

4. Check clone history for `REPLICA_RELOCATING` failures:
   ```sql
   SHOW PROC "/cluster_balance/history_tablets";
   ```

### Scenario E: Balance/Repair Failures

Check clone task history by tablet_id:
```sql
SHOW PROC "/cluster_balance/history_tablets";
-- or use system table
SELECT * FROM information_schema.fe_tablet_schedules
WHERE tablet_id = <tablet_id> ORDER BY create_time DESC;
```

Common error messages:
- `unable to find dest path for new replica` — No available destination path
- `redundant replica is deleted` — Successfully removed redundant replica

### Scenario F: Colocate Group Issues

```sql
-- View colocate groups
SHOW PROC "/colocation_group";

-- Check group balance status
SHOW PROC "/colocation_group/<group_id>";
```

If colocate group unstable:
- Check `tablet_sched_colocate_be_down_tolerate_time_s` (default 12hr)
- Check `tablet_sched_colocate_balance_wait_system_stable_time_s` (default 15min)

---

## 6. Tablet Scheduler Status Types

| Status | Description |
|---|---|
| REPLICA_MISSING | Missing replica count |
| REPLICA_VERSION_MISSING | Missing version on replica |
| REPLICA_RELOCATING | Replica being relocated (decommission) |
| REPLICA_LOCATION_MISMATCH | Location constraint violation |
| REDUNDANT | Excess replicas to delete |
| VERSION_INCOMPLETE | Incomplete versions |

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| Balance too slow | Low slot count or scheduling limit | Increase slot and max_scheduling_tablets |
| Balance impacts load | Too many concurrent clones | Reduce slot count; clear queue |
| Decommission stuck | 3-replica tables with only 3 BEs | Reduce replica num; add BE |
| Decommission stuck | Tables in recycle bin | Shorten catalog_trash_expire_second |
| Clone task failed | No available dest path | Check disk space; check BE status |
| Colocate unstable | BE down recently | Wait tolerate_time; check BE health |
| Replica missing long time | BE down > tolerate_time | Check BE; or manual repair |

---

## Related Cases

- `case-004-disk-balancing` — IO saturation from migration retry loop

---

## Resources

- [Tablet Scheduler Documentation](https://docs.starrocks.io/docs/administration/management/tablet_management/)
- [fe_tablet_schedules System Table](https://docs.starrocks.io/docs/sql-reference/information_schema/fe_tablet_schedules/)