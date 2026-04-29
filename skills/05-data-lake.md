---
type: skill
category: data-lake
priority: 5
keywords: [HMS, Hive, Kerberos, HDFS, S3, external table, data lake, catalog, cache, metadata cache, data cache, freshness, Iceberg]
---

# 05 - Data Lake / External Table Troubleshooting

Investigation guide for Hive Metastore connectivity, Kerberos authentication, HDFS/S3
access errors, and external catalog query failures.

---

## 1. Hive Metastore Connection Issues

| Error keyword | Investigation direction |
|---|---|
| `set_ugi() not successful` | Check Kerberos config; verify `HADOOP_USER_NAME` in `hadoop_env.sh` |
| `GSS initiate failed` | Verify keytab is not expired (`klist`); check JCE extensions |
| `Failed to get current notification event id` | Check HMS user permissions; configure `HADOOP_USER_NAME` |
| `Filesystem closed` | Increase `hdfs_client_max_cache_size` (must exceed total namenode count) |

---

## 2. Kerberos Debugging

Enable Kerberos debug logging in FE/BE config:

```
# In fe.conf JAVA_OPTS:
-Dsun.security.krb5.debug=true

# In be/conf/hadoop_env.sh:
HADOOP_OPTS="$HADOOP_OPTS -Dsun.security.krb5.debug=true"
```

Debug output goes to `fe.out` / `be.out`.

### Quick Diagnostic Commands

```bash
# List principals in keytab
klist -kt /path/to/keytab

# Test kinit with keytab
kinit -kt /path/to/keytab principal_name@REALM

# View current ticket cache
klist
```

### Common Kerberos Errors

| Error | Cause | Fix |
|---|---|---|
| `GSS initiate failed` | Expired keytab or missing JCE | Renew keytab; install JCE for AES-256 |
| `Server not found in Kerberos database` | SPN mismatch | Verify service principal matches server |
| `Clock skew too great` | Time sync issue | Ensure NTP is running |
| `Preauthentication failed` | Wrong keytab/password | Regenerate keytab |
| `Checksum failed` | Encryption type mismatch | Check krb5.conf encryption settings |

---

## 3. S3 / Object Storage Issues

- EC2 instances can use IAM Roles without AK/SK, but must not set `AWS_EC2_METADATA_DISABLED`.
- Non-EC2 environments require AK/SK/Endpoint configuration.
- Connection pool exhaustion: increase `fs.s3a.connection.maximum` (for Paimon Catalog use `paimon.option.fs.s3a.connection.maximum`).

### SSL Issues with Private OSS

Some private object-storage deployments do not support SSL. StarRocks defaults to SSL-encrypted
access; if `ssl_enable` is required to be off, ensure you are on a version where the parameter
takes effect (older releases had a bug ignoring the flag).

---

## 4. Network-Layer Bottlenecks

When external-table queries saturate a CN/BE node's network bandwidth, the HMS service may be
the upstream cause. Symptoms:

- Continuous network saturation on a single node.
- jstack shows threads blocked on `org.apache.hadoop.hive.metastore.security.TFilterTransport.readAll`.
- Heavy JOINs between internal tables and external (Hive/Iceberg) tables generate large shuffles.

Mitigation:

- Add timeout controls for HMS access.
- Investigate HMS service health independently.
- Reduce external-table JOIN cardinality with predicate pushdown and partition pruning.

---

## 5. Catalog Cache Freshness

Understanding cache mechanisms is critical for diagnosing data freshness issues with external catalogs.

### 5.1 Data Cache (Block-Level Caching)

Data cache provides transparent block-level caching for external table data.

**Key Design:**
- Cache keys combine `hash(filename)`, `filesize/modify_time`, and `blockId` to uniquely identify data blocks.
- Default block size: 1 MB.
- Validity relies on file modification time. If the source file changes, the cache key becomes invalid.

**Storage & Eviction:**
- Backend storage: local disk (NVMe/SSD recommended).
- LRU-based eviction: automatically purges least-recently-used blocks when space thresholds are reached.

**Applicability:**
- Only triggers for external tables (S3/HDFS backed).
- Cache hits significantly improve query performance.
- **No data freshness issues** — cache invalidates automatically when source files change.

### 5.2 Metadata Cache

Metadata cache stores data location, partition information, file info, and other query execution metadata.

#### Hive Table Caching

Catalog properties for controlling Hive metadata cache:

