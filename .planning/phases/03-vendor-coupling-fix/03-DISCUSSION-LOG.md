# Phase 3 Discussion Log — Vendor Coupling Fix

**Date:** 2026-05-06
**Phase:** 03 — Vendor Coupling Fix
**Mode:** default (4 single-question turns; manual fallback for SDK-API mismatch)

User selected all 4 presented gray areas.

---

## Area 1 — Judge consolidation strategy

**Selection:** Two classes + factory dispatcher (Recommended)

**Locked decision:** D1 — `make_judge(model)` factory in `judge.py` picks `AnthropicJudge` or `OpenAIJudge` based on prefix.

---

## Area 2 — Routing signal source

**Selection:** Reuse `runner._is_openai_model` (Recommended)

**Locked decision:** D2 — `judge.py::make_judge` imports `_is_openai_model` from `runner.py`. Single source of truth.

---

## Area 3 — `--judge-model` default on `compare`

**Selection:** First model in --models (Recommended)

**Notes:** Self-judging is the default; users override with `--judge-model`. `--help` text includes self-judging caveat. Picking this option means JUDGE_MODEL env var stays unimplemented; cleaned up in Area 4.

**Locked decision:** D3.

---

## Area 4 — Hygiene scope

**Selection:** Strict minimum (Recommended)

**Notes:** Five hygiene items: pyproject.toml `rich` removal, `.env.example` JUDGE_MODEL/AGENT_MODEL removal, `book_flight.py` unused-import cleanup, README API-key section update, `--judge-model` documentation in compare usage example.

**Locked decision:** D4.

---

## Decisions summary

| ID | Decision | Captured |
|----|----------|----------|
| D1 | Two parallel judge classes + `make_judge(model)` factory dispatcher | CONTEXT §D1 |
| D2 | Reuse `runner._is_openai_model` (single source of truth, no new module) | CONTEXT §D2 |
| D3 | `--judge-model` default = `args.judge_model or models[0]` (first model). Self-judging caveat in --help. | CONTEXT §D3 |
| D4 | Strict-minimum hygiene: 5 specific changes | CONTEXT §D4 |

## Cross-phase impact

None. Phase 3 is independent of Phase 1+2 (different code paths). The factory function uses TRUST schema implicitly (judges return `DimensionScore`s with status fields; unchanged behavior).

## Scope creep redirected

None during this discussion. User explicitly chose strict-minimum hygiene over comprehensive README rewrite — kept Phase 3 scope tight.
