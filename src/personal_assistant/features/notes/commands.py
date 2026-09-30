"""CLI-команди нотаток."""

from typing import TYPE_CHECKING

from personal_assistant.cli.registry import Argument, Registry
from personal_assistant.core.errors import PersonalAssistantError
from personal_assistant.core.text import EMPTY, format_table, join_or_dash, pluralise
from personal_assistant.features.notes import service
from personal_assistant.features.notes.models import Note

if TYPE_CHECKING:
    from personal_assistant.context import AppContext

GROUP = "Нотатки"

#: Скільки символів тексту показувати у списку.
PREVIEW_LENGTH = 40


def register(registry: Registry) -> None:
    """Підключає команди нотаток до реєстру."""
    registry.add(
        "add note",
        _add_note,
        summary="Створити нотатку",
        group=GROUP,
        usage="<заголовок> [текст]",
        min_args=1,
        arguments=(Argument("<заголовок>"), Argument("[текст]")),
    )
    registry.add(
        "list notes",
        _list_notes,
        summary="Показати всі нотатки (найсвіжіші згори)",
        group=GROUP,
        aliases=("notes",),
    )
    registry.add(
        "show note",
        _show_note,
        summary="Показати нотатку повністю",
        group=GROUP,
        usage="<нотатка>",
        min_args=1,
        arguments=(Argument("<нотатка>", values=_note_values),),
    )
    registry.add(
        "edit note",
        _edit_note,
        summary="Замінити текст нотатки",
        group=GROUP,
        usage="<нотатка> <текст>",
        min_args=2,
        arguments=(Argument("<нотатка>", values=_note_values), Argument("<текст>")),
    )
    registry.add(
        "rename note",
        _rename_note,
        summary="Змінити заголовок нотатки",
        group=GROUP,
        usage="<нотатка> <новий заголовок>",
        min_args=2,
        arguments=(Argument("<нотатка>", values=_note_values), Argument("<новий заголовок>")),
    )
    registry.add(
        "delete note",
        _delete_note,
        summary="Видалити нотатку",
        group=GROUP,
        usage="<нотатка>",
        min_args=1,
        arguments=(Argument("<нотатка>", values=_note_values),),
    )
    registry.add(
        "find notes",
        _find_notes,
        summary="Пошук за заголовком, текстом і тегами",
        group=GROUP,
        usage="<запит>",
        min_args=1,
        arguments=(Argument("<запит>"),),
    )
    registry.add(
        "add tag",
        _add_tag,
        summary="Додати тег до нотатки",
        group=GROUP,
        usage="<нотатка> <тег>",
        min_args=2,
        arguments=(
            Argument("<нотатка>", values=_note_values),
            Argument("<тег>", values=_all_tag_values),
        ),
    )
    registry.add(
        "remove tag",
        _remove_tag,
        summary="Прибрати тег з нотатки",
        group=GROUP,
        usage="<нотатка> <тег>",
        min_args=2,
        arguments=(
            Argument("<нотатка>", values=_note_values),
            Argument("<тег>", values=_note_tag_values),
        ),
    )
    registry.add(
        "notes by tag",
        _notes_by_tag,
        summary="Нотатки з указаним тегом",
        group=GROUP,
        usage="<тег>",
        min_args=1,
        arguments=(Argument("<тег>", values=_all_tag_values),),
    )
    registry.add(
        "sort notes",
        _sort_notes,
        summary="Показати нотатки, згруповані за тегами",
        group=GROUP,
    )
    registry.add(
        "list tags",
        _list_tags,
        summary="Усі теги з кількістю нотаток",
        group=GROUP,
        aliases=("tags",),
    )


# ----------------------------------------------- джерела для автодоповнення


def _note_values(ctx: "AppContext", _args: list[str]) -> list[str]:
    return [note.title for note in service.listing(ctx.notes)]


def _all_tag_values(ctx: "AppContext", _args: list[str]) -> list[str]:
    return [tag for tag, _ in service.tag_counts(ctx.notes)]


def _note_tag_values(ctx: "AppContext", args: list[str]) -> list[str]:
    """Теги саме тієї нотатки, яку вже вказали першим аргументом."""
    if not args:
        return []
    try:
        return service.resolve(ctx.notes, args[0]).tags
    except PersonalAssistantError:
        return []


