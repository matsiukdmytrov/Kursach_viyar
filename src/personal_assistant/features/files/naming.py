"""Транслітерація та нормалізація імен файлів.

Таблиця й підхід перенесені з навчальної роботи `HM1_Nasukha.py`. Змін дві:
повторні підкреслення тепер згортаються (інакше `Мій файл (1).jpg`
перетворювався на `Mii_fail__1_`), а складені розширення на кшталт `.tar.gz`
зберігаються цілими.
"""

import re
from pathlib import Path

#: Українська кирилиця -> латиниця. Для великих літер результат капіталізується.
TRANSLITERATION = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "h",
    "ґ": "g",
    "д": "d",
    "е": "e",
    "є": "ie",
    "ж": "zh",
    "з": "z",
    "и": "y",
    "і": "i",
    "ї": "yi",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ь": "",
    "ю": "iu",
    "я": "ia",
}

#: Розширення, які треба зберігати цілими, а не лише останню частину.
COMPOUND_SUFFIXES = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst")

#: Чим замінюємо ім'я, від якого після нормалізації нічого не лишилось.
FALLBACK_STEM = "file"

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def transliterate(text: str) -> str:
    """Замінює українські літери латиницею, решту символів лишає як є."""
    result: list[str] = []
    for char in text:
        replacement = TRANSLITERATION.get(char.lower())
        if replacement is None:
            result.append(char)
        elif char.isupper():
            result.append(replacement.capitalize())
        else:
            result.append(replacement)
    return "".join(result)


def normalize_stem(stem: str) -> str:
    """Зводить ім'я без розширення до латиниці, цифр і підкреслень."""
    normalized = _NON_ALNUM.sub("_", transliterate(stem)).strip("_")
    return normalized or FALLBACK_STEM


def split_name(filename: str) -> tuple[str, str]:
    """Ділить ім'я на основу й розширення, не розриваючи `.tar.gz`."""
    lowered = filename.lower()
    for compound in COMPOUND_SUFFIXES:
        if lowered.endswith(compound) and len(filename) > len(compound):
            return filename[: -len(compound)], filename[-len(compound) :]

    path = Path(filename)
    return path.stem, path.suffix


def normalize_filename(filename: str) -> str:
    """Нормалізує ім'я файлу, зберігаючи розширення (у нижньому регістрі)."""
    stem, suffix = split_name(filename)
    return f"{normalize_stem(stem)}{suffix.lower()}"
