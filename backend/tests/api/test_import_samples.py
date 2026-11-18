"""The sample import files in docs/import-samples import cleanly (FR-IMP-01; owner answer to
requirements open question 2: no real trackers, so a documented sample format instead)."""

from pathlib import Path

import pytest

from app.core.principal import RoleCode
from app.modules.dataimport.fields import FIELDS, EntityType
from tests.api.test_imports import run
from tests.helpers import TestApp

SAMPLES = Path(__file__).resolve().parents[3] / "docs" / "import-samples"
ORDER: tuple[EntityType, ...] = ("organizations", "contacts", "leads", "opportunities")
# Later files refer to organizations in earlier ones.


def test_every_sample_column_is_a_template_header() -> None:
    for entity in ORDER:
        header = (SAMPLES / f"{entity}.csv").read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == [f.en for f in FIELDS[entity]], entity


def test_the_format_document_lists_every_field_in_both_languages() -> None:
    doc = (SAMPLES.parent / "import-format.md").read_text(encoding="utf-8")
    for entity in ORDER:
        for field in FIELDS[entity]:
            assert f"| {field.en} | {field.bg} |" in doc, (entity, field.key)


@pytest.mark.parametrize("duplicates", ["skip"])
async def test_FR_IMP_01_samples_import_without_errors(test_app: TestApp, duplicates: str) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    for entity in ORDER:
        content = (SAMPLES / f"{entity}.csv").read_bytes()
        batch = await run(manager, entity, content, name=f"{entity}.csv", duplicates=duplicates)
        assert None not in batch["mapping"].values(), (entity, batch["mapping"])
        counts = batch["counts"]
        assert (counts["valid"], counts["invalid"]) == (3, 0), (entity, counts)
        committed = await manager.post(
            f"/api/v1/imports/{batch['id']}/commit", json={"mode": "strict"}
        )
        assert committed.status_code == 200, committed.text
        assert committed.json()["counts"]["created"] == 3, entity
