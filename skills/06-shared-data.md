---
type: skill
category: shared-data
priority: 6
keywords: [DataCache, S3, FE leader switch, shared-data, StarCache, multipart upload, vacuum, compaction score]
---

# 06 - Shared-Data Troubleshooting

Investigation guide for shared-data architecture issues: DataCache (StarCache) corruption
and autoscaling regressions, S3 rate limiting and multipart upload failures, FE leader
switch bugs, and compaction score management.

---

## 1. DataCache Issues

### DataCache autoscaling causing compaction regression

- **Symptom**: Compaction score suddenly rises, S3 GET IOPS spike, query latency increases.
- Check `be.WARNING` for star cache autoscaling logs.
- **Correlation**: each time disk utilization reaches the autoscaling threshold, cache eviction occurs;
  cache miss triggers compaction reads from S3, compaction slows, compaction score rises.
- **Fix**: disable DataCache autoscaling if no disk resource competition exists (e.g., pure shared-data
  with separate ingestion/query warehouses).

### DataCache corruption causing publish failures

- **Symptom**: Publish version fails with `corrupted compressed block contents`.
- **Root cause**: StarCache data corruption (caused by software bugs or disk failures).
- **Fix**:
  ```bash
  # Stop BE, remove DataCache directory, restart BE
  # Data will be re-read from S3/HDFS on next access
  ```
- **Long-term**: implement self-cleaning mechanism for corrupted cache entries.

---

## 2. S3 Rate Limiting and Performance

### `503: Please reduce your request rate`

Use partitioned prefix to distribute requests across S3 partitions:

```sql
CREATE STORAGE VOLUME sv WITH (num_partitioned_prefix = 100);
```

- Reduce upload size: increase `mutable_bucket_num` (default 7) to reduce per-upload size.
- S3 IO latency increases with larger IO sizes — this is expected behavior.

### S3 multipart upload failures

- Can cause `.dat` and `.sst` file loss.
- Monitor with dat/sst loss metrics.
- Increase `lake_metadata_cache_limit` (e.g., 8G) for larger clusters.
- Set conservative vacuum: `lake_autovacuum_grace_period_minutes = 4320` (3 days).

---

## 3. FE Leader Switch Issues

### Meta file not found after leader switch

- **Root cause**: during FE graceful exit, EditLog write may fail but FE continues sending publish tasks.
  After the leader switch, the new leader cannot replay the missing transaction, leading to
  `txn_version` collision and GTID validation failure (`meta file not found`).
- **Mitigation**: disable FE graceful exit if leader switches cause issues.
- **Diagnosis**: check if FE leader switched seconds before the error; search FE logs for
  leader transition events.

---

## 4. Compaction Score Management

### Compaction falling behind ingestion

- Put compaction and ingestion in the same warehouse (avoid S3 cross-reads).
- Monitor `information_schema.be_cloud_native_compactions` for compaction timing.
- Check if compaction is reading from remote storage (S3 cache miss).
- Disable global profile collection (`enable_profile = false`); use `big_query_profile_threshold` instead.
- Increase Flink/data source CPU if the ingestion client is the bottleneck.

---

## 5. Cached Tablet Metadata Inconsistencies

A class of bugs in 4.0.x related to the "latest tablet meta cache":

- Symptom: `publish version fail because tablet meta file is missing — The specified key does not exist`
- The actual meta file on S3 has a lower version than the cached one.
- BE log shows `base version adjusted from N to M, because the latest tablet meta cache has meta which version is M`.
- Workaround: restart BE to reset cache state.
- See `case-009-stream-load-stuck` for a full investigation.

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| Compaction score climbing during steady-state ingestion | DataCache autoscaling evicting hot data | Disable autoscaling on ingestion warehouse |
| `corrupted compressed block` on publish | StarCache corruption | Clear DataCache; restart BE |
| `meta file not found` immediately after leader switch | EditLog persistence bug on graceful exit | Disable FE graceful exit |
| `.dat` / `.sst` file missing | S3 multipart upload failed silently | Conservative vacuum; monitor loss metrics |
| S3 503 on heavy ingest | S3 partition request rate exceeded | `num_partitioned_prefix=100`; reduce per-upload size |

---

## Related Cases

- `case-009-stream-load-stuck` — cached tablet meta bug in 4.0.2
- `case-010-datacache-corruption` — silent StarCache corruption causing publish failures
- `case-011-multi-root-cause` — leader-switch GTID collision plus S3 multipart failures
- `case-013-datacache-autoscaling` — autoscaling-induced compaction regression

---

## Resources

- [Shared-data architecture overview](https://docs.starrocks.io/docs/deployment/shared_data/)
