"""Lead lifecycle and qualification score (FR-LEAD-02, FR-LEAD-03). Pure functions.

new ──> contacted ──> qualified ──> converted
 │          │             │
 └──────────┴─────────────┴──> disqualified ──(reopen, Manager+)──> contacted
"""

from collections.abc import Mapping

OPEN_STATUSES = frozenset({"new", "contacted", "qualified"})
READ_ONLY_STATUSES = frozenset({"converted", "disqualified"})

# action -> (statuses it may start from, resulting status)
TRANSITIONS: Mapping[str, tuple[frozenset[str], str]] = {
    "mark_contacted": (frozenset({"new"}), "contacted"),
    "qualify": (frozenset({"contacted"}), "qualified"),
    "disqualify": (OPEN_STATUSES, "disqualified"),
    "reopen": (frozenset({"disqualified"}), "contacted"),
    "convert": (frozenset({"qualified"}), "converted"),  # Phase 4
}

BANT_ITEMS = ("budget", "authority", "need", "timeline")
_POINTS = {"yes": 25.0, "partial": 12.5, "no": 0.0, "unknown": 0.0}


def next_status(action: str, current: str) -> str | None:
    """The status after `action`, or None when the action is not allowed from `current`."""
    allowed_from, result = TRANSITIONS[action]
    return result if current in allowed_from else None


def qualification_score(statuses: Mapping[str, str]) -> int:
    """yes = 25, partial = 12.5, no/unknown = 0 per BANT item, rounded half up (0..100).

    The spec's example (yes, partial, yes, unknown) gives 62.5 -> 63.
    """
    total = sum(_POINTS[statuses[item]] for item in BANT_ITEMS)
    return int(total + 0.5)


def unknown_bant_items(statuses: Mapping[str, str]) -> list[str]:
    """Items still unknown; qualifying needs none (FR-LEAD-03 AC1)."""
    return [item for item in BANT_ITEMS if statuses[item] == "unknown"]
