---
type: case
category: tablet
issue: inverted-index
keywords: [inverted-index, builtin-index, pending, create-index, alter-table]
status: pending  # Missing investigation and resolution
---

# Case-019: Builtin Inverted Index Creation Pending After ALTER TABLE

## Environment

- StarRocks version: 4.1.0
- Architecture: shared-nothing (3 nodes, FE/BE co-deployed)
- Index type: builtin inverted index

## Symptom

Customer reports inconsistent behavior when adding builtin inverted index:

**Works:**
- Adding inverted index during `CREATE TABLE` statement
- Adding inverted index after `CREATE TABLE` in test environment (4.1.0-rc, single node)

**Fails:**
- Adding inverted index via `ALTER TABLE ADD INDEX` in production (4.1.0, 3 nodes)
- Index creation remains in `PENDING` state indefinitely

**Error:**

```
[PENDING: Need specific error messages and index creation status]
```

## Investigation

### Step 1: Compare Environments

| Attribute | Production | Test |
|---|---|---|
| Version | 4.1.0 | 4.1.0-rc |
| Nodes | 3 nodes | 1 node |
| FE/BE | Co-deployed | Single node |
| Result | PENDING | Works |

### Step 2: Check Index Creation Status

[PENDING: Need commands to check index status]

### Step 3: Check Tablet/Replica Status

[PENDING: Need tablet health check]

## Root Cause

[PENDING: Need investigation results]

**Hypotheses:**
- Multi-node environment may have different index creation workflow
- Tablet replica synchronization issue
- FE/BE co-deployment resource contention

## Resolution

[PENDING: Need solution]

## Key Commands

```sql
-- Check index status
SHOW INDEX FROM <table_name>;

-- Check tablet status
SHOW TABLET FROM <table_name>;

-- Check tablet health
ADMIN SHOW REPLICA STATUS FROM <table_name>;
```

```bash
# Check BE logs for index creation errors
grep -i "index" be.INFO | grep -i "pending\|error\|fail"
```

## Lessons Learned

[PENDING: Will be filled after resolution]

---

## Notes

**Status**: This case is created from a conversation without full resolution details.
Update this case when investigation completes and root cause/resolution are found.

**Environment Difference**: Key observation is that behavior differs between:
- CREATE TABLE with index: works
- ALTER TABLE ADD INDEX: pending (only in multi-node production)

**Related Issues**: None identified yet.