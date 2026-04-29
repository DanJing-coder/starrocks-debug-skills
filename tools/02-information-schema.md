---
type: tool
category: information-schema
keywords: [information_schema, tables, loads, be_tablets, be_metrics, fe_metrics, task_runs, materialized_views, compaction, routine_load, tablet, partition, statistics, RBAC, permissions]
---

# 02 - Information Schema Diagnostic Queries

A comprehensive collection of diagnostic SQL queries using StarRocks information_schema system tables.

---

## 1. Tables - Capacity Analysis

### Internal Tables

```sql
-- Database data size (GB)
SELECT
    TABLE_SCHEMA AS dbname,
    ROUND(SUM(DATA_LENGTH)/1024/1024/1024, 3) AS datasize
FROM information_schema.tables
GROUP BY TABLE_SCHEMA;

-- Database row count
SELECT
    TABLE_SCHEMA AS dbname,
    SUM(TABLE_ROWS) AS table_rows
FROM information_schema.tables
GROUP BY TABLE_SCHEMA;

-- Top 3 largest tables per database
WITH ranked_tables AS (
    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        DATA_LENGTH,
        ROUND(DATA_LENGTH / 1024 / 1024 / 1024, 2) AS DATA_LENGTH_GB,
        ROW_NUMBER() OVER (
            PARTITION BY TABLE_SCHEMA
            ORDER BY DATA_LENGTH DESC
        ) AS rn
    FROM INFORMATION_SCHEMA.TABLES
)
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    DATA_LENGTH_GB
FROM ranked_tables
WHERE rn <= 3
ORDER BY TABLE_SCHEMA, DATA_LENGTH_GB DESC;
```

### External Tables

```sql
-- External catalog tables (limited info available)
SHOW CATALOGS;
SET CATALOG xxx;
SELECT * FROM information_schema.tables;
-- Note: External tables may show NULL for many fields
```

---

## 2. Tables_Config - Index Configuration

```sql
-- Find tables with Bloom Filter index
SELECT
    table_schema,
    table_name,
    table_model,
    primary_key,
    partition_key,
    distribute_key,
    sort_key,
    regexp_extract(properties, '"bloom_filter_columns":"([^"]+)"', 1) AS bloom_cols
FROM information_schema.tables_config
WHERE properties LIKE '%"bloom_filter_columns"%';
```

---

## 3. BE_DataCache_Metrics - Data Cache Status

```sql
-- Data Cache memory and disk capacity (shared-data clusters)
SELECT * FROM information_schema.be_datacache_metrics;
```

| Field | Description |
|---|---|
| BE_ID | Backend ID |
| STATUS | Normal/Abnormal |
| DISK_QUOTA_BYTES | Disk quota |
| DISK_USED_BYTES | Disk used |
| MEM_QUOTA_BYTES | Memory quota |
| MEM_USED_BYTES | Memory used |
| META_USED_BYTES | Metadata memory |
| DIR_SPACES | Disk space details |

---

## 4. Loads - Import Job Analysis

### 4.1 Failed Import Detection

```sql
-- Failed imports in last 24 hours
SELECT
    ID,
    LABEL,
    TYPE,
    STATE,
    ERROR_MSG,
    TRACKING_SQL,
    CREATE_TIME,
    LOAD_FINISH_TIME
FROM information_schema.loads
WHERE STATE = 'CANCELLED'
  AND CREATE_TIME > NOW() - INTERVAL 1 DAY
ORDER BY CREATE_TIME DESC;
```

### 4.2 Data Quality Issues

```sql
-- Tasks with filtered rows (dirty data)
SELECT
    LABEL,
    DB_NAME,
    TABLE_NAME,
    SCAN_ROWS,
    FILTERED_ROWS,
    (FILTERED_ROWS / SCAN_ROWS) * 100 AS filter_rate_percent,
    REJECTED_RECORD_PATH
FROM information_schema.loads
WHERE FILTERED_ROWS > 0
ORDER BY CREATE_TIME DESC
LIMIT 20;
```

