"""Форматування виводу для CLI.

Таблиці потрібні контактам, нотаткам і задачам однаково, тому код живе тут,
а не в теці однієї з фіч.
"""

import unicodedata
from collections.abc import Iterable, Sequence

#: Чим позначаємо незаповнене поле у виводі.
EMPTY = "—"

#: Українська абетка в правильному порядку.
UKRAINIAN_ALPHABET = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"
_UKRAINIAN_ORDER = {char: index for index, char in enumerate(UKRAINIAN_ALPHABET)}

# Групи символів визначають порядок між різними абетками. Пробіли й розділові
# знаки — першими, щоб «Іван Петренко» стояв перед «Іванна».
_GROUP_PUNCTUATION = 0
_GROUP_DIGIT = 1
_GROUP_UKRAINIAN = 2
_GROUP_OTHER_CYRILLIC = 3
_GROUP_LATIN = 4
_GROUP_OTHER_LETTER = 5

# Літери з рискою не мають канонічного розкладу в Unicode, тому base-літеру
# для них доводиться задавати вручну.
_LATIN_STROKE = {
    "ł": "l",
    "đ": "d",
    "ø": "o",
    "ħ": "h",
    "ŧ": "t",
    "ı": "i",
    "ß": "s",
    "æ": "a",
    "œ": "o",
    "þ": "t",
    "ð": "d",
}

#: Результат `collation_key` — щоб анотації не повторювали вкладені кортежі.
type CollationKey = tuple[tuple[int, int, int], ...]

#: Символи, які в терміналі займають дві позиції (емодзі, ієрогліфи).
_WIDE_WIDTHS = frozenset({"W", "F"})


def collapse_whitespace(text: str) -> str:
    """Зводить будь-які пробільні символи до одинарних пробілів.

    Ім'я з `\n` всередині приходить не з клавіатури, а з імпортованого CSV
    чи JSON — і ламає верстку таблиць. Нормалізуємо, а не відхиляємо: втрачати
    через це весь запис було б надто суворо.
    """
    return " ".join(text.split())


def display_width(text: str) -> int:
    """Скільки позицій рядок займе в моноширинному терміналі.

    `len` тут не годиться: емодзі та ієрогліфи займають дві позиції, а
    діакритичні знаки, що комбінуються, — жодної.
    """
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in _WIDE_WIDTHS else 1
    return width


def collation_key(text: str) -> CollationKey:
    """Ключ сортування за українською абеткою.

    Стандартне порівняння рядків впорядковує за кодами Unicode, а `і`, `ї`,
    `є` та `ґ` лежать поза основним кириличним блоком. Через це `Іван`
    опинявся після `Марії`. `locale.strxfrm` тут не підходить: він вимагає
    встановленої в системі локалі `uk_UA`, якої на машині колеги може не бути.
    """
    return tuple(_char_key(char) for char in text.casefold())


def _char_key(char: str) -> tuple[int, int, int]:
    """Ключ одного символу: (група абетки, базова літера, сам символ).

    Третій елемент розводить `e` і `é`, залишаючи їх сусідами: без нього
    `José` та `Jose` вважались би однаковими.
    """
    position = _UKRAINIAN_ORDER.get(char)
    if position is not None:
        return _GROUP_UKRAINIAN, position, 0
    if char.isdigit():
        return _GROUP_DIGIT, ord(char), 0
    if not char.isalpha():
        return _GROUP_PUNCTUATION, ord(char), 0
    if _is_cyrillic(char):
        return _GROUP_OTHER_CYRILLIC, ord(char), 0

    base = _latin_base(char)
    if base is not None:
        return _GROUP_LATIN, ord(base), ord(char)
    return _GROUP_OTHER_LETTER, ord(char), 0


def _is_cyrillic(char: str) -> bool:
    return "CYRILLIC" in unicodedata.name(char, "")


def _latin_base(char: str) -> str | None:
    """Латинська літера без діакритики: `ö` -> `o`, `ł` -> `l`."""
    first = unicodedata.normalize("NFKD", char)[0]
    if first.isascii() and first.isalpha():
        return first
    return _LATIN_STROKE.get(char)


def value_or_dash(value: object) -> str:
    """Рядкове представлення значення; порожнє — як прочерк."""
    if value is None:
        return EMPTY
    text = str(value).strip()
    return text or EMPTY


def format_table(rows: Sequence[Sequence[str]], headers: Sequence[str] | None = None) -> str:
    """Вирівнює комірки в колонки.

    Ширина рахується через `display_width`, бо емодзі та ієрогліфи займають
    дві позиції — інакше рядок з ними зсуває всю колонку праворуч.
    """
    if not rows:
        return ""

    body = [list(map(str, row)) for row in rows]
    columns = max(len(row) for row in body)
    if headers:
        columns = max(columns, len(headers))

    for row in body:
        row.extend([""] * (columns - len(row)))

    widths = [0] * columns
    header_row = list(headers) + [""] * (columns - len(headers)) if headers else None
    for row in [header_row, *body] if header_row else body:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], display_width(cell))

    lines: list[str] = []
    if header_row:
        lines.append(_render_row(header_row, widths))
        lines.append("  ".join("─" * width for width in widths))
    lines.extend(_render_row(row, widths) for row in body)
    return "\n".join(lines)


def _render_row(row: Sequence[str], widths: Sequence[int]) -> str:
    # Останню колонку не доповнюємо пробілами — інакше рядок тягне хвіст.
    cells = [
        cell + " " * max(0, width - display_width(cell))
        for cell, width in zip(row[:-1], widths[:-1], strict=False)
    ]
    cells.append(row[-1])
    return "  ".join(cells).rstrip()


def join_or_dash(values: Iterable[str], separator: str = ", ") -> str:
    """З'єднує значення або повертає прочерк для порожньої послідовності."""
    joined = separator.join(values)
    return joined or EMPTY


def pluralise(count: int, one: str, few: str, many: str) -> str:
    """Українська форма множини: 1 день, 2 дні, 5 днів."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return few
    return many
