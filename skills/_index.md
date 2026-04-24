---
type: index
category: skills
description: Troubleshooting skill guides organized by problem category
---

# Skills Index

This directory contains troubleshooting skill guides. Each skill file should follow the naming convention: `<number>-<category>.md`.

## Categories

| # | Category | Description | Keywords |
|---|---|---|---|
| 01 | query | Query hang, slow query, profile analysis | query hang, slow query, profile, scan, join, data skew |
| 02 | import | Import slow, timeout, RPC failed, publish timeout | import, broker load, stream load, RPC failed, publish timeout |
| 03 | node | BE Crash, BE OOM, FE deadlock, FE Full GC | BE crash, OOM, FE deadlock, FE GC, memory |
| 04 | materialized-view | MV refresh failures, rewrite failures | MV refresh, MV timeout, MV inactive, query rewrite |
| 05 | data-lake | HMS, Kerberos, HDFS/S3, external table | HMS, Hive, Kerberos, HDFS, S3, external table |
| 06 | shared-data | DataCache, S3 issues in shared-data architecture | DataCache, S3, FE leader switch, shared-data |
| 07 | tablet | Tablet health, balance, data skew | tablet health, tablet balance, data skew, bucket |
| 08 | deployment | FE/BE startup, port conflicts, BDB | FE startup, BE startup, port conflict, BDB, JDK |
| 09 | high-concurrency | High QPS optimization | high QPS, connection pool, PreparedStatement, query cache |
| 10 | resource-isolation | Resource groups, query queues | resource group, query queue, SQL blacklist, circuit breaker |

## File Template

Create file: `<number>-<category>.md`

```markdown
---
type: skill
category: <category>
priority: <number>
keywords: [keyword1, keyword2, ...]
---

# <number> - <Category> Troubleshooting

Brief description.

---

## 1. <Subcategory>

### Diagnostic Steps

<Step-by-step instructions>

### Key Commands

```sql/bash
<commands>
```

### Common Issues

| Issue | Cause | Fix |
|---|---|---|
| ... | ... | ... |

---

## Related Cases

- [case-XXX](../cases/<category>/case-XXX-<name>.md)
```

## Adding New Skill

1. Choose appropriate category number
2. Create file with YAML frontmatter
3. Follow template structure
4. Link related cases at bottom
5. Update this index