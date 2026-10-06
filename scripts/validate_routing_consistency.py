#!/usr/bin/env python3
"""
Routing consistency validator.

model-routing/models.json is documented as the single source of truth for tier
definitions, but the tier -> model mapping is duplicated in several places. When
a tier is retired or renumbered, those copies drift silently and the agent starts
reporting a model it is not running on.

This checks that every copy agrees with models.json:

  - model-routing/model_router.py    MODELS dict
  - scripts/slack_model_router.py    self.models dict
  - model-routing/ROUTING.md         routing table
  - skills/dm-model-signature/SKILL.md  chip table
  - README.md                        section 3.1 tier table

It also rejects any reference to a model ID that models.json no longer lists, so
a retired tier cannot linger in prose.

Note the ID convention: models.json and the docs use dots
(anthropic/claude-opus-4.8); OpenRouter calls use dashes
(anthropic/claude-opus-4-8) because dots 404. Both spellings are accepted here
and normalised before comparison.

Usage:
    python3 scripts/validate_routing_consistency.py

Exit 0 if consistent, 1 if not.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Model IDs that used to be in service. If one of these shows up in a tier
# mapping or a tier table, something was missed during a renumbering.
RETIRED_MODELS = {
    "anthropic/claude-opus-4.7",
    "anthropic/claude-opus-4.6",
    "anthropic/claude-haiku-4.5",
}


def norm(model_id: str) -> str:
    """Normalise an OpenRouter model ID for comparison (dashes -> dots)."""
    model_id = model_id.strip().strip("`\"'")
    # Only the version suffix differs in spelling: claude-opus-4-8 -> claude-opus-4.8
    return re.sub(r"-(\d+)-(\d+)$", r"-\1.\2", model_id)


def load_source_of_truth():
    data = json.loads((REPO / "model-routing" / "models.json").read_text())
    tiers = {t["id"]: norm(t["model"]) for t in data["tiers"]}
    return tiers


def extract_dict_mapping(path: Path, pattern: str) -> dict:
    """Pull "lN": "model/id" pairs out of a Python source file."""
    text = path.read_text()
    block = re.search(pattern, text, re.S)
    if not block:
        return {}
    return {
        m.group(1): norm(m.group(2))
        for m in re.finditer(r'"(l\d)":\s*"([^"]+)"', block.group(0))
    }


def check(label: str, found: dict, truth: dict, errors: list, *, subset_ok: bool = False):
    """Compare a discovered tier mapping against models.json."""
    if not found:
        errors.append(f"{label}: no tier mapping found — did the file structure change?")
        return

    for tier, model in sorted(found.items()):
        if tier not in truth:
            errors.append(
                f"{label}: defines {tier} ({model}) but models.json has no such tier"
            )
        elif model != truth[tier]:
            errors.append(
                f"{label}: {tier} = {model}, models.json says {truth[tier]}"
            )

    if not subset_ok:
        for tier in sorted(set(truth) - set(found)):
            errors.append(f"{label}: missing {tier} ({truth[tier]}) from models.json")


def check_retired(label: str, path: Path, errors: list):
    text = path.read_text()
    for retired in sorted(RETIRED_MODELS):
        # Allow a retirement note to name the model, but not a live mapping.
        for line in text.splitlines():
            if retired not in line and norm(retired) not in norm_line(line):
                continue
            if re.search(r"retir|remov|stale|was\s+L\d|legacy|deprecat", line, re.I):
                continue
            errors.append(f"{label}: retired model {retired} still referenced: {line.strip()[:100]}")


def norm_line(line: str) -> str:
    return re.sub(r"-(\d+)-(\d+)\b", r"-\1.\2", line)


def main() -> int:
    truth = load_source_of_truth()
    errors: list = []

    print("models.json — source of truth:")
    for tier, model in sorted(truth.items()):
        print(f"  {tier} = {model}")
    print()

    # ── Python tier maps ─────────────────────────────────────────────────────
    check(
        "model_router.py MODELS",
        extract_dict_mapping(REPO / "model-routing" / "model_router.py", r"MODELS\s*=\s*\{.*?\n\}"),
        truth,
        errors,
    )
    # The Slack router predates L5 and only ever handled L1-L4, so a subset is fine.
    check(
        "slack_model_router.py self.models",
        extract_dict_mapping(REPO / "scripts" / "slack_model_router.py", r"self\.models\s*=\s*\{.*?\n\s*\}"),
        truth,
        errors,
        subset_ok=True,
    )

    # ── Docs that carry a tier table ─────────────────────────────────────────
    doc_files = [
        ("ROUTING.md", REPO / "model-routing" / "ROUTING.md"),
        ("dm-model-signature/SKILL.md", REPO / "skills" / "dm-model-signature" / "SKILL.md"),
        ("README.md", REPO / "README.md"),
        ("models.json", REPO / "model-routing" / "models.json"),
        ("model_router.py", REPO / "model-routing" / "model_router.py"),
    ]
    for label, path in doc_files:
        if path.exists():
            check_retired(label, path, errors)
        else:
            errors.append(f"{label}: file missing at {path}")

    # ── Every tier in models.json should be named in ROUTING.md ─────────────
    routing = (REPO / "model-routing" / "ROUTING.md").read_text()
    routing_norm = norm_line(routing)
    for tier, model in sorted(truth.items()):
        if model not in routing_norm:
            errors.append(f"ROUTING.md: does not document {tier} model {model}")
        if not re.search(rf"\b{tier.upper()}\b", routing):
            errors.append(f"ROUTING.md: does not mention tier {tier.upper()}")

    if errors:
        print("❌ ROUTING INCONSISTENT")
        for e in errors:
            print(f"   - {e}")
        return 1

    print("✅ Routing consistent across models.json, routers, and docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
