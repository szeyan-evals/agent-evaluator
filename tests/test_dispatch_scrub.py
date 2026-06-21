"""Publication guard for source-system vocabulary.

The restricted strings are kept outside this repository. Only SHA-256
fingerprints are stored here, so the test can detect accidental reintroduction
without publishing the source-to-public vocabulary mapping.
"""

import hashlib
import json
import re
from pathlib import Path

from agent_evaluator.dispatch import all_scenarios

RESTRICTED_FINGERPRINTS = {
    "06cdede198bc96a594f1685fcdc2f7b3f39a454ac97d700a1c63b2bc02cd75e1",
    "4bf1926511c7294d9c3cfe23815e3cdaee2481590300cc884490a3886cfaad17",
    "e8177903fe8c2cbe706f9f859a41f684cfd6fc190cada9bf8beff0cb5005def4",
    "2fd26213d6e572849ca6b5b6b74e790ee6ae75b9a646d76780baf760dceddf85",
    "4261433e1b89061661bbdd15a47dda0f7a5fb890c6645de860d19475a7ff7fe2",
    "c741a75319e5724ca59a9fa2f69ae714cf13d39f6d7f6aaeba839bb599b4cf4d",
    "84fb95ba77e4406836794da332ad0ed8cf0839cfd35aa6406aedec14a42e23b8",
    "24011d0e544ad3d5d0048f0eb01ba6b035cac135c8c8e2c23e95f3333b2aced1",
    "421071eced1264d6e96ddc05dba1810f82e597c3dd184a4f331f320b0c70fb2d",
    "2facf57ab9e21fa61f6adb3e029fd3a5c9331f95f7eddec007b261d915ecdf22",
    "5d3c2887aab8c887cda1a73ea1518ad2a9601858354f5723b94ed0c8c1b8b612",
    "43db2afc1938a49aea463fda1a55af612eeb00a9f8bb17b57b5840fe7ed38748",
    "dccdacc87520c09e583c4138aa9301c90f430bf36b479f573d73e6404bae7cdd",
}

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".md", ".py", ".toml", ".json", ".yaml", ".yml", ".txt"}
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "results"}


def _fingerprint_hits(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    observed: set[str] = set()
    for size in (1, 2, 3):
        for index in range(len(words) - size + 1):
            phrase = " ".join(words[index:index + size])
            observed.add(hashlib.sha256(phrase.encode()).hexdigest())
    return observed & RESTRICTED_FINGERPRINTS


def test_publishable_tree_has_no_restricted_vocabulary():
    offenders: dict[str, list[str]] = {}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        hits = _fingerprint_hits(path.read_text(errors="replace"))
        if hits:
            offenders[str(path.relative_to(ROOT))] = sorted(hits)
    assert not offenders, f"restricted vocabulary fingerprints found: {offenders}"


def test_serialized_scenarios_have_no_restricted_vocabulary():
    blob = json.dumps([scenario.model_dump() for scenario in all_scenarios()])
    assert not _fingerprint_hits(blob)


def test_publication_safety_document_exists():
    path = ROOT / "src" / "agent_evaluator" / "dispatch" / "GLOSSARY.md"
    assert path.is_file()
