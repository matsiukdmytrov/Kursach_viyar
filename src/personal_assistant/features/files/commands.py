"""CLI-команди роботи з файлами.

Усі три команди показують попередній перегляд і **нічого не змінюють на
диску**. Це видно з тексту кожної відповіді — користувач має розуміти, що
операція ще не виконана.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from personal_assistant.cli.registry import Argument, Registry
from personal_assistant.core.text import format_table, pluralise
from personal_assistant.features.files import service
from personal_assistant.features.files.service import DuplicateGroup, PlannedMove, ScanResult

if TYPE_CHECKING:
    from personal_assistant.context import AppContext

GROUP = "Файли"

#: Скільки рядків показувати, перш ніж згорнути решту.
MAX_ROWS = 40

DRY_RUN_NOTE = "Це попередній перегляд — на диску нічого не змінено."


def register(registry: Registry) -> None:
    """Підключає команди роботи з файлами до реєстру."""
    registry.add(
        "sort files",
        _sort_files,
        summary="Показати, як розклалися б файли теки за категоріями",
        group=GROUP,
        usage="<тека>",
        min_args=1,
        arguments=(Argument("<тека>", path=True),),
    )
    registry.add(
        "normalize names",
        _normalize_names,
        summary="Показати, які імена файлів змінилися б після транслітерації",
        group=GROUP,
        usage="<тека>",
        min_args=1,
        arguments=(Argument("<тека>", path=True),),
    )
    registry.add(
        "find duplicates",
        _find_duplicates,
        summary="Знайти файли з однаковим вмістом (за SHA-256)",
        group=GROUP,
        usage="<тека>",
        min_args=1,
        arguments=(Argument("<тека>", path=True),),
    )


# --------------------------------------------------------------- обробники


def _sort_files(_ctx: "AppContext", args: list[str]) -> str:
    root = service.resolve_directory(" ".join(args))
    moves, scanned = service.plan_sort(root)

    if not moves:
        return f"У теці {root} немає файлів для сортування.{_scan_note(scanned)}"

    sections: list[str] = []
    for category in service.iter_categories():
        in_category = [move for move in moves if move.category == category]
        if not in_category:
            continue
        sections.append(f"{category}/  ({len(in_category)})")
        sections.append(_moves_table(in_category, root))
        sections.append("")

    summary = _plural_files(len(moves))
    renamed = sum(1 for move in moves if move.renamed)
    collisions = sum(1 for move in moves if move.collision)

    footer = [f"Разом: {summary}, з них перейменовано {renamed}."]
    if collisions:
        footer.append(_collision_note(collisions))
    footer.append(_scan_note(scanned).strip())
    footer.append(DRY_RUN_NOTE)

    return "\n".join([*sections, *(line for line in footer if line)])


def _normalize_names(_ctx: "AppContext", args: list[str]) -> str:
    root = service.resolve_directory(" ".join(args))
    renames, scanned = service.plan_normalize(root)

    if not renames:
        return f"Усі імена у теці {root} вже нормалізовані.{_scan_note(scanned)}"

    shown, hidden = _limit(renames)
    rows = [
        [_relative(item.source, root), "→", item.target.name + (" ⚠" if item.collision else "")]
        for item in shown
    ]

    lines = [format_table(rows, headers=["Зараз", "", "Стане"])]
    if hidden:
        lines.append(f"…і ще {hidden}.")

    collisions = sum(1 for item in renames if item.collision)
    lines.append(f"Разом: {_plural_files(len(renames))} до перейменування.")
    if collisions:
        lines.append(_collision_note(collisions))
    lines.append(_scan_note(scanned).strip())
    lines.append(DRY_RUN_NOTE)

    return "\n".join(line for line in lines if line)


def _find_duplicates(_ctx: "AppContext", args: list[str]) -> str:
    root = service.resolve_directory(" ".join(args))
    groups, scanned = service.find_duplicates(root)

    if not groups:
        return f"Дублікатів у теці {root} не знайдено.{_scan_note(scanned)}"

    shown, hidden = _limit(groups)
    sections = [_group_section(group, root) for group in shown]
    if hidden:
        sections.append(f"…і ще {hidden} {pluralise(hidden, 'група', 'групи', 'груп')}.")

    wasted = sum(group.wasted_bytes for group in groups)
    extra = sum(len(group.files) - 1 for group in groups)
    sections.append(
        f"Разом: {len(groups)} {pluralise(len(groups), 'група', 'групи', 'груп')}, "
        f"зайвих копій — {extra}, місця займають {_human_size(wasted)}."
    )
    sections.append(_scan_note(scanned).strip())
    sections.append("Нічого не видалено — це лише звіт.")

    return "\n".join(line for line in sections if line)


# ------------------------------------------------------------------ службове


def _limit[ItemT](items: list[ItemT]) -> tuple[list[ItemT], int]:
    """Обрізає довгий список, повертаючи показане й кількість прихованого."""
    if len(items) <= MAX_ROWS:
        return items, 0
    return items[:MAX_ROWS], len(items) - MAX_ROWS


def _relative(path: Path, root: Path) -> str:
    """Шлях відносно кореня — абсолютні шляхи в таблиці нечитабельні."""
    try:
        return str(path.relative_to(root))
    except ValueError:  # pragma: no cover - шлях завжди всередині кореня
        return str(path)


def _moves_table(moves: list[PlannedMove], root: Path) -> str:
    shown, hidden = _limit(moves)
    rows = [
        [
            _relative(move.source, root),
            "→",
            move.target.name + (" ⚠" if move.collision else ""),
        ]
        for move in shown
    ]
    table = format_table(rows)
    return f"{table}\n  …і ще {hidden}." if hidden else table


def _group_section(group: DuplicateGroup, root: Path) -> str:
    header = (
        f"{_human_size(group.size)} × {len(group.files)} "
        f"(зайве: {_human_size(group.wasted_bytes)})  [{group.digest[:12]}]"
    )
    files = "\n".join(f"  {_relative(path, root)}" for path in group.files)
    return f"{header}\n{files}\n"


def _collision_note(count: int) -> str:
    return (
        f"⚠ {count} {pluralise(count, 'ім’я збіглося', 'імені збіглися', 'імен збіглися')} "
        "з іншим файлом — до таких додано числовий суфікс."
    )


def _scan_note(scanned: ScanResult) -> str:
    parts: list[str] = []
    if scanned.hidden_count:
        parts.append(f"приховані пропущено: {scanned.hidden_count}")
    if scanned.skipped_sorted:
        parts.append(f"вже розсортованих тек пропущено: {scanned.skipped_sorted}")
    if scanned.unreadable:
        parts.append(f"не вдалося прочитати: {len(scanned.unreadable)}")
    return f"\n({'; '.join(parts)})" if parts else ""


def _plural_files(count: int) -> str:
    return f"{count} {pluralise(count, 'файл', 'файли', 'файлів')}"


def _human_size(size: int) -> str:
    """Розмір у зручних одиницях."""
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            precision = 0 if unit == "Б" else 1
            return f"{value:.{precision}f} {unit}"
        value /= 1024
    return f"{value:.1f} ГБ"  # pragma: no cover
