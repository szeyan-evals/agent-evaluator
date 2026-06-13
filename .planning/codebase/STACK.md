# Stack — agent-evaluator (brownfield)

Inferred from `pyproject.toml` and confirmed by the System Judge evidence manifest. Versions are minimums declared by the project; current runtime versions in `.venv/` may be higher.

## Runtime

| Component | Version | Role | Notes |
|---|---|---|---|
| Python | ≥3.11 | Language runtime | `pyproject.toml::requires-python`. `tests/` and `src/` use 3.11 features (`from __future__ import annotations`, `Literal`, `match` keyword in some scenarios). |
| `pydantic` | ≥2.7 | Data modeling | Hub of the codebase — every module imports from `models.py`. Forward references in `models.py:24, 57` rely on Pydantic v2 auto-rebuild. |
| `anthropic` | ≥0.40 | Anthropic SDK | Used by both `runner.py` (agent under test) and `judge.py` (judge LLM). Default judge model: `claude-sonnet-4-20250514`. |
| `openai` | ≥1.50 | OpenAI SDK | Used by `runner.py` for OpenAI-family agents. `OpenAIJudge` exists but is unreachable from CLI today. |
| `jinja2` | ≥3.1 | Prompt templates | Used by `rubrics.py` to render judge prompts per dimension. |
| `python-dotenv` | ≥1.0 | Env loading | Loads `.env` in `cli.py` and `examples/sample_run.py`. |
| `rich` | ≥13.0 | (declared, unused) | **Dead dependency.** No module imports `rich`. Remove or actually use during Phase 3 (VEND-04). |

## Dev / Build

| Component | Version | Role | Notes |
|---|---|---|---|
| `pytest` | ≥8.0 | Test runner | `asyncio_mode = "auto"`, `pythonpath = ["src"]`. |
| `pytest-asyncio` | ≥0.24 | Async test support | Used implicitly via `asyncio_mode = "auto"`. |
| `ruff` | ≥0.5 | Lint + format | `target-version = "py311"`, `line-length = 100`. No custom rule set. 6 minor findings in current code (3 auto-fixable). |
| `hatchling` | (build backend) | Wheel builder | Wheel packages `["src/agent_evaluator", "scenarios"]`. |

## Console Entry Point

```toml
[project.scripts]
agent-eval = "agent_evaluator.cli:main"
```

## Environment Variables

Documented vs actually-read divergence (per System Judge):

| Variable | Documented in `.env.example` | Actually read by code | Status |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes (required) | yes (via SDK auto-detection) | ✓ matches |
| `OPENAI_API_KEY` | yes (optional, "for model comparison") | yes (via SDK auto-detection) | ✓ matches; documentation framing is misleading per F-C (see judgment) |
| `JUDGE_MODEL` | yes | **no** | ✗ dead documentation |
| `AGENT_MODEL` | yes | **no** | ✗ dead documentation |

## Known Stack-Level Constraints

- **Python ≥3.11** — `from __future__ import annotations` + Pydantic v2 auto-rebuild assumes a behavior that may shift in Pydantic v3 or earlier Python.
- **Anthropic SDK is implicit on every code path** — even `compare --models gpt-4o,gpt-4o-mini` requires `ANTHROPIC_API_KEY` because the judge defaults to Anthropic. Phase 3 (VEND) addresses this.
- **No CI configured.** All quality checks are manual (`pytest`, `ruff`).
- **No git repo.** Project is not under version control as of 2026-05-05.

## v1 Stack Changes (planned)

- Phase 5: add `.github/workflows/ci.yml` for `pytest` + `ruff` on every push.
- Phase 5: possibly add a cassette/VCR library (`vcrpy` or hand-rolled fixtures) for `runner.py` / `judge.py` integration tests. Decided during Phase 5 discuss.
- Phase 3: remove `rich>=13.0` if not used by VEND-04 work (dead dep).
- Phase 3: remove or implement `JUDGE_MODEL` / `AGENT_MODEL` in `.env.example`.
