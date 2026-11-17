"""Bulgarian unified identification code (EIK/UIC, BULSTAT) checksum.

9-digit codes: weights 1..8 mod 11; if the result is 10, weights 3..10 mod 11;
if that is 10 again the check digit is 0. 13-digit codes (branches) add a second
check over digits 9-12 with weights (2, 7, 3, 5), then (4, 9, 5, 7).
A wrong checksum is reported as a warning, not an error (owner decision, Phase 2).
"""


def _check(digits: list[int], first: tuple[int, ...], second: tuple[int, ...]) -> int:
    value = sum(d * w for d, w in zip(digits, first, strict=True)) % 11
    if value == 10:
        value = sum(d * w for d, w in zip(digits, second, strict=True)) % 11
    return 0 if value == 10 else value


def is_valid_eik(code: str) -> bool:
    if not code.isdigit() or len(code) not in (9, 13):
        return False
    digits = [int(c) for c in code]
    if _check(digits[:8], (1, 2, 3, 4, 5, 6, 7, 8), (3, 4, 5, 6, 7, 8, 9, 10)) != digits[8]:
        return False
    if len(code) == 13:
        return _check(digits[8:12], (2, 7, 3, 5), (4, 9, 5, 7)) == digits[12]
    return True
