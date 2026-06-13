"""Report generation — Markdown tables and per-scenario breakdowns.

Post-v1 TRUST schema: report cells distinguish three states:
- ok       → "0.85"           (legitimate score)
- error    → "err*"           (no usable score; * = partial, see footnote)
- na       → "--"             (dim doesn't apply, e.g. skipped error_recovery)

When at least one row is partial (any dim has status != "ok"), the row's
overall cell carries `*` and a footnote section lists the partial rows
with errored-dim names + error_type. Legacy (`legacy=True`) results are
skipped from main-table aggregations and listed separately.
"""

from __future__ import annotations

from agent_evaluator.models import DimensionScore, EvaluationResult
from agent_evaluator.rubrics import RUBRICS


def _render_dim_cell(ds: DimensionScore | None) -> str:
    """Render one dim cell honoring status. Returns '--' if ds is None or status='na'."""
    if ds is None:
        return "--"
    if ds.status == "na":
        return "--"
    if ds.status == "error":
        return "err*"
    return f"{ds.score:.2f}"


def _render_overall_cell(result: EvaluationResult) -> str:
    marker = "*" if result.partial else ""
    return f"**{result.overall_score:.2f}{marker}**"


def _partial_footnote_lines(results: list[EvaluationResult]) -> list[str]:
    """Build the 'Partial evaluations' footnote section. Empty if no partials.

    Phase 2 D3: only entries with status='error' surface here. status='na'
    is silent (rendered as -- in cells; routine, not actionable).
    """
    partial_results = [r for r in results if r.partial]
    if not partial_results:
        return []
    lines: list[str] = ["", "**Partial evaluations:**"]
    for r in partial_results:
        for ds in r.dimension_scores:
            if ds.status != "error":
                continue
            err = ds.error_type or "unknown"
            lines.append(
                f"- `{r.model_id}` on `{r.scenario_id}`: {ds.dimension} "
                f"errored ({err}) — excluded from overall"
            )
    lines.append("")
    return lines


def _legacy_footnote_lines(legacy_results: list[EvaluationResult]) -> list[str]:
    if not legacy_results:
        return []
    lines: list[str] = ["", "**Legacy evaluations excluded** (pre-v1 TRUST schema, may contain silent zeros — see JUDGMENT.md F-A):"]
    for r in legacy_results:
        lines.append(
            f"- `{r.model_id}` on `{r.scenario_id}` (schema_version={r.schema_version})"
        )
    lines.append("")
    return lines


def generate_report(results: list[EvaluationResult]) -> str:
    """Generate a Markdown evaluation report (single model)."""
    lines: list[str] = []
    lines.append("# Agent Trajectory Evaluation Report\n")

    if not results:
        lines.append("No results to report.\n")
        return "\n".join(lines)

    # Filter legacy out of main aggregation; surface separately.
    legacy_results = [r for r in results if r.legacy]
    active_results = [r for r in results if not r.legacy]

    if not active_results:
        lines.append("No non-legacy results to report.\n")
        lines.extend(_legacy_footnote_lines(legacy_results))
        return "\n".join(lines)

    model_id = active_results[0].model_id
    lines.append(f"**Model**: `{model_id}`\n")
    lines.append(f"**Scenarios evaluated**: {len(active_results)}\n")

    # Summary table
    dimensions = list(RUBRICS.keys())
    dim_headers = [d.replace("_", " ").title() for d in dimensions]

    lines.append("## Summary\n")
    header = "| Scenario | " + " | ".join(dim_headers) + " | Overall |"
    separator = "|" + "|".join(["---"] * (len(dimensions) + 2)) + "|"
    lines.append(header)
    lines.append(separator)

    for result in active_results:
        ds_by_dim = {s.dimension: s for s in result.dimension_scores}
        cells = [_render_dim_cell(ds_by_dim.get(d)) for d in dimensions]
        row = (
            f"| {result.scenario_id} | "
            + " | ".join(cells)
            + f" | {_render_overall_cell(result)} |"
        )
        lines.append(row)

    # Averages row — TRUST-04 strict: mark partial when any contributing row was partial.
    any_partial = any(r.partial for r in active_results)
    partial_count = sum(1 for r in active_results if r.partial)
    avg_dim_cells: list[str] = []
    for dim in dimensions:
        # Only count ok-status entries for that dim
        ok_scores = [
            s.score
            for r in active_results
            for s in r.dimension_scores
            if s.dimension == dim and s.status == "ok"
        ]
        excluded = any(
            s.dimension == dim and s.status != "ok"
            for r in active_results
            for s in r.dimension_scores
        )
        if not ok_scores:
            avg_dim_cells.append("--")
        else:
            avg = sum(ok_scores) / len(ok_scores)
            avg_dim_cells.append(f"{avg:.2f}{'*' if excluded else ''}")

    avg_overall = sum(r.overall_score for r in active_results) / len(active_results)
    overall_marker = "*" if any_partial else ""
    lines.append(
        "| **Average** | "
        + " | ".join(avg_dim_cells)
        + f" | **{avg_overall:.2f}{overall_marker}** |"
    )

    if any_partial:
        lines.append(
            f"\n*Average computed across {len(active_results)} rows; "
            f"{partial_count} were partial.*"
        )

    lines.extend(_partial_footnote_lines(active_results))
    lines.extend(_legacy_footnote_lines(legacy_results))

    # Per-scenario details
    lines.append("## Scenario Details\n")
    for result in active_results:
        lines.append(f"### {result.scenario_id}\n")
        for score in result.dimension_scores:
            cell = _render_dim_cell(score)
            if score.status == "ok":
                # Phase 4: surface judge_method on the header line
                annotation = f"  _({score.judge_method})_"
            else:
                # Existing status surfacing for error/na
                annotation = (
                    f"  _(status: {score.status}, "
                    f"error_type: {score.error_type or '—'})_"
                )
            lines.append(
                f"**{score.dimension.replace('_', ' ').title()}**: {cell}"
                f"{annotation}"
            )
            lines.append(f"> {score.reasoning}\n")
            if score.evidence:
                for e in score.evidence:
                    lines.append(f"- {e}")
                lines.append("")
        if result.cost_usd is not None:
            lines.append(f"**Run cost (est.)**: ${result.cost_usd:.4f}\n")
        lines.append("---\n")

    return "\n".join(lines)


