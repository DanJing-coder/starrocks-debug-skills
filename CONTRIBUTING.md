---
type: contributing
description: How to add and maintain content in this project
---

# Contributing Guide

How to add cases, skills, and tools.

---

## Project Structure

```
starrocks_debug_skills/
├── README.md           # Overview
├── LICENSE             # Apache 2.0
├── SKILL.md            # Main entry point
├── CONTRIBUTING.md     # This file
├── skills/
│   └── _index.md       # Index + templates
├── cases/
│   ├── _index.md       # Index + templates
│   └── <category>/     # Subdirectories
└── tools/
    └── _index.md       # Index + templates
```

---

## Adding Content

### Add Skill

1. Check [skills/_index.md](skills/_index.md) for category number
2. Create: `skills/<number>-<category>.md`
3. Use template from _index.md
4. Include YAML frontmatter

### Add Case

1. Check [cases/_index.md](cases/_index.md) for existing numbers
2. Create: `cases/<category>/case-<number>-<name>.md`
3. Use template from _index.md
4. Update quick reference table

### Add Tool

1. Check [tools/_index.md](tools/_index.md) for tool number
2. Create: `tools/<number>-<name>.md`
3. Organize for quick copy-paste

---

## YAML Frontmatter

Every file should have frontmatter:

```yaml
---
type: skill | case | tool
category: <category>
keywords: [keyword1, keyword2, ...]
---
```

---

## Naming Convention

- **Skills**: `<number>-<category>.md` (e.g., `01-query-troubleshoot.md`)
- **Cases**: `case-<number>-<short-name>.md` (e.g., `case-001-broker-load-backlog.md`)
- **Tools**: `<number>-<name>.md` (e.g., `01-diagnostic-commands.md`)

---

## Quality Guidelines

1. No customer names
2. English only
3. Link related content
4. Test commands before adding

---

## Directory Indexes

Each directory has `_index.md` containing:
- Category/table listing
- File template
- Instructions for adding new content