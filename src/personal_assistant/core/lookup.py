"""Пошук запису за тим, що набрав користувач.

Однакова потреба в контактів, нотаток і задач: людина вводить `Петренко`,
`Зустріч` або `3f2a1b8c` і очікує, що знайдеться саме те, що вона мала на
увазі. Логіка одна на всіх, різняться лише назви сутностей у повідомленнях.
"""

import string
from collections.abc import Callable
from dataclasses import dataclass

from personal_assistant.core.entity import Entity
from personal_assistant.core.errors import ConflictError, NotFoundError
from personal_assistant.core.repository import Repository

#: Мінімальна довжина рядка, який ще має сенс приймати за ідентифікатор.
ID_PREFIX_MIN_LENGTH = 4


@dataclass(frozen=True, slots=True)
class EntityNames:
    """Назви сутності у відмінках, потрібних для повідомлень про помилки.

    Українська вимагає різних форм у різних реченнях: «Контакт не знайдено»,
    але «Нотатку не знайдено». Один рядок тут не обійтися.
    """

    accusative: str
    """Знахідний відмінок: «Контакт», «Нотатку» — для «... не знайдено»."""

    plural_dative: str
    """Давальний множини: «контактам» — для «підходить кільком ...»."""

    hint: str
    """Що уточнити: «Уточни ім'я.», «Уточни заголовок.»"""


def resolve_by_text[EntityT: Entity](
    repo: Repository[EntityT],
    reference: str,
    *,
    text_of: Callable[[EntityT], str],
    names: EntityNames,
    describe: Callable[[EntityT], str] | None = None,
) -> EntityT:
    """Знаходить запис за текстовим полем або ідентифікатором.

    Порядок спроб — від точного до розпливчастого:

    1. повний збіг тексту;
    2. ідентифікатор або його початок;
    3. збіг з окремим словом — щоб `Іван` знаходив «Іван Петренко»,
       а не спотикався об «Іванна Шевченко»;
    4. входження підрядком.

    Неоднозначність на будь-якому рівні — це помилка з переліком кандидатів,
    а не мовчазний вибір першого-ліпшого. `describe` задає, як показати
    кандидата: для нотаток самих заголовків замало, бо вони можуть збігатись.
    """
    describe = describe or text_of
    needle = reference.strip()
    if not needle:
        raise NotFoundError("Не вказано, що саме шукати.")

    folded = needle.casefold()

    exact = repo.find(lambda entity: text_of(entity).casefold() == folded)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        # Точний збіг теж буває неоднозначним: дві нотатки цілком можуть
        # називатись однаково.
        raise _ambiguous(exact, reference, names, describe)

    if looks_like_id(needle):
        try:
            return repo.resolve(needle)
        except (NotFoundError, ConflictError):
            # Рядок лише скидався на ідентифікатор: «cafe» чи «Abba» цілком
            # можуть бути іменем. Пробуємо далі як текст.
            pass

    by_word = repo.find(lambda entity: folded in text_of(entity).casefold().split())
    if len(by_word) == 1:
        return by_word[0]

    candidates = by_word or repo.find(lambda entity: folded in text_of(entity).casefold())
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise _ambiguous(candidates, reference, names, describe)

    raise NotFoundError(f"{names.accusative} '{reference}' не знайдено.")


def _ambiguous[EntityT: Entity](
    candidates: list[EntityT],
    reference: str,
    names: EntityNames,
    describe: Callable[[EntityT], str],
) -> ConflictError:
    found = ", ".join(sorted(describe(entity) for entity in candidates))
    return ConflictError(
        f"'{reference}' підходить кільком {names.plural_dative}: {found}. {names.hint}"
    )


def looks_like_id(value: str) -> bool:
    """Чи схожий рядок на UUID або його початок."""
    stripped = value.replace("-", "")
    return len(stripped) >= ID_PREFIX_MIN_LENGTH and all(
        char in string.hexdigits for char in stripped
    )