| Property | Description |
|---|---|
| `metastore_cache_ttl_sec` | TTL for metastore metadata (database/table/partition) |
| `metastore_cache_refresh_interval_sec` | Refresh interval for metastore cache |
| `remote_file_cache_ttl_sec` | TTL for remote file metadata |
| `remote_file_cache_refresh_interval_sec` | Refresh interval for file cache |

**Staleness Handling:**
- Pending requests receive stale data if a refresh is in progress.
- Configure TTL and refresh intervals based on data update frequency.

#### Iceberg Table Caching

Iceberg uses snapshot-based caching with different TTLs:

| Metadata Type | Default TTL | Configuration Property |
|---|---|---|
| Table metadata | 30 minutes | `iceberg_table_cache_ttl_sec` |
| Database/Partition | 48 hours | `iceberg_meta_cache_ttl_sec` |
| DataFiles/DeleteFiles | 48 hours | Indirectly controlled via snapshot_id |

**Key Design:**
- Cache keys include `snapshot_id` for partition and file metadata.
- Cache auto-invalidates when a new snapshot is detected.
- No explicit refresh trigger needed — snapshot change triggers invalidation.
- Memory/disk cache for metadata files is transparent, no impact on freshness.

**Data Freshness Guarantee:**
- Iceberg guarantees data freshness via snapshot_id.
- New snapshots automatically invalidate relevant cache entries.
- No stale data risk for Iceberg tables.

### 5.3 Background Refresh Mechanism

FE runs a daemon thread to proactively refresh metadata for frequently accessed tables.

**Configuration (fe.conf):**

| Property | Default | Description |
|---|---|---|
| `background_refresh_metadata_interval_millis` | 600000 (10 min) | Interval between refresh runs |
| `background_refresh_metadata_time_secs_since_last_access_secs` | 86400 (24 hours) | Refresh tables accessed within this window |

**Process:**
1. FE daemon thread runs every 10 minutes.
2. Identifies tables accessed in the last 24 hours.
3. Triggers metadata refresh for those tables.

**Data Freshness Guarantees:**

| Catalog Type | Freshness Behavior |
|---|---|
| Hive | Background refresh ensures metadata stays current; stale data served during refresh if cache TTL expired |
| Iceberg | Snapshot-based invalidation ensures freshness; background refresh keeps snapshot info current |

### 5.4 Troubleshooting Cache Freshness Issues

**Symptoms:**
- Query returns outdated data from Hive catalog.
- New partitions not visible immediately.
- Iceberg query sees old snapshot data.

**Investigation:**

```sql
-- Check catalog properties
SHOW CREATE CATALOG <catalog_name>;

-- Manually refresh catalog metadata
REFRESH CATALOG <catalog_name>;
REFRESH DATABASE <catalog_name>.<db_name>;
REFRESH TABLE <catalog_name>.<db_name>.<table_name>;
```

**Common Fixes:**

| Issue | Fix |
|---|---|
| Hive data stale | Reduce `metastore_cache_ttl_sec` and `remote_file_cache_ttl_sec` |
| Hive refresh too slow | Reduce `metastore_cache_refresh_interval_sec` |
| New partitions not visible | Call `REFRESH DATABASE` or `REFRESH TABLE` manually |
| Iceberg snapshot lag | Check `iceberg_table_cache_ttl_sec`; call `REFRESH TABLE` |

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| `GSS initiate failed` | Expired keytab or missing JCE | Renew keytab; install JCE extensions |
| `Filesystem closed` | NN cache too small | Increase `hdfs_client_max_cache_size` |
| `503 reduce request rate` from S3 | S3 rate limit | Use `num_partitioned_prefix`; see `skills/06-shared-data.md` |
| External JOIN saturates network | HMS slow + large shuffle | Fix HMS; reduce shuffle |
| SSL handshake error to private OSS | Default SSL on; param bug | Upgrade to fixed version; disable SSL param |
| Hive data stale | Metadata cache TTL too long | Reduce TTL; `REFRESH TABLE` manually |
| New Hive partitions not visible | Background refresh delay | Call `REFRESH DATABASE`; tune refresh interval |

---

## Related Cases

- `case-005-ssl-certificate` — private OSS SSL issue blocking Broker Load
- `case-006-network-saturation` — HMS degradation saturating CN network
- `case-016-kerberos-authentication` — Kerberos authentication failures with Hive/HDFS

---

## Resources

- [Hive catalog documentation](https://docs.starrocks.io/docs/data_source/catalog/hive_catalog/)
