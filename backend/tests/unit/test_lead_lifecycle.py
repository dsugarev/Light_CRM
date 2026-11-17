"""Lead lifecycle and qualification score (FR-LEAD-02, FR-LEAD-03)."""

import itertools

import pytest

from app.modules.sales.lifecycle import (
    BANT_ITEMS,
    next_status,
    qualification_score,
    unknown_bant_items,
)

STATUSES = ("new", "contacted", "qualified", "converted", "disqualified")
# The allowed transitions of the API spec (section 9); everything else is refused.
ALLOWED = {
    ("mark_contacted", "new"): "contacted",
    ("qualify", "contacted"): "qualified",
    ("disqualify", "new"): "disqualified",
    ("disqualify", "contacted"): "disqualified",
    ("disqualify", "qualified"): "disqualified",
    ("reopen", "disqualified"): "contacted",
    ("convert", "qualified"): "converted",
}


@pytest.mark.parametrize(
    ("action", "status"),
    list(
        itertools.product(
            ["mark_contacted", "qualify", "disqualify", "reopen", "convert"], STATUSES
        )
    ),
)
def test_FR_LEAD_02_transition_matrix(action: str, status: str) -> None:
    assert next_status(action, status) == ALLOWED.get((action, status))


def test_FR_LEAD_02_AC2_converted_and_disqualified_are_terminal_except_reopen() -> None:
    for action in ("mark_contacted", "qualify", "disqualify", "convert"):
        assert next_status(action, "converted") is None
        assert next_status(action, "disqualified") is None


@pytest.mark.parametrize(
    ("statuses", "score"),
    [
        (("yes", "partial", "yes", "unknown"), 63),  # the API spec example: 62.5 rounds up
        (("yes", "yes", "yes", "yes"), 100),
        (("unknown",) * 4, 0),
        (("no", "no", "no", "no"), 0),
        (("partial", "partial", "partial", "partial"), 50),
        (("partial", "no", "no", "no"), 13),
        (("yes", "partial", "partial", "partial"), 63),
    ],
)
def test_FR_LEAD_03_AC2_score(statuses: tuple[str, ...], score: int) -> None:
    assert qualification_score(dict(zip(BANT_ITEMS, statuses, strict=True))) == score


def test_FR_LEAD_03_AC1_unknown_items_are_listed() -> None:
    statuses = {"budget": "yes", "authority": "unknown", "need": "no", "timeline": "unknown"}
    assert unknown_bant_items(statuses) == ["authority", "timeline"]
    assert unknown_bant_items(dict.fromkeys(BANT_ITEMS, "no")) == []
