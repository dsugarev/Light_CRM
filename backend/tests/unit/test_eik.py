"""EIK/UIC checksum (FR-PARTY-01): a wrong checksum is a warning, not an error."""

import pytest

from app.modules.party.eik import is_valid_eik

# Vectors computed by hand from the published algorithm (fictional numbers):
#   123456789: 1*1+2*2+...+8*8 = 204, 204 mod 11 = 6 -> valid check digit is 6.
#   13 digits 123456786 + 000: (6*2 + 0*7 + 0*3 + 0*5) mod 11 = 1 -> last digit 1.


@pytest.mark.parametrize("code", ["123456786", "000000000", "1234567860001"])
def test_valid_codes(code: str) -> None:
    assert is_valid_eik(code)


@pytest.mark.parametrize("code", ["123456789", "1234567860002", "12345678", "12345678a", ""])
def test_invalid_codes(code: str) -> None:
    assert not is_valid_eik(code)


def test_second_weights_are_used_when_the_first_sum_gives_10() -> None:
    # Digits 1..8 = 0,0,0,0,2,0,0,0. First weights 1..8: 2*5 = 10 -> 10 mod 11 = 10,
    # so the second weights 3..10 apply: 2*7 = 14 -> 14 mod 11 = 3. Check digit 3.
    assert is_valid_eik("000020003")
    assert not is_valid_eik("000020000")
