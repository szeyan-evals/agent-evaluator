---
phase: 05-test-coverage-and-ci
plan: "04"
subsystem: ci
tags: [ci, github-actions, ruff, pytest, readme]
dependency_graph:
  requires: [05-01]
  provides: [TEST-04, CI gate on push/PR]
  affects: [.github/workflows/ci.yml, README.md]
tech_stack:
  added: [GitHub Actions (ci.yml)]
  patterns: [pull_request trigger (not pull_request_target), pinned action versions, hermetic pytest via marker exclusion]
key_files:
  created:
    - .github/workflows/ci.yml
  modified:
    - README.md
decisions:
  - "Used pull_request (not pull_request_target) — fork PRs run with read-only token, no secret access (T-05-07)"
  - "Pinned actions/checkout@v4 and actions/setup-python@v5 — no floating @master refs (T-05-09)"
  - "pytest -m 'not live' keeps CI hermetic — no API keys configured or needed (T-05-08)"
  - "Badge uses <OWNER> placeholder — slug unknown until user creates GitHub remote"
metrics:
  duration: "~5 minutes"
  completed_date: "2026-06-13"
  tasks_completed: 2
  tasks_total: 3
  files_created: 1
  files_modified: 1
---

# Phase 5 Plan 04: CI Workflow + README Badge Summary

GitHub Actions CI workflow created (ruff + hermetic pytest on push/PR, pinned actions, no secrets) and CI status badge added to README. Actual CI greenness is a pending human-verify step — requires pushing to GitHub first.

## Tasks Completed

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 | Write `.github/workflows/ci.yml` (TEST-04, D4) | cd3c3bc | Done |
| 2 | Add CI status badge to README | a7459f7 | Done |
| 3 | CI is green (post-push verification) | — | **PENDING — human-verify** |

## What Was Built

### `.github/workflows/ci.yml`

Hermetic CI workflow locked to D4 spec:

- **Triggers:** `push` to `main` + `pull_request` (bare). Explicitly NOT `pull_request_target` — fork PRs run with a read-only token and no access to repo secrets (T-05-07 mitigation).
- **Actions pinned:** `actions/checkout@v4`, `actions/setup-python@v5` — no floating refs (T-05-09 mitigation).
- **Python:** 3.11 with pip cache.
- **Install:** `pip install -e ".[dev]"` — installs pytest, pytest-asyncio, ruff from the already-declared dev extra. No new packages introduced.
- **Lint step:** `ruff check src/ scenarios/ tests/`
- **Test step:** `pytest -m 'not live'` — live-API tests deselected; no API keys configured or needed (T-05-08 mitigation).
- **No:** coverage reporting, version matrix, branch protection, secrets/env API keys.
- **YAML validation:** `yaml.safe_load` succeeded locally; structure asserted correct (on-block, trigger names, ruff step, pytest step, action uses).

### README.md badge

Single badge line inserted immediately after the H1 title (line 2), before the description paragraph:

```markdown
<!-- CI badge — replace OWNER with your GitHub org/user after pushing to GitHub -->
[![CI](https://github.com/<OWNER>/agent-evaluator/actions/workflows/ci.yml/badge.svg)](https://github.com/<OWNER>/agent-evaluator/actions/workflows/ci.yml)
```

`<OWNER>` is an explicit placeholder. The HTML comment above the badge tells the user what to do. No other README content was changed.

## Pending Human-Verify Checkpoint (Task 3)

**What:** Confirm CI runs green after pushing to GitHub.

**Steps:**
1. Create a GitHub repository (e.g. `https://github.com/<your-org>/agent-evaluator`).
2. Replace `<OWNER>` in `README.md` line 4 with your actual GitHub org/user.
3. Push to `main`:
   ```bash
   git remote add origin https://github.com/<OWNER>/agent-evaluator.git
   git push -u origin main
   ```
4. Open the **Actions** tab on GitHub. Confirm the CI run goes green:
   - Lint step: `ruff check src/ scenarios/ tests/` passes
   - Test step: `pytest -m 'not live'` shows 100 passed, 3 deselected, 1 xfailed
5. Once CI is green, re-run the System Judge: `judge ship` — this is the v1 closure gate.

**Note:** The `models.py` file has an uncommitted change (`turn_index: int | None = None` added to `TrajectoryStep`). This was present before Plan 04 started and is unrelated to CI/README work. Verify its disposition before pushing — either commit it intentionally or revert it.

## Deviations from Plan

None — plan executed exactly as written. The ci.yml content is verbatim D4. The README badge uses the recommended placeholder approach from the plan's task 2 action spec.

## Threat Coverage

All three mitigations in the STRIDE register were applied:

| Threat ID | Mitigation | Applied |
|-----------|-----------|---------|
| T-05-07 | `pull_request` not `pull_request_target` | Yes — verified in YAML assertion |
| T-05-08 | No API keys; `pytest -m 'not live'` | Yes — test step uses marker exclusion |
| T-05-09 | Pinned `@v4`/`@v5` action versions | Yes — no `@master` or floating refs |
| T-05-SC | Only installs declared `[dev]` extra | Yes — no new packages |

## Verification Results

```
# YAML structure assertion
CI_YAML_OK

# pytest -m 'not live'
100 passed, 3 deselected, 1 xfailed

# ruff check src/ tests/
All checks passed!
```

## Self-Check: PASSED

- `.github/workflows/ci.yml` exists: FOUND
- `README.md` badge line present: FOUND (grep confirms `actions/workflows/ci.yml/badge.svg`)
- Commits cd3c3bc and a7459f7: FOUND (git log)
- Test suite still green: 100 passed, 3 deselected, 1 xfailed
- Ruff clean: All checks passed