### 4.3 Import Performance Analysis

```sql
-- Slow imports (stage-by-stage timing)
SELECT
    LABEL,
    TYPE,
    SCAN_ROWS,
    SINK_ROWS,
    TIMESTAMPDIFF(SECOND, CREATE_TIME, LOAD_START_TIME) AS queue_time_sec,
    TIMESTAMPDIFF(SECOND, LOAD_START_TIME, LOAD_COMMIT_TIME) AS load_time_sec,
    TIMESTAMPDIFF(SECOND, LOAD_COMMIT_TIME, LOAD_FINISH_TIME) AS commit_time_sec,
    (SCAN_BYTES / 1024 / 1024) / TIMESTAMPDIFF(SECOND, LOAD_START_TIME, LOAD_COMMIT_TIME) AS throughput_mb_s
FROM information_schema.loads
WHERE STATE = 'FINISHED'
  AND TIMESTAMPDIFF(SECOND, CREATE_TIME, LOAD_FINISH_TIME) > 60
ORDER BY load_time_sec DESC;
```

### 4.4 Stream Load Client Distribution

```sql
-- Stream Load client analysis (FE metadata pressure check)
SELECT
    get_json_object(RUNTIME_DETAILS, '$.client_ip') AS client_ip,
    COUNT(*) AS load_count,
    AVG(CAST(get_json_object(RUNTIME_DETAILS, '$.begin_txn_time_ms') AS SIGNED)) AS avg_begin_txn_ms,
    AVG(CAST(get_json_object(RUNTIME_DETAILS, '$.receive_data_time_ms') AS SIGNED)) AS avg_receive_ms
FROM information_schema.loads
WHERE TYPE = 'STREAM_LOAD'
  AND CREATE_TIME > NOW() - INTERVAL 1 HOUR
GROUP BY 1
ORDER BY 3 DESC;
```

### 4.5 BE-Related Import Issues

```sql
-- Imports on specific BE (backend_id = 311686287)
SELECT
    ID,
    LABEL,
    TABLE_NAME,
    RUNTIME_DETAILS
FROM information_schema.loads
WHERE CAST(RUNTIME_DETAILS AS STRING) LIKE '%311686287%'
  AND STATE = 'LOADING'
  AND CREATE_TIME > NOW() - INTERVAL 1 HOUR;
```

### 4.6 Resource Audit

```sql
-- Database write pressure (last 24 hours)
SELECT
    DB_NAME,
    COUNT(*) AS load_count,
    SUM(CASE WHEN SCAN_BYTES > 0 THEN SCAN_BYTES ELSE 0 END) / 1024 / 1024 / 1024 AS total_scan_gb,
    SUM(CASE WHEN SINK_ROWS > 0 THEN SINK_ROWS ELSE 0 END) AS total_sink_rows,
    AVG(TIMESTAMPDIFF(SECOND, CREATE_TIME, LOAD_FINISH_TIME)) AS avg_duration_sec
FROM information_schema.loads
WHERE STATE = 'FINISHED' AND CREATE_TIME > NOW() - INTERVAL 1 DAY
GROUP BY DB_NAME
ORDER BY total_scan_gb DESC;
```

### 4.7 Small File Risk Detection

```sql
-- High-frequency small imports (version explosion risk)
SELECT
    DB_NAME,
    TABLE_NAME,
    DATE_FORMAT(CREATE_TIME, '%Y-%m-%d %H:%i') AS minute_slot,
    COUNT(*) AS load_per_minute,
    AVG(SCAN_BYTES) / 1024 AS avg_load_kb
FROM information_schema.loads
WHERE TYPE = 'STREAM_LOAD' AND CREATE_TIME > NOW() - INTERVAL 1 HOUR
GROUP BY 1, 2, 3
HAVING load_per_minute > 10
ORDER BY load_per_minute DESC;
```

