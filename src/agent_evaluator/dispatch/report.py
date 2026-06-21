"""Render a dispatch EvaluationReport as Markdown.

A generated artifact (regenerates from one command), not a live dashboard. It
emits the numbers — per-layer pass rates, pass^k, high-cost failures, and a
MECHANICAL release signal. The written release recommendation is the operator's
to make; this report is its evidence base.
"""

from __future__ import annotations

from agent_evaluator.dispatch.scoring import EvaluationReport


def render_dispatch_report(report: EvaluationReport) -> str:
    lines: list[str] = ["# Dispatch Agent Evaluation\n"]

    passed, total = report.overall()
    signal, why = report.release_signal()
    lines.append(f"**Overall:** {passed}/{total} scenarios passed\n")
    lines.append(f"**Release signal (mechanical):** {signal} — {why}")
    lines.append("> The written release recommendation is the operator's call; "
                 "this is the evidence, not the verdict.\n")

    lines.append("## Pass rate by layer\n")
    lines.append("| Layer | Passed | Total |")
    lines.append("|---|---|---|")
    for layer, (p, t) in report.by_layer().items():
        lines.append(f"| {layer} | {p} | {t} |")
    lines.append("")

    highs = report.high_cost_failures()
    if highs:
        lines.append("## ⚠ High-cost failures (release-critical)\n")
        for r in highs:
            lines.append(f"- `{r.id}` ({r.probes}) — {r.reason}")
        lines.append("")

    lines.append("## Per-scenario results\n")
    lines.append("| Scenario | Layer | Cost | Result | pass^k | Tools | Notes |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in report.results:
        mark = "✓" if r.passed else "✗"
        passk = f"{r.trial_passes}/{r.trials}" if r.trials > 1 else "—"
        lines.append(
            f"| {r.id} | {r.layer} | {r.error_cost} | {mark} | {passk} | "
            f"{r.tool_calls} | {r.reason} |"
        )
    lines.append("")
    return "\n".join(lines)
