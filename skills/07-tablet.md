---
type: skill
category: tablet
priority: 7
keywords: [tablet health, tablet balance, data skew, bucket, compaction, version count]
---

# 07 - Tablet Governance

Investigation guide for tablet health, balance, sanity, bucket optimization, and
compaction-score / too-many-versions issues.

---

## 1. Core Objectives

- **Health**: All tablet replicas should be in OK state. Watch for `VERSION_ERROR`, `SCHEMA_ERROR`.
- **Balance**: Tablets should be evenly distributed across BEs. Skew leads to performance bottlenecks.
- **Sanity**: Keep tablet count reasonable. Too many tablets increases FE metadata overhead.

---

## 2. Diagnostic SQL

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

-- Check data distribution across nodes
ADMIN SHOW REPLICA DISTRIBUTION FROM <table>;
```

Replica health: `SHOW TABLET` and compare `VERSION`, `LstFailedVersion`, `LstSuccessVersion`
across replicas. `VersionCount` greater than 500 continuously indicates compaction cannot keep up.

---

## 3. Automated Health Inspection

A community Python script (`healthy_report.py`) automates tablet health, colocate-group,
and distribution-balance checks. It connects via MySQL protocol and emits an HTML report.
See `tools/01-diagnostic-commands.md` for invocation details.

---

## 4. Bucket Strategy Analysis

A standalone CLI utility (`StarRocksBuckets`) can analyze bucket strategies and emit
`ALTER TABLE` statements for optimal bucket count or new bucket key candidates.
Use when fixing data skew or right-sizing bucket counts on existing tables.

---

## 5. Best Practices

- **Tablet size**: target ~1GB per tablet (raw data). Adjust bucket count accordingly.
- **Small partitions** (<100MB): consider coarser partition granularity (month instead of day).
- **Data skew**: if standard deviation > 10, review bucket key selection. Bucket key must have high cardinality.
- **High-concurrency small tables** (<100MB, QPS >10): use 3 buckets minimum.
- **Total tablet count**: clean up unused test/backup tables. Use default 3 replicas in production.
- **Compaction for too many versions** (`close index failed` or `too many tablet versions`):
  - Increase per-batch data volume; reduce import frequency.
  - Tune compaction: `cumulative_compaction_num_threads_per_disk=4`, `base_compaction_num_threads_per_disk=2`, `cumulative_compaction_check_interval_seconds=2`.

---

## 6. Migration / Disk-Balancing Failures

When disk balancing tasks retry endlessly and saturate IO, the root cause is usually
metadata-cleanup state inconsistency on the target disk. Restarting all BE nodes resets
`_shutdown_tablets` state and lets balancing complete cleanly. Long-term fix lives in
the BE migration code.

---

## Common Issues

| Issue | Cause | Fix |
|---|---|---|
| `too many tablet versions` | Compaction can't keep up with ingest | Tune compaction; reduce import frequency |
| Single tablet 100x larger than others | Bad bucket key (low cardinality / hot value) | Re-bucket with high-cardinality key |
| Disk balance retries forever | `_shutdown_tablets` state inconsistent | Restart all BEs |
| `VERSION_ERROR` on a replica | Replica desync after long network blip | Mark replica bad to trigger clone |
| Tablet count too high | Too-fine partition or excess buckets | Coarser partition; reduce bucket count |

---

## Related Cases

- `case-004-disk-balancing` — IO saturation from migration retry loop
- `case-014-scan-skew` — data skew driven by bucket key with hot value

---

## Resources

- [Tablet management documentation](https://docs.starrocks.io/docs/administration/management/tablet_management/)
