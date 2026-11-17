"""Password policy and hashing (FR-AUTH-03)."""

import pytest

from app.modules.identity.passwords import (
    hash_password,
    needs_rehash,
    policy_violations,
    verify_password,
)


def test_FR_AUTH_03_minimum_length_is_12() -> None:
    assert policy_violations("short-pass1") == ["password.too_short"]
    assert policy_violations("Twelve-chars") == []


def test_FR_AUTH_03_common_passwords_are_rejected_case_insensitively() -> None:
    # Present in the bundled list; long enough to pass the length rule.
    assert "password.too_common" in policy_violations("unbelievable")
    assert "password.too_common" in policy_violations("UnBelievable")


def test_overlong_passwords_are_rejected() -> None:
    assert policy_violations("x" * 129) == ["password.too_long"]


@pytest.mark.parametrize("candidate", ["Tuesday-Orchard-Lantern-42", "кирилица-парола-2026"])
def test_FR_AUTH_03_acceptable_passwords(candidate: str) -> None:
    assert policy_violations(candidate) == []


async def test_FR_AUTH_03_stored_only_as_argon2id_hash() -> None:
    hashed = await hash_password("Tuesday-Orchard-Lantern-42")
    assert hashed.startswith("$argon2id$")
    assert "Tuesday" not in hashed
    assert await verify_password(hashed, "Tuesday-Orchard-Lantern-42")
    assert not await verify_password(hashed, "tuesday-orchard-lantern-42")
    assert not needs_rehash(hashed)


async def test_garbage_hash_never_verifies() -> None:
    assert not await verify_password("not-a-hash", "anything")
