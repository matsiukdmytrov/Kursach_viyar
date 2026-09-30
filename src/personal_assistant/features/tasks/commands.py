"""CLI-команди ToDo-менеджера."""

from typing import TYPE_CHECKING

from personal_assistant.cli.registry import Argument, Registry
from personal_assistant.core.dates import DATE_FORMAT_HINT, format_date
from personal_assistant.core.text import EMPTY, format_table, pluralise, value_or_dash
from personal_assistant.features.tasks import service
from personal_assistant.features.tasks.models import Task, TaskStatus

if TYPE_CHECKING:
    from personal_assistant.context import AppContext

GROUP = "Задачі"

#: Скільки символів опису показувати у списку.
PREVIEW_LENGTH = 30

#: Позначка простроченої задачі.
OVERDUE_MARK = "!"

_STATUS_LIST = " | ".join(status.value for status in TaskStatus)


def register(registry: Registry) -> None:
    """Підключає команди задач до реєстру."""
    registry.add(
        "add task",
        _add_task,
        summary="Створити задачу",
        group=GROUP,
        usage="<заголовок> [опис]",
        min_args=1,
        arguments=(Argument("<заголовок>"), Argument("[опис]")),
    )
    registry.add(
        "list tasks",
        _list_tasks,
        summary="Показати задачі, за потреби лише вказаного статусу",
        group=GROUP,
        usage="[статус]",
        aliases=("tasks",),
        arguments=(Argument("[статус]", values=_status_values),),
    )
    registry.add(
        "show task",
        _show_task,
        summary="Показати задачу повністю",
        group=GROUP,
        usage="<задача>",
        min_args=1,
        arguments=(Argument("<задача>", values=_task_values),),
    )
    registry.add(
        "edit task",
        _edit_task,
        summary="Замінити опис задачі",
        group=GROUP,
        usage="<задача> <опис>",
        min_args=2,
        arguments=(Argument("<задача>", values=_task_values), Argument("<опис>")),
    )
    registry.add(
        "rename task",
        _rename_task,
        summary="Змінити заголовок задачі",
        group=GROUP,
        usage="<задача> <новий заголовок>",
        min_args=2,
        arguments=(Argument("<задача>", values=_task_values), Argument("<новий заголовок>")),
    )
    registry.add(
        "delete task",
        _delete_task,
        summary="Видалити задачу",
        group=GROUP,
        usage="<задача>",
        min_args=1,
        arguments=(Argument("<задача>", values=_task_values),),
    )
    registry.add(
        "find tasks",
        _find_tasks,
        summary="Пошук за заголовком і описом",
        group=GROUP,
        usage="<запит>",
        min_args=1,
        arguments=(Argument("<запит>"),),
    )
    registry.add(
        "set status",
        _set_status,
        summary=f"Змінити статус ({_STATUS_LIST})",
        group=GROUP,
        usage="<задача> <статус>",
        min_args=2,
        arguments=(
            Argument("<задача>", values=_task_values),
            Argument("<статус>", values=_status_values),
        ),
    )
    registry.add(
        "set due",
        _set_due,
        summary=f"Записати дедлайн у форматі {DATE_FORMAT_HINT} (порожнє значення очищає)",
        group=GROUP,
        usage="<задача> [дата]",
        min_args=1,
        arguments=(Argument("<задача>", values=_task_values), Argument("[дата]")),
    )
    registry.add(
        "start",
        _start,
        summary="Перевести задачу в статус in_progress",
        group=GROUP,
        usage="<задача>",
        min_args=1,
        arguments=(Argument("<задача>", values=_task_values),),
    )
    registry.add(
        "done",
        _done,
        summary="Позначити задачу виконаною",
        group=GROUP,
        usage="<задача>",
        min_args=1,
        arguments=(Argument("<задача>", values=_task_values),),
    )
    registry.add(
        "cancel",
        _cancel,
        summary="Скасувати задачу",
        group=GROUP,
        usage="<задача>",
        min_args=1,
        arguments=(Argument("<задача>", values=_task_values),),
    )
    registry.add(
        "overdue",
        _overdue,
        summary="Задачі з простроченим дедлайном",
        group=GROUP,
    )


# ----------------------------------------------- джерела для автодоповнення


def _task_values(ctx: "AppContext", _args: list[str]) -> list[str]:
    return [task.title for task in service.listing(ctx.tasks)]


def _status_values(_ctx: "AppContext", _args: list[str]) -> list[str]:
    return [status.value for status in TaskStatus]


# --------------------------------------------------------------- обробники


def _add_task(ctx: "AppContext", args: list[str]) -> str:
    title, *rest = args
    task = service.create(ctx.tasks, title, " ".join(rest))
    return f"Задачу '{task.title}' створено [{task.short_id}]."