**Recommendation**: If avg_load_kb is only tens of KB with high frequency, increase Flink Sink `buffer_flush_interval` or `batch_size`.

### 4.8 Zombie Task Detection

```sql
-- Tasks running > 30 minutes without completion
SELECT
    ID,
    LABEL,
    USER,
    STATE,
    TYPE,
    TIMESTAMPDIFF(MINUTE, CREATE_TIME, NOW()) AS running_minutes,
    get_json_object(RUNTIME_DETAILS, '$.txn_id') AS txn_id,
    get_json_object(PROPERTIES, '$.timeout') AS config_timeout
FROM information_schema.loads
WHERE STATE NOT IN ('FINISHED', 'CANCELLED')
  AND CREATE_TIME < NOW() - INTERVAL 30 MINUTE;
```

**Action**: Cancel zombie tasks with `CANCEL LOAD FROM db_name WHERE LABEL = "xxx";`

### 4.9 Data Skew Detection

```sql
-- BE distribution for specific large job
SELECT
    ID,
    LABEL,
    TABLE_NAME,
    get_json_object(RUNTIME_DETAILS, '$.backends') AS participating_backends,
    get_json_object(RUNTIME_DETAILS, '$.unfinished_backends') AS stuck_backends
FROM information_schema.loads
WHERE ID = 1482344928;  -- Replace with your Job ID
```

### 4.10 Timeout Analysis

```sql
-- Timeout tasks with progress analysis
SELECT
    LABEL,
    SCAN_ROWS,
    SCAN_BYTES / 1024 / 1024 AS scan_mb,
    CAST(get_json_object(PROPERTIES, '$.timeout') AS SIGNED) AS config_timeout_sec,
    TIMESTAMPDIFF(SECOND, CREATE_TIME, LOAD_FINISH_TIME) AS actual_duration_sec,
    ERROR_MSG
FROM information_schema.loads
WHERE STATE = 'CANCELLED'
  AND (ERROR_MSG LIKE '%timeout%' OR ERROR_MSG LIKE '%Timeout%')
ORDER BY CREATE_TIME DESC;
```

### 4.11 Dirty Data Query Generation

```sql
-- Generate dirty data debug SQL
SELECT
    CONCAT('/* Dirty data: ', LABEL, ' */ ', TRACKING_SQL) AS debug_sql
FROM information_schema.loads
WHERE FILTERED_ROWS > 0
  AND TRACKING_SQL IS NOT NULL
ORDER BY CREATE_TIME DESC
LIMIT 5;
```

---

## 5. Stream_Loads - Real-time Import Monitoring

```sql
-- Stream Load table statistics (last 1 hour)
SELECT
    DB_NAME,
    TABLE_NAME,
    COUNT(*) AS load_count,
    SUM(NUM_LOAD_BYTES) / 1024 / 1024 AS total_mb,
    AVG(TIMEOUT_SECOND) AS avg_timeout,
    AVG(END_TIME_MS - START_LOADING_TIME_MS) / 1000 AS avg_duration_sec
FROM information_schema.stream_loads
WHERE STATE = 'FINISHED'
  AND CREATE_TIME_MS > (UNIX_TIMESTAMP(NOW() - INTERVAL 1 HOUR) * 1000)
GROUP BY DB_NAME, TABLE_NAME
ORDER BY total_mb DESC;
```

---

## 6. BE_Cloud_Native_Compactions - Shared-Data Compaction

> **Note**: Only available in shared-data (cloud-native) clusters.

```sql
SELECT * FROM information_schema.be_cloud_native_compactions;
```

| Field | Description |
|---|---|
| BE_ID | Backend ID |
| TXN_ID | Transaction ID |
| TABLET_ID | Tablet ID |
| VERSION | Version number |
| PROGRESS | Progress percentage |
| STATUS | Error message if any |
| PROFILE | Execution metrics (v3.2.12+, v3.3.5+) |

### Profile Fields (JSON)

