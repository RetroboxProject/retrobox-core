import locale
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class LangData:
    aliases: List[str]
    lang: str
    region: str


# Direct port of EmulationStation's langDatas table.
LANG_DATA: List[LangData] = [
    LangData(["usa", "us", "u"], "en", "us"),

    LangData(["europe", "eu", "e", "ue", "euro"], "", "eu"),

    LangData(["w", "wor", "world"], "en", "wr"),
    LangData(["uk", "gb"], "en", "eu"),
    LangData(["es", "spain", "s"], "es", "eu"),
    LangData(["fr", "france", "fre", "french", "f"], "fr", "eu"),
    LangData(["de", "germany", "d"], "de", "eu"),
    LangData(["it", "italy", "i"], "it", "eu"),
    LangData(["nl", "netherlands"], "nl", "eu"),
    LangData(["gr", "greece"], "gr", "eu"),
    LangData(["no"], "no", "eu"),
    LangData(["sw", "sweden", "se"], "sw", "eu"),
    LangData(["pt", "portugal"], "pt", "eu"),
    LangData(["pl", "poland"], "pl", "eu"),

    LangData(["en"], "en", ""),

    LangData(["jp", "japan", "ja", "j"], "jp", "jp"),

    LangData(["br", "brazil"], "br", "br"),
    LangData(["ru", "r"], "ru", "ru"),
    LangData(["kr", "korea", "k"], "kr", "kr"),
    LangData(["cn", "china", "hong", "kong", "ch", "hk", "as", "tw"], "cn", "cn"),

    LangData(["canada", "ca", "c", "fc"], "fr", "wr"),

    LangData(["in", "ìndia"], "in", "in"),
]


def _find_lang_data(token: str) -> Optional[LangData]:
    """Looks up a token (e.g. 'usa', 'fr', 'spain') in the LANG_DATA alias table."""
    token = token.strip().lower()
    for entry in LANG_DATA:
        if token in entry.aliases:
            return entry
    return None


def _raw_locale_token() -> str:
    """
    Reads the raw system locale token, before any normalization.
    Priority order: LANGUAGE > LC_ALL > LANG > locale.getlocale() > 'en'
    """
    for var in ("LANGUAGE", "LC_ALL", "LANG"):
        val = os.environ.get(var, "").strip()
        if val and val not in ("C", "POSIX"):
            # LANGUAGE can be "es_ES:en_US:…" — take the first one
            token = val.split(":")[0]
            # Strip encoding suffix if present (.UTF-8, etc.)
            token = token.split(".")[0]
            if len(token) >= 2:
                return token

    # Fallback: system locale
    try:
        code, _ = locale.getlocale()
        if code:
            return code
    except Exception:
        pass

    return "en_US"


def _detect_language(with_region: bool = False):
    """
    Detects the current system language and normalizes it to Batocera format
    ('es', 'en', 'fr', 'de', ...), using the same alias table as EmulationStation.

    If with_region is True, returns a tuple (lang, region), e.g. ('en', 'us').
    Otherwise returns just the lang code as a string.
    """
    raw = _raw_locale_token()
    # Take only the language part (before '_' or '-'), e.g. "es_ES" -> "es"
    lang_part = raw.replace("-", "_").split("_")[0].lower()

    entry = _find_lang_data(lang_part)
    if entry is None:
        # Unknown alias: fall back to the raw language code itself
        lang = lang_part if lang_part else "en"
        region = ""
    else:
        # Some entries (e.g. "europe") have no lang, only a region
        lang = entry.lang if entry.lang else lang_part
        region = entry.region

    if with_region:
        return lang, region
    return lang