# --------------------------------------------------------------- обробники


def _add_note(ctx: "AppContext", args: list[str]) -> str:
    title, *rest = args
    note = service.create(ctx.notes, title, " ".join(rest))
    return f"Нотатку '{note.title}' створено [{note.short_id}]."


def _list_notes(ctx: "AppContext", _args: list[str]) -> str:
    notes = service.listing(ctx.notes)
    if not notes:
        return "Нотаток ще немає. Створи першу: add note <заголовок> [текст]"
    return _notes_table(notes)


def _show_note(ctx: "AppContext", args: list[str]) -> str:
    note = service.resolve(ctx.notes, " ".join(args))
    return _note_details(note)


def _edit_note(ctx: "AppContext", args: list[str]) -> str:
    reference, *rest = args
    note = service.resolve(ctx.notes, reference)
    service.edit(note, " ".join(rest))
    return f"Текст нотатки '{note.title}' оновлено."


def _rename_note(ctx: "AppContext", args: list[str]) -> str:
    reference, *rest = args
    note = service.resolve(ctx.notes, reference)
    old_title = note.title
    service.rename(note, " ".join(rest))
    return f"Нотатку '{old_title}' перейменовано на '{note.title}'."


def _delete_note(ctx: "AppContext", args: list[str]) -> str:
    note = service.delete(ctx.notes, " ".join(args))
    return f"Нотатку '{note.title}' видалено."


def _find_notes(ctx: "AppContext", args: list[str]) -> str:
    query = " ".join(args)
    found = service.search(ctx.notes, query)
    if not found:
        return f"За запитом '{query}' нічого не знайдено."
    return _notes_table(found)


def _add_tag(ctx: "AppContext", args: list[str]) -> str:
    reference, *rest = args
    note = service.resolve(ctx.notes, reference)
    tag = service.add_tag(note, " ".join(rest))
    return f"Нотатці '{note.title}' додано тег #{tag}."


def _remove_tag(ctx: "AppContext", args: list[str]) -> str:
    reference, *rest = args
    note = service.resolve(ctx.notes, reference)
    tag = service.remove_tag(note, " ".join(rest))
    return f"У нотатки '{note.title}' прибрано тег #{tag}."


def _notes_by_tag(ctx: "AppContext", args: list[str]) -> str:
    tag = " ".join(args)
    found = service.by_tag(ctx.notes, tag)
    if not found:
        return f"Нотаток з тегом #{tag} немає."
    return _notes_table(found)


def _sort_notes(ctx: "AppContext", _args: list[str]) -> str:
    notes = service.sorted_by_tag(ctx.notes)
    if not notes:
        return "Нотаток ще немає."
    return _notes_table(notes)


def _list_tags(ctx: "AppContext", _args: list[str]) -> str:
    counts = service.tag_counts(ctx.notes)
    if not counts:
        return "Тегів ще немає. Додай перший: add tag <нотатка> <тег>"

    rows = [
        [f"#{tag}", f"{count} {pluralise(count, 'нотатка', 'нотатки', 'нотаток')}"]
        for tag, count in counts
    ]
    return format_table(rows, headers=["Тег", "Скільки"])


# ------------------------------------------------------------------ службове


def _preview(text: str) -> str:
    """Перший рядок тексту, обрізаний до довжини колонки."""
    if not text:
        return EMPTY
    if len(text) <= PREVIEW_LENGTH:
        return text
    return text[: PREVIEW_LENGTH - 1].rstrip() + "…"


def _notes_table(notes: list[Note]) -> str:
    rows = [
        [
            note.short_id,
            note.title,
            join_or_dash(f"#{tag}" for tag in note.tags),
            _preview(note.text),
        ]
        for note in notes
    ]
    return format_table(rows, headers=["ID", "Заголовок", "Теги", "Текст"])


def _note_details(note: Note) -> str:
    header = format_table(
        [
            ["Теги:", join_or_dash(f"#{tag}" for tag in note.tags)],
            ["Ідентифікатор:", note.short_id],
        ]
    )
    body = "\n".join(f"  {line}" for line in header.splitlines())
    text = note.text or EMPTY
    return f"{note.title}\n{body}\n\n{text}"