| Field | Description |
|---|---|
| read_local_sec | Local cache read time (seconds) |
| read_local_mb | Local cache read size (MB) |
| read_remote_sec | Remote S3/HDFS read time (seconds) |
| read_remote_mb | Remote read size (MB) |
| read_remote_count | Remote read count |
| read_local_count | Local cache read count |
| in_queue_sec | Queue wait time (seconds) |

---

## 7. BE_Threads - Thread Analysis

### Thread Comparison Across BEs

```sql
-- Compare thread counts across BE nodes
SELECT
    NAME,
    SUM(IF(BE_ID = 10001, 1, 0)) AS BE_10001,
    SUM(IF(BE_ID = 19097, 1, 0)) AS BE_19097,
    SUM(IF(BE_ID = 19495, 1, 0)) AS BE_19495
FROM information_schema.be_threads
GROUP BY NAME
ORDER BY NAME;
```

> **Note**: Get BE_ID from `SHOW BACKENDS` BackendId column. If one BE has significantly higher thread counts than others, investigate potential issues.

### Resource Group Threads

```sql
-- Resource group thread allocation
SELECT BE_ID, NAME, BOUND_CPUS
FROM information_schema.be_threads
WHERE NAME IN (
    'pip_exec_<resource_group_id>',
    'pip_scan_<resource_group_id>',
    'pip_con_scan_<resource_group_id>'
);
```

---

## 8. BE_Txns - Large Import Detection

```sql
-- Large imports within time range
SELECT
    SUM(NUM_ROW) AS load_rows,
    SUM(DATA_SIZE) AS total_size,
    TXN_ID
FROM be_txns
WHERE PUBLISH_TIME BETWEEN
    UNIX_TIMESTAMP('2025-01-04 09:00:00') AND
    UNIX_TIMESTAMP('2025-01-04 10:00:00')
GROUP BY TXN_ID
ORDER BY total_size;
```

---

## 9. BE_Compactions - Compaction Health

```sql
SELECT * FROM information_schema.be_compactions;
```

> **Criteria**: `LATEST_COMPACTION_SCORE` and `CANDIDATE_MAX_SCORE` < 100 indicates healthy state.

---

## 10. Partitions_Meta & BE_Tablets - Tablet Health

### Rowset/Segment Overflow Detection

```sql
-- Tables with too many versions or segments
SELECT
    pm.DB_NAME,
    pm.TABLE_NAME,
    tbt.TABLET_ID,
    tbt.NUM_VERSION,
    tbt.NUM_SEGMENT,
    tbt.DATA_SIZE / (1024 * 1024 * 1024) AS data_size_gb
FROM information_schema.partitions_meta pm
JOIN information_schema.be_tablets tbt ON pm.PARTITION_ID = tbt.PARTITION_ID
WHERE tbt.NUM_ROWSET > 100
   OR tbt.NUM_SEGMENT > 50
ORDER BY tbt.NUM_VERSION DESC, tbt.NUM_SEGMENT DESC
LIMIT 10;
```

> **Impact**: Too many versions/segments increase scan overhead and reduce query efficiency.
> **Solution**: Reduce import frequency or trigger compaction via `ALTER TABLE ... COMPACT`.

### Abnormal Replica Detection

```sql
-- Tablets with abnormal replica state
SELECT
    pm.DB_NAME,
    pm.TABLE_NAME,
    tbt.TABLET_ID,
    tbt.BE_ID,
    tbt.STATE,
    tbt.DATA_SIZE / (1024 * 1024 * 1024) AS data_size_gb
FROM information_schema.partitions_meta pm
JOIN information_schema.be_tablets tbt ON pm.PARTITION_ID = tbt.PARTITION_ID
WHERE tbt.STATE NOT IN ('NORMAL', 'RUNNING')
ORDER BY pm.DB_NAME, pm.TABLE_NAME, tbt.TABLET_ID;
```

---

