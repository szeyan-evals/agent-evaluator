# Phase 5 Discussion Log — Test Coverage and CI

**Date:** 2026-05-07
**Phase:** 05 — Test Coverage and CI (final phase of v1)
**Mode:** default (manual fallback)

User selected 2 of 4 presented gray areas; the other 2 were locked at recommended defaults.

---

## Areas presented

1. Cassette / replay strategy
2. Coverage targets
3. CI scope ✓ selected
4. Live-API tests ✓ selected

User chose to discuss the user-facing decisions (live tests behavior, CI configuration); the implementation-detail areas (fixture format, test count) were left at sensible defaults.

---

## Area 1 (locked default) — Cassette strategy

**Locked:** Hand-rolled fixtures (JSON files in `tests/fixtures/` + extended `_FakeClient` pattern from Phase 2/3). No `vcrpy` dependency added.

---

## Area 2 (locked default) — Coverage targets

**Locked:** Standard. ~12-15 new tests covering happy paths + parse errors + 3 specific regression guards (F-G, F-H, F-I).

---

## Area 3 — Live-API tests

**Selection:** Marker-skipped live tests (Recommended)

**Decision:** D3 — Add `live` pytest marker; new `tests/test_live_smoke.py` with ~3 marker-skipped tests; CI runs `pytest -m 'not live'`. Local opt-in via `pytest -m live` (requires API keys in env). Provides the structured live-API verification path the user has been deferring across Phases 1-4.

---

## Area 4 — CI scope

**Selection:** Standard (Recommended) — pytest + ruff

**Decision:** D4 — `.github/workflows/ci.yml` runs `ruff check` + `pytest -m 'not live'`. Single Python 3.11. Triggers on push-to-main + every PR. ~30s total runtime. No coverage threshold (deferred to v2).

---

## Decisions summary

| ID | Decision | Captured |
|----|----------|----------|
| D1 | Hand-rolled JSON fixtures + `_FixtureClient` helper (no vcrpy) | CONTEXT §D1 |
| D2 | ~12-15 new tests; standard coverage with F-G/F-H/F-I regression guards | CONTEXT §D2 |
| D3 | `@pytest.mark.live` marker; ~3 live-API tests opt-in via `pytest -m live`; CI excludes | CONTEXT §D3 |
| D4 | Standard CI (pytest + ruff) on push to main + PRs; Python 3.11 only | CONTEXT §D4 |

## Cross-phase impact

None. Phase 5 is purely additive — adds tests + CI without modifying production code from Phases 1-4. F-H regression guard test for `_run_anthropic` may be xfail since the underlying unguarded-usage bug is documented but unfixed (per Phase 1 risk #2).

## Scope creep redirected

None. User chose strict-minimum CI scope and deferred live tests cleanly via the marker pattern. Discussed but rejected: coverage thresholds, multi-version matrix, vcrpy integration — all v2.

## v1 closure note

**Phase 5 is the final phase of the v1 remediation milestone.** When it lands:
- All TEST-01..04 requirements satisfied
- All 5 phases (TRUST/DIM/VEND/DET/TEST) complete
- System Judge can be re-run as `judge ship` for milestone validation
- Recommended next step: regenerate `results/comparison.md` post-Phase-1+2 to demonstrate the F-A and F-B remediation empirically (the `results/legacy/comparison-2026-04-08.md` artifact is the "before" snapshot)