def generate_comparison_report(
    results_by_model: dict[str, list[EvaluationResult]],
) -> str:
    """Generate a side-by-side model comparison report."""
    lines: list[str] = []
    lines.append("# Model Comparison Report\n")

    models = list(results_by_model.keys())
    if not models:
        lines.append("No results to compare.\n")
        return "\n".join(lines)

    # Filter legacy out of each model's results, surface separately.
    active_by_model: dict[str, list[EvaluationResult]] = {}
    legacy_collect: list[EvaluationResult] = []
    for m, rs in results_by_model.items():
        active_by_model[m] = [r for r in rs if not r.legacy]
        legacy_collect.extend(r for r in rs if r.legacy)

    lines.append(f"**Models compared**: {', '.join(f'`{m}`' for m in models)}\n")

    # Union of scenarios across active results only
    all_scenarios: set[str] = set()
    for results in active_by_model.values():
        for r in results:
            all_scenarios.add(r.scenario_id)
    scenarios = sorted(all_scenarios)

    dimensions = list(RUBRICS.keys())

    # Per-dimension comparison tables
    for dim in dimensions:
        dim_title = dim.replace("_", " ").title()
        lines.append(f"## {dim_title}\n")

        header = "| Scenario | " + " | ".join(f"`{m}`" for m in models) + " |"
        separator = "|" + "|".join(["---"] * (len(models) + 1)) + "|"
        lines.append(header)
        lines.append(separator)

        for scenario_id in scenarios:
            cells = []
            for model in models:
                model_results = active_by_model[model]
                result = next(
                    (r for r in model_results if r.scenario_id == scenario_id),
                    None,
                )
                if result:
                    ds = next(
                        (s for s in result.dimension_scores if s.dimension == dim),
                        None,
                    )
                    cells.append(_render_dim_cell(ds))
                else:
                    cells.append("—")
            lines.append(f"| {scenario_id} | " + " | ".join(cells) + " |")

        lines.append("")

    # Overall comparison
    lines.append("## Overall Scores\n")
    header = "| Scenario | " + " | ".join(f"`{m}`" for m in models) + " |"
    separator = "|" + "|".join(["---"] * (len(models) + 1)) + "|"
    lines.append(header)
    lines.append(separator)

    for scenario_id in scenarios:
        cells = []
        for model in models:
            result = next(
                (r for r in active_by_model[model] if r.scenario_id == scenario_id),
                None,
            )
            cells.append(_render_overall_cell(result) if result else "—")
        lines.append(f"| {scenario_id} | " + " | ".join(cells) + " |")

    # Footnotes (partials across all models, legacy across all models)
    all_active = [r for rs in active_by_model.values() for r in rs]
    lines.extend(_partial_footnote_lines(all_active))
    lines.extend(_legacy_footnote_lines(legacy_collect))

    lines.append("")
    return "\n".join(lines)