## 11. FE_Metrics - FE Monitoring

```sql
-- Edit Log count per FE
SELECT
    NAME,
    SUM(IF(FE_ID = '172.26.92.154_19010_1716174646625', VALUE, NULL)) AS FE_154,
    SUM(IF(FE_ID = '172.26.194.184_19010_1765939312252', VALUE, NULL)) AS FE_184,
    SUM(IF(FE_ID = '172.26.92.155_19010_1762244987643', VALUE, NULL)) AS FE_155
FROM fe_metrics
WHERE NAME = 'meta_log_count'
GROUP BY NAME
ORDER BY NAME;
```

---

## 12. BE_Metrics - Memory Usage

```sql
-- Memory metrics per BE
SELECT
    NAME,
    SUM(IF(BE_ID = 10001, VALUE, NULL)) AS BE_10001,
    SUM(IF(BE_ID = 19097, VALUE, NULL)) AS BE_19097,
    SUM(IF(BE_ID = 19495, VALUE, NULL)) AS BE_19495
FROM be_metrics
WHERE NAME LIKE '%mem_bytes'
   OR NAME LIKE '%malloc%'
GROUP BY NAME
ORDER BY NAME;
```

---

## 13. Tasks & Task_Runs - ETL Task Monitoring

```sql
-- List all tasks
SELECT * FROM INFORMATION_SCHEMA.tasks;
SELECT * FROM information_schema.tasks WHERE task_name = '<task_name>';

-- List task runs with status
SELECT * FROM INFORMATION_SCHEMA.task_runs;
SELECT * FROM information_schema.task_runs WHERE task_name = '<task_name>';
```

### TaskRun States

| State | Description |
|---|---|
| PENDING | Waiting to execute |
| RUNNING | Executing |
| FAILED | Execution failed |
| SUCCESS | Execution successful |

---

## 14. Load_Tracking_Logs - Import Error Details

> Available since v3.0.

```sql
-- Query by label (use JOB_ID or LABEL from loads view)
SELECT * FROM information_schema.load_tracking_logs
WHERE label = 'user_behavior'\G
```

---

## 15. Pipe_Files & Pipes - Pipe Import Status

> Available since v3.2.

```sql
-- Pipe file import status
SELECT * FROM information_schema.pipe_files;

-- Pipe details
SELECT * FROM information_schema.pipes;

-- Alternative command
SHOW PIPES;
```

---

## 16. Routine_Load_Jobs - Routine Import Monitoring

```sql
SELECT * FROM information_schema.routine_load_jobs;
```

---

## 17. Statistics - Index Suitability Analysis

```sql
-- Check statistics table
SELECT * FROM _statistics_.table_statistic_v1;
```

### Index Suitability Criteria

| Index Type | Suitable Condition |
|---|---|
| BITMAP | `distinct_count / row_count < 80%` AND `distinct_count` between 100-100,000 |
| BLOOM FILTER | `distinct_count / row_count > 80%` |

---

## 18. Sys Schema - RBAC & Permissions

> **Note**: Must `USE sys;` first. Only users with `user_admin` role can query these views.

### 18.1 Grants_to_Roles

```sql
USE sys;
SELECT * FROM grants_to_roles WHERE OBJECT_DATABASE = 'rbac_test';
```

### 18.2 Grants_to_Users

```sql
USE sys;
SELECT * FROM grants_to_users WHERE OBJECT_DATABASE = 'rbac_test' AND GRANTEE LIKE '%user%';
```

### 18.3 Role_Edges

```sql
USE sys;
SELECT * FROM role_edges WHERE FROM_ROLE LIKE '%role%';
```

### 18.4 User Direct Permissions

```sql
USE sys;
SELECT * FROM grants_to_users WHERE GRANTEE = "'user_g'@'%'";
```

### 18.5 User Inherited Permissions via Roles

