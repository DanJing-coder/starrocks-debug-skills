---
type: index
category: cases
description: Real-world troubleshooting case studies organized by category
---

# Cases Index

This directory contains real-world troubleshooting cases with complete investigation walkthroughs.

## Case Categories

| Category | Description | Directory |
|---|---|---|
| query | Query hang, slow query, profile analysis | [query/](query/) |
| import | Import slow, timeout, RPC failed, publish timeout | [import/](import/) |
| node | BE Crash, BE OOM, FE deadlock, FE Full GC | [node/](node/) |
| materialized-view | MV refresh failures, rewrite failures | [materialized-view/](materialized-view/) |
| data-lake | HMS, Kerberos, external table errors | [data-lake/](data-lake/) |
| shared-data | DataCache, S3 issues in shared-data | [shared-data/](shared-data/) |
| tablet | Tablet health, balance, data skew | [tablet/](tablet/) |
| deployment | FE/BE startup failures, port conflicts | [deployment/](deployment/) |
| concurrency | High QPS, memory volatility | [concurrency/](concurrency/) |

## Quick Reference

| Case ID | Category | Issue Type | Summary |
|---|---|---|---|
| case-001 | import | Broker Load backlog | Task queue saturation |
| case-002 | import | RPC Failed | Statistics collection starving RPC |
| case-003 | node | FE Deadlock | LockManager deadlock |
| case-004 | tablet | Disk balancing | Migration retry loop |
| case-005 | deployment | SSL Certificate | Private OSS SSL issue |
| case-006 | data-lake | Network saturation | HMS blocking |
| case-007 | node | Memory tracking leak | System memory exhausted |
| case-008 | node | BE OOM | OOM causing publish stall |
| case-009 | shared-data | Stream Load stuck | Tablet meta cache bug |
| case-010 | shared-data | DataCache corruption | Silent data corruption |
| case-011 | shared-data | Multi-root-cause | Leader switch + S3 failures |
| case-012 | materialized-view | Refresh failures | FE abort + S3 rate limit |
| case-013 | shared-data | DataCache autoscaling | Cache eviction regression |
| case-014 | query | Scan skew | Bucket key optimization |
| case-015 | concurrency | Memory volatility | Session timeout override |
| case-016 | data-lake | Kerberos auth | Kerberos authentication failures |
| case-017 | import | Reached timeout | Replica sync thread pool saturation |
| case-018 | import | ORC compression overflow | Large ORC file import fails, use zstd or reduce file size |
| case-019 | tablet | Inverted index pending | ALTER TABLE ADD INDEX stuck in PENDING, workaround with history_job_keep_max_second |
| case-020 | deployment | FE startup blocked | Hive catalog connection blocks FE startup, upgrade to 3.5.0 with lazy connector |

## Case Template

Create file: `cases/<category>/case-<number>-<short-name>.md`

```markdown
---
type: case
category: <category>
issue: <issue-type>
keywords: [keyword1, keyword2, ...]
---

# Case-XXX: <Short Title>

## Environment

- StarRocks version: X.X.X
- Architecture: shared-data / shared-nothing

## Symptom

<What user reported>

**Error:**
```
<Exact error>
```

## Investigation

### Step 1: <Action>

<Command and analysis>

### Step 2: ...

## Root Cause

<Underlying issue>

## Resolution

### Short-term

<Immediate fix>

### Long-term

<Permanent solution>

## Lessons Learned

<What we learned>

---

## Related Skills

- [XX-<skill>.md](../../skills/XX-<skill>.md)
```

## Adding New Case

1. Choose category and sequential number
2. Create file with YAML frontmatter
3. Follow template structure
4. Update this quick reference table