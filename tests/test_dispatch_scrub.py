"""Scrub guard: no company-specific vocabulary may leak into the dispatch domain.

Scans the dispatch package's Python source AND the serialized scenario data for
a blocklist of proprietary terms. If anyone reintroduces one (e.g. while adding
a scenario), this test fails loudly. The audit trail in dispatch/GLOSSARY.md is
intentionally NOT scanned — it is the one place the originals are named.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_evaluator.dispatch import all_scenarios  # noqa: E402

# Lowercased substrings that must never appear in published source/data.
# "deadhead"/"linehaul" are deliberately NOT here — they are generic trucking terms.
BANNED_TERMS = [
    "5f",
    "fleetforce",
    "fleet force",
    "frac",
    "preload",
    "sandi",
    "lohi",
    "vorto",
    "agnus",
    "subcontractor",
    "well diversion",
    "up for grabs",
    "up_for_grabs",
    " hse ",  # spaced to avoid matching unrelated substrings
]

_DISPATCH_DIR = Path(__file__).resolve().parent.parent / "src" / "agent_evaluator" / "dispatch"


def _hits(text: str) -> list[str]:
    low = text.lower()
    return [term for term in BANNED_TERMS if term in low]


def test_package_source_has_no_banned_terms():
    offenders: dict[str, list[str]] = {}
    for py in sorted(_DISPATCH_DIR.glob("*.py")):
        hits = _hits(py.read_text())
        if hits:
            offenders[py.name] = hits
    assert not offenders, f"proprietary terms leaked into source: {offenders}"


def test_serialized_scenarios_have_no_banned_terms():
    # The data an agent (and any published artifact) actually sees.
    blob = json.dumps([sc.model_dump() for sc in all_scenarios()])
    assert not _hits(blob), f"proprietary terms leaked into scenario data: {_hits(blob)}"


def test_glossary_exists_as_the_audit_trail():
    assert (_DISPATCH_DIR / "GLOSSARY.md").is_file()