```sql
USE sys;
-- Direct role grants to user
SELECT DISTINCT
    gr.GRANTEE AS RoleOrUser,
    gr.OBJECT_DATABASE AS ObjectDatabase,
    gr.OBJECT_NAME AS ObjectName,
    gr.PRIVILEGE_TYPE AS PrivilegeType
FROM grants_to_roles gr
JOIN role_edges re1 ON gr.GRANTEE = re1.FROM_ROLE
WHERE re1.TO_USER = "'user_g'@'%'"
UNION
-- Level 1 inheritance
SELECT DISTINCT gr.GRANTEE, gr.OBJECT_DATABASE, gr.OBJECT_NAME, gr.PRIVILEGE_TYPE
FROM grants_to_roles gr
JOIN role_edges re1 ON gr.GRANTEE = re1.FROM_ROLE
JOIN role_edges re2 ON re1.TO_ROLE = re2.FROM_ROLE
WHERE re2.TO_USER = "'user_g'@'%'"
UNION
-- Level 2 inheritance
SELECT DISTINCT gr.GRANTEE, gr.OBJECT_DATABASE, gr.OBJECT_NAME, gr.PRIVILEGE_TYPE
FROM grants_to_roles gr
JOIN role_edges re1 ON gr.GRANTEE = re1.FROM_ROLE
JOIN role_edges re2 ON re1.TO_ROLE = re2.FROM_ROLE
JOIN role_edges re3 ON re2.TO_ROLE = re3.FROM_ROLE
WHERE re3.TO_USER = "'user_g'@'%'";
```

### 18.6 Role Inheritance Chain

```sql
USE sys;
SELECT re1.FROM_ROLE AS ParentRole, re1.TO_ROLE AS ChildRole
FROM role_edges re1
WHERE re1.FROM_ROLE = 'role_s' AND re1.TO_ROLE IS NOT NULL
UNION ALL
SELECT re2.FROM_ROLE AS ParentRole, re2.TO_ROLE AS ChildRole
FROM role_edges re1
JOIN role_edges re2 ON re1.TO_ROLE = re2.FROM_ROLE
WHERE re1.FROM_ROLE = 'role_s' AND re2.TO_ROLE IS NOT NULL;
```

### 18.7 Check Role Activation

```sql
-- Check if role is active in current session (v3.1.4+)
SELECT is_role_in_session("r1");
```

### 18.8 Simplified Permission Queries

```sql
-- Recommended: Use SHOW GRANTS instead of complex joins
SHOW GRANTS;                              -- Current user
SHOW GRANTS FOR ROLE <role_name>;         -- Specific role
SHOW GRANTS FOR <user_identity>;          -- Specific user
```

---

## 19. FE_Memory_Usage - FE Memory Breakdown

```sql
USE sys;
SELECT * FROM fe_memory_usage;
```

> **Note**: Absolute values may not be 100% accurate, but useful for relative comparison.

---

## Quick Reference by Scenario

| Scenario | Key Tables |
|---|---|
| Import failure | `loads`, `load_tracking_logs`, `stream_loads` |
| Data quality | `loads` (FILTERED_ROWS) |
| Performance bottleneck | `loads`, `be_metrics`, `fe_metrics`, `be_threads` |
| Tablet health | `be_tablets`, `partitions_meta`, `be_compactions` |
| Compaction issues | `be_compactions`, `be_cloud_native_compactions` |
| MV refresh | `materialized_views`, `task_runs` |
| Data Cache | `be_datacache_metrics` |
| Permissions/RBAC | `sys.grants_to_roles`, `sys.grants_to_users`, `sys.role_edges` |
| Statistics | `_statistics_.table_statistic_v1` |

---

## Usage

This document provides ready-to-use SQL queries for common diagnostic scenarios. Combine with:

- `tools/01-diagnostic-commands.md` for shell commands and advanced MV queries.
- `skills/01-query.md` for query-specific troubleshooting.
- `skills/02-import.md` for import pipeline issues.
- `skills/03-node.md` for BE/FE node problems.