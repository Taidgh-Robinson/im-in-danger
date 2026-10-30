"""Per-criterion status reported by the agent."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

STATUS_FILE = "status.json"


@dataclass(frozen=True, slots=True)
class CriterionStatus:
    """The agent's assessment of one checklist item; `met` is None when unreported."""

    id: str
    text: str
    met: bool | None
    evidence: str = ""


def read_status(
    path: Path, checklist: Sequence[tuple[str, str]]
) -> tuple[CriterionStatus, ...] | None:
    """Return status for every checklist item, or None when the file is unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    statuses = []
    for item_id, text in checklist:
        entry = data.get(item_id)
        met: bool | None = None
        evidence = ""
        if isinstance(entry, dict):
            if isinstance(entry.get("met"), bool):
                met = entry["met"]
            if isinstance(entry.get("evidence"), str):
                evidence = entry["evidence"].strip()
        statuses.append(CriterionStatus(item_id, text, met, evidence))
    return tuple(statuses)


def format_status(statuses: Sequence[CriterionStatus]) -> str:
    """Render statuses as a terminal checklist."""
    marks = {True: "x", False: " ", None: "?"}
    lines = []
    for status in statuses:
        lines.append(f"[{marks[status.met]}] {status.id}: {status.text}")
        if status.evidence:
            lines.append(f"      {status.evidence}")
    return "\n".join(lines)
