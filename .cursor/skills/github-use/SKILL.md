---
name: github-use
description: Git and GitHub workflow — branches, commits, PRs, checks, and documenting validation with real LinkedIn data when relevant.
---

# GitHub

## Overview

Use this skill for **git operations**, **pull requests**, and **what to record in PR descriptions** so reviewers can reproduce and trust the change.

## Branches and commits

- **Feature branches** off `main` (or the agreed base); **no direct commits to `main`** for feature work.
- **Branch names:** include a **Linear ticket id** when the work maps to a ticket (e.g. `cursor/luc-68-short-topic-0276`).
- **Commits:** small, focused; **conventional commits with gitmoji** (see [gitmoji](https://gitmoji.dev/) and project `CLAUDE.md`).
- **Before pushing:** run **`uv run black --check .`**, **`uv run flake8 …`**, **`uv run mypy linkedin_api`**, and **`uv run pytest`** (adjust scope if the project standard says otherwise). Fix failures or call them out explicitly.
- **Never force-push** to shared branches unless the team explicitly asked for it.

## Pull requests

- **Title:** use **`[TICKET-XX] Short title`** when tied to Linear (e.g. `[LUC-68] Rich Markdown post bodies`).
- **Body:** summarize **what changed** and **why**; link the Linear issue if applicable.
- **Update the PR** when you push new commits (description or comments if behavior or validation changed).

## PR validation block (when the change touches fetch, enrich, content store, or pipeline behavior)

If a human or agent **can** run against real LinkedIn data (`LINKEDIN_ACCESS_TOKEN` valid in that environment), add a **Validation** section that is **systematic** enough to rerun and **safe** to paste publicly.

### Pin the run

- **Branch and commit:** branch name + `git rev-parse --short HEAD`; if comparing to `main`, note **`main` at** the baseline short SHA you used.
- **Isolated data dir:** set **`LINKEDIN_DATA_DIR`** to a **dedicated path** per run (e.g. `/tmp/prNN_main` vs `/tmp/prNN_branch`) so outputs do not overwrite local dev data and diffs are comparable.
- **Scope:** state the **time window** (e.g. `summarize_activity --last 1d`) and **slice** (e.g. last **N** rows of `activities.csv`, **`enrich_activities --limit N`**).

### Commands (copy-pasteable)

Include the **exact** sequence used, for example:

1. `uv sync --all-groups` (if needed)
2. `uv run python -m linkedin_api.summarize_activity --last 1d` (or the project’s fetch step)
3. Build a small CSV (e.g. `tail -n N "$LINKEDIN_DATA_DIR/activities.csv" > /tmp/…`)
4. `ENRICH_TELEMETRY=1 uv run python -m linkedin_api.enrich_activities … --limit N` (when testing enrichment)

If the token is **missing or expired**, say so in the PR (**do not** paste secrets). Partial validation (unit tests only) is OK if labeled as such.

### What to paste back

- **Exit codes / outcome:** fetch and enrich succeeded or failed (e.g. 401 / expired token).
- **Telemetry:** one line or summary of **`ENRICH_TELEMETRY`** counters when enrichment ran.
- **Diff or summary:** e.g. `diff -ruN` between two isolated `content/` trees, or bullets: which files changed, whether `.md` vs `.meta.json` differed, any known skips (login wall, empty window).

### Redaction

- **Never** paste `LINKEDIN_ACCESS_TOKEN` or other secrets.
- Truncate or generalize **sensitive URLs** in prose if needed; hashed content-store stems are fine.

### Optional

- Attach a **sanitized** log file (gist or PR comment) if stdout is long; keep the PR body to a **short** summary plus link.

## GitHub CLI

- **`gh pr list`**, **`gh pr view`**, **`gh api repos/…/pulls/…/comments`** — use to inspect or address review comments when the task requires it.
