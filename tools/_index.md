---
type: index
category: tools
description: Diagnostic utilities and quick reference guides
---

# Tools Index

This directory contains diagnostic utilities and quick reference guides.

## Tools List

| # | Tool | Description | Purpose |
|---|---|---|---|
| 01 | diagnostic-commands | SQL and shell commands quick reference | Quick lookup for diagnosis |
| 02 | information-schema | Information schema diagnostic queries | System table-based analysis |
| 03 | mv-diagnostic-sql | Materialized view diagnostic SQL queries | MV refresh, rewrite, performance analysis |
| 04 | known-bugs | Known issues and fixes reference | Version-specific bug awareness |
| 05 | log-patterns | Log search patterns | Error hunting in logs |
| 06 | parameters | Key FE/BE parameters reference | Configuration tuning |

## Tool Template

Create file: `<number>-<name>.md`

```markdown
---
type: tool
category: <name>
keywords: [keyword1, keyword2, ...]
---

# <number> - <Name>

Brief description.

---

## Section 1

<Content organized for quick lookup>

### Subsection

| Item | Description |
|---|---|
| ... | ... |

## Usage

<How to use this tool>
```

## Adding New Tool

1. Choose appropriate number
2. Create file with YAML frontmatter
3. Organize for quick copy-paste
4. Update this index