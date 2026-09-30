"""Бізнес-логіка нотаток.

На відміну від контактів, однакові заголовки тут дозволені: дві нотатки
«Зустріч» — це нормально, а ім'я контакту є способом адресації. Через це
кандидати в повідомленнях про неоднозначність показуються разом з
ідентифікатором, інакше перелік із двох однакових заголовків нічого не давав би.
"""

from collections import Counter
from collections.abc import Iterable

from personal_assistant.core.errors import ConflictError, NotFoundError, ValidationError
from personal_assistant.core.lookup import EntityNames, resolve_by_text
from personal_assistant.core.repository import Repository
from personal_assistant.core.text import CollationKey, collation_key
from personal_assistant.core.validation import assign, build
from personal_assistant.features.notes.models import Note, normalize_tag

#: Назви полів для повідомлень про помилки валідації.
FIELD_LABELS = {
    "title": "заголовок",
    "text": "текст",
    "tags": "теги",
}

#: Як звертатись до нотатки в повідомленнях про помилки пошуку.
NOTE_NAMES = EntityNames(
    accusative="Нотатку",
    plural_dative="нотаткам",
    hint="Уточни заголовок або вкажи ідентифікатор.",
)


# --------------------------------------------------------------------- пошук


def resolve(repo: Repository[Note], reference: str) -> Note:
    """Знаходить нотатку за заголовком, його частиною або ідентифікатором."""
    return resolve_by_text(
        repo,
        reference,
        text_of=lambda note: note.title,
        names=NOTE_NAMES,
        describe=lambda note: f"{note.title} [{note.short_id}]",
    )


def search(repo: Repository[Note], query: str) -> list[Note]:
    """Нотатки, у яких запит трапляється в заголовку, тексті або тегах."""
    if not query.strip():
        raise ValidationError("Порожній запит нічого не шукає.")
    return _recent_first(repo.find(lambda note: note.matches(query)))


def by_tag(repo: Repository[Note], tag: str) -> list[Note]:
    """Нотатки з указаним тегом."""
    normalized = normalize_tag(tag)
    return _recent_first(repo.find(lambda note: normalized in note.tags))


def listing(repo: Repository[Note]) -> list[Note]:
    """Усі нотатки, найсвіжіші згори."""
    return _recent_first(repo.all())


def sorted_by_tag(repo: Repository[Note]) -> list[Note]:
    """Усі нотатки, згруповані за першим тегом; нетеговані — у кінці."""
    return sorted(repo.all(), key=lambda note: note.sort_key)


def tag_counts(repo: Repository[Note]) -> list[tuple[str, int]]:
    """Усі теги з кількістю нотаток, за українською абеткою."""
    counter = Counter(tag for note in repo.all() for tag in note.tags)
    return sorted(counter.items(), key=lambda item: collation_key(item[0]))


# ------------------------------------------------------------------- зміни


def create(repo: Repository[Note], title: str, text: str = "", tags: Iterable[str] = ()) -> Note:
    """Створює нотатку."""
    clean_title = title.strip()
    if not clean_title:
        raise ValidationError("Заголовок нотатки не може бути порожнім.")

    note = build(Note, FIELD_LABELS, title=clean_title, text=text, tags=list(tags))
    return repo.add(note)


def edit(note: Note, text: str) -> None:
    """Замінює текст нотатки."""
    assign(note, "text", text, FIELD_LABELS)
    note.touch()


def rename(note: Note, new_title: str) -> None:
    """Змінює заголовок, зберігаючи ідентифікатор."""
    clean_title = new_title.strip()
    if not clean_title:
        raise ValidationError("Заголовок нотатки не може бути порожнім.")

    assign(note, "title", clean_title, FIELD_LABELS)
    note.touch()


def delete(repo: Repository[Note], reference: str) -> Note:
    """Видаляє нотатку і повертає видалений запис."""
    note = resolve(repo, reference)
    return repo.delete(note.id)


def add_tag(note: Note, tag: str) -> str:
    """Додає тег. Повертає його канонічний вигляд."""
    normalized = normalize_tag(tag)
    if not note.add_tag(normalized):
        raise ConflictError(f"Нотатка вже має тег #{normalized}.")
    return normalized


def remove_tag(note: Note, tag: str) -> str:
    """Прибирає тег. Повертає його канонічний вигляд."""
    normalized = normalize_tag(tag)
    if not note.remove_tag(normalized):
        raise NotFoundError(f"Нотатка не має тегу #{normalized}.")
    return normalized


# ------------------------------------------------------------------ службове


def _recent_first(notes: list[Note]) -> list[Note]:
    """Найсвіжіші згори, за однакового часу — за абеткою заголовків."""
    return sorted(notes, key=lambda note: (-note.updated_at.timestamp(), _by_title(note)))


def _by_title(note: Note) -> CollationKey:
    return collation_key(note.title)