def _list_tasks(ctx: "AppContext", args: list[str]) -> str:
    status = TaskStatus.parse(" ".join(args)) if args else None
    tasks = service.listing(ctx.tasks, status)

    if not tasks:
        if status is not None:
            return f"Задач зі статусом '{status.value}' немає."
        return "Задач ще немає. Створи першу: add task <заголовок> [опис]"

    if status is not None:
        # Під відфільтрованим списком загальний підсумок читався б як опис
        # саме цієї вибірки — а він про всі задачі.
        return _tasks_table(tasks)

    return f"{_tasks_table(tasks)}\n\n{_summary(ctx)}"


def _show_task(ctx: "AppContext", args: list[str]) -> str:
    return _task_details(service.resolve(ctx.tasks, " ".join(args)))


def _edit_task(ctx: "AppContext", args: list[str]) -> str:
    reference, *rest = args
    task = service.resolve(ctx.tasks, reference)
    service.edit(task, " ".join(rest))
    return f"Опис задачі '{task.title}' оновлено."


def _rename_task(ctx: "AppContext", args: list[str]) -> str:
    reference, *rest = args
    task = service.resolve(ctx.tasks, reference)
    old_title = task.title
    service.rename(task, " ".join(rest))
    return f"Задачу '{old_title}' перейменовано на '{task.title}'."


def _delete_task(ctx: "AppContext", args: list[str]) -> str:
    task = service.delete(ctx.tasks, " ".join(args))
    return f"Задачу '{task.title}' видалено."


def _find_tasks(ctx: "AppContext", args: list[str]) -> str:
    query = " ".join(args)
    found = service.search(ctx.tasks, query)
    if not found:
        return f"За запитом '{query}' нічого не знайдено."
    return _tasks_table(found)


def _set_status(ctx: "AppContext", args: list[str]) -> str:
    reference, *rest = args
    task = service.resolve(ctx.tasks, reference)
    return _apply_status(task, " ".join(rest))


def _start(ctx: "AppContext", args: list[str]) -> str:
    return _shortcut(ctx, args, TaskStatus.IN_PROGRESS)


def _done(ctx: "AppContext", args: list[str]) -> str:
    return _shortcut(ctx, args, TaskStatus.DONE)


def _cancel(ctx: "AppContext", args: list[str]) -> str:
    return _shortcut(ctx, args, TaskStatus.CANCELLED)


def _set_due(ctx: "AppContext", args: list[str]) -> str:
    reference, *rest = args
    task = service.resolve(ctx.tasks, reference)
    value = " ".join(rest).strip()

    service.set_due_date(task, value or None)
    if task.due_date is None:
        return f"Дедлайн задачі '{task.title}' очищено."

    marker = " — вже прострочено" if task.is_overdue() else ""
    return f"Дедлайн задачі '{task.title}': {format_date(task.due_date)}{marker}."


def _overdue(ctx: "AppContext", _args: list[str]) -> str:
    tasks = service.overdue(ctx.tasks)
    if not tasks:
        return "Прострочених задач немає."
    return _tasks_table(tasks)


# ------------------------------------------------------------------ службове


def _shortcut(ctx: "AppContext", args: list[str], status: TaskStatus) -> str:
    task = service.resolve(ctx.tasks, " ".join(args))
    return _apply_status(task, status)


def _apply_status(task: Task, status: TaskStatus | str) -> str:
    if not service.set_status(task, status):
        return f"Задача '{task.title}' уже має статус '{task.status.value}'."
    return f"Задача '{task.title}': статус '{task.status.value}' ({task.status.label})."


def _summary(ctx: "AppContext") -> str:
    parts = [f"{status.label} — {count}" for status, count in service.status_counts(ctx.tasks)]
    total = len(ctx.tasks)
    word = pluralise(total, "задача", "задачі", "задач")
    return f"Усього {total} {word}: {', '.join(parts)}."


def _preview(text: str) -> str:
    if not text:
        return EMPTY
    if len(text) <= PREVIEW_LENGTH:
        return text
    return text[: PREVIEW_LENGTH - 1].rstrip() + "…"


def _due_cell(task: Task) -> str:
    if task.due_date is None:
        return EMPTY
    shown = format_date(task.due_date)
    return f"{OVERDUE_MARK} {shown}" if task.is_overdue() else f"  {shown}"


def _tasks_table(tasks: list[Task]) -> str:
    rows = [
        [
            task.short_id,
            task.status.label,
            task.title,
            _due_cell(task),
            _preview(task.description),
        ]
        for task in tasks
    ]
    return format_table(rows, headers=["ID", "Статус", "Заголовок", "Дедлайн", "Опис"])


def _task_details(task: Task) -> str:
    due = EMPTY
    if task.due_date is not None:
        due = format_date(task.due_date)
        if task.is_overdue():
            due += " (прострочено)"

    rows = [
        ["Статус:", f"{task.status.value} ({task.status.label})"],
        ["Дедлайн:", due],
        ["Ідентифікатор:", task.short_id],
    ]
    body = "\n".join(f"  {line}" for line in format_table(rows).splitlines())
    return f"{task.title}\n{body}\n\n{value_or_dash(task.description)}"
