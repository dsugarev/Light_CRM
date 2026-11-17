"""Latin/Cyrillic normalisation for duplicates and search (FR-PARTY-01, FR-I18N-04)."""

import pytest

from app.core.text import (
    escape_like,
    fold,
    normalize_company_name,
    search_terms,
    search_text,
    transliterate,
)


@pytest.mark.parametrize(
    ("cyrillic", "latin"),
    [
        ("София", "sofia"),  # word-final -ия -> -ia (Transliteration Act)
        ("Мария Иванова", "maria ivanova"),
        ("Щастливец", "shtastlivets"),
        ("Юлиян Ъгълов", "yuliyan agalov"),
        ("Жълт Чай", "zhalt chay"),
    ],
)
def test_FR_I18N_04_bulgarian_transliteration(cyrillic: str, latin: str) -> None:
    assert transliterate(cyrillic) == latin


def test_fold_strips_accents_and_case() -> None:
    assert fold("Café ÉCOLE") == "cafe ecole"


@pytest.mark.parametrize(
    "variant",
    ["Акме ЕООД", "ACME e.o.o.d.", "Acme EOOD", "acme", "„Акме“ ООД", "Acme Ltd."],
)
def test_FR_PARTY_01_AC1_name_key_ignores_script_case_punctuation_and_legal_form(
    variant: str,
) -> None:
    assert normalize_company_name(variant) == "akme"


def test_name_key_keeps_names_made_only_of_a_legal_form() -> None:
    assert normalize_company_name("АД") == "ad"


def test_different_companies_keep_different_keys() -> None:
    assert normalize_company_name("Сирма Груп Холдинг АД") != normalize_company_name("Сирма АД")


def test_FR_I18N_04_search_text_holds_original_and_folded_forms() -> None:
    text = search_text("София Тех", None, "info@example.bg")
    assert "софия тех" in text
    assert "sofia teh" in text
    assert "info@example.bg" in text


def test_search_terms_offer_both_forms() -> None:
    assert search_terms("СОФИЯ tech") == [["софия", "sofia"], ["tech"]]


def test_like_wildcards_are_escaped() -> None:
    assert escape_like("100%_a\\b") == "100\\%\\_a\\\\b"
