"""Text normalisation for duplicate detection and search (Latin and Cyrillic).

Bulgarian is transliterated with the official Streamlined System (Transliteration
Act 2009), including the rule that word-final "-ия" becomes "-ia", so that
"София" and "Sofia", or "Акме ЕООД" and "Acme EOOD", compare equal.
"""

import re
import unicodedata

_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sht", "ъ": "a", "ь": "y", "ю": "yu", "я": "ya",
    # Non-Bulgarian Cyrillic letters that appear in company and person names.
    "ё": "yo", "э": "e", "ы": "y", "і": "i", "ї": "yi", "є": "ye", "ґ": "g",
}  # fmt: skip

# Legal forms ignored when comparing organisation names (Bulgarian and common foreign).
_LEGAL_FORMS = frozenset(
    {
        "eood", "ood", "ead", "ad", "et", "kd", "kda", "sd", "dzzd", "adsits",
        "ltd", "llc", "inc", "plc", "gmbh", "ag", "sa", "srl", "spa", "bv", "nv", "co",
    }
)  # fmt: skip
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_FINAL_IA = re.compile(r"ия\b")


def transliterate(text: str) -> str:
    """Lower-case Latin rendering of `text` (Latin input passes through)."""
    lowered = _FINAL_IA.sub("ia", text.casefold())
    return "".join(_CYRILLIC.get(char, char) for char in lowered)


def fold(text: str) -> str:
    """Case-fold, transliterate and strip accents: the form used for comparisons."""
    decomposed = unicodedata.normalize("NFKD", transliterate(text))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# Latin spellings that transliterated Bulgarian cannot produce, mapped to the
# letters it does produce ("Acme" vs "Акме" -> "akme"). Used for the duplicate key only.
_PHONETIC = (("ph", "f"), ("kh", "h"), ("ck", "k"), ("c", "k"), ("q", "k"), ("w", "v"), ("x", "ks"))


def normalize_company_name(name: str) -> str:
    """Duplicate key for an organisation name: folded, punctuation and legal forms
    removed, Latin spellings aligned with transliterated Bulgarian.

    "Акме ЕООД", "ACME e.o.o.d." and "Acme EOOD" all become "akme".
    """
    # Dots are dropped first so abbreviations such as "e.o.o.d." or "Ltd." form one word.
    words = _NON_WORD.sub(" ", fold(name).replace(".", "")).split()
    kept = [w for w in words if w not in _LEGAL_FORMS] or words
    key = " ".join(kept)
    for latin, replacement in _PHONETIC:
        key = key.replace(latin, replacement)
    return key


def search_text(*parts: str | None) -> str:
    """Text stored for searching: each part in its original lower case and folded,
    so both "софия" and "sofia" find "София"."""
    pieces: list[str] = []
    for part in parts:
        if part:
            lowered = part.casefold()
            pieces.append(lowered)
            folded = fold(part)
            if folded != lowered:
                pieces.append(folded)
    return " ".join(pieces)


def search_terms(query: str) -> list[list[str]]:
    """Terms of a free-text query; each term matches in its original or folded form."""
    terms: list[list[str]] = []
    for word in query.split():
        variants = list(dict.fromkeys([word.casefold(), fold(word)]))
        terms.append(variants)
    return terms


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
