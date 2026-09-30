"""Бізнес-логіка ToDo-менеджера.

Порядок у списку — головне рішення тут: спершу те, що ще в роботі, всередині
— за дедлайном. Список задач читають, щоб зрозуміти, чим зайнятись зараз, а
не щоб побачити хронологію створення.
"""

from collections import Counter
from datetime import date

from personal_assistant.core.dates import coerce_date
from personal_assistant.core.errors import ValidationError
from personal_assistant.core.lookup import EntityNames, resolve_by_text
from personal_assistant.core.repository import Repository
from personal_assistant.core.text import CollationKey, collation_key
from personal_assistant.core.validation import assign, build
from personal_assistant.features.tasks.models import Task, TaskStatus

#: Назви полів для повідомлень про помилки валідації.
FIELD_LABELS = {
    "title": "заголовок",
    "description": "опис",
    "status": "статус",
    "due_date": "дедлайн",
}

#: Як звертатись до задачі в повідомленнях про помилки пошуку.
TASK_NAMES = EntityNames(
    accusative="Задачу",
    plural_dative="задачам",
    hint="Уточни заголовок або вкажи ідентифікатор.",
)


# --------------------------------------------------------------------- пошук


def resolve(repo: Repository[Task], reference: str) -> Task:
    """Знаходить задачу за заголовком, його частиною або ідентифікатором."""
    return resolve_by_text(
        repo,
        reference,
        text_of=lambda task: task.title,
        names=TASK_NAMES,
        describe=lambda task: f"{task.title} [{task.short_id}]",
    )


def search(repo: Repository[Task], query: str) -> list[Task]:
    """Задачі, у яких запит трапляється в заголовку або описі."""
    if not query.strip():
        raise ValidationError("Порожній запит нічого не шукає.")
    return _ordered(repo.find(lambda task: task.matches(query)))


def listing(repo: Repository[Task], status: TaskStatus | None = None) -> list[Task]:
    """Усі задачі або лише задачі вказаного статусу."""
    if status is None:
        return _ordered(repo.all())
    return _ordered(repo.find(lambda task: task.status is status))


def overdue(repo: Repository[Task], today: date | None = None) -> list[Task]:
    """Задачі з простроченим дедлайном (закриті не рахуються)."""
    return _ordered(repo.find(lambda task: task.is_overdue(today)))


def status_counts(repo: Repository[Task]) -> list[tuple[TaskStatus, int]]:
    """Кількість задач у кожному статусі, у порядку оголошення статусів."""
    counter = Counter(task.status for task in repo.all())
    return [(status, counter[status]) for status in TaskStatus if counter[status]]


# ------------------------------------------------------------------- зміни


def create(
    repo: Repository[Task],
    title: str,
    description: str = "",
    due_date: str | None = None,
) -> Task:
    """Створює задачу зі статусом `new`."""
    clean_title = title.strip()
    if not clean_title:
        raise ValidationError("Заголовок задачі не може бути порожнім.")

    task = build(
        Task,
        FIELD_LABELS,
        title=clean_title,
        description=description,
        due_date=due_date,
    )
    return repo.add(task)


def edit(task: Task, description: str) -> None:
    """Замінює опис задачі."""
    assign(task, "description", description, FIELD_LABELS)
    task.touch()


def rename(task: Task, new_title: str) -> None:
    """Змінює заголовок, зберігаючи ідентифікатор."""
    clean_title = new_title.strip()
    if not clean_title:
        raise ValidationError("Заголовок задачі не може бути порожнім.")

    assign(task, "title", clean_title, FIELD_LABELS)
    task.touch()


def delete(repo: Repository[Task], reference: str) -> Task:
    """Видаляє задачу і повертає видалений запис."""
    task = resolve(repo, reference)
    return repo.delete(task.id)


def set_status(task: Task, status: TaskStatus | str) -> bool:
    """Змінює статус. Повертає False, якщо він і так був таким."""
    return task.set_status(status)


def set_due_date(task: Task, value: str | None) -> None:
    """Записує або очищає дедлайн."""
    assign(task, "due_date", coerce_date(value) if value else None, FIELD_LABELS)
    task.touch()


# ------------------------------------------------------------------ службове


def _ordered(tasks: list[Task]) -> list[Task]:
    """Незакриті згори, всередині — за дедлайном, потім за заголовком.

    Задачі без дедлайну опиняються в кінці своєї групи: `date.max` як
    заповнювач дає це безкоштовно, без окремого прапорця в ключі.
    """
    return sorted(
        tasks,
        key=lambda task: (
            not task.status.is_open,
            task.due_date or date.max,
            _by_title(task),
        ),
    )


def _by_title(task: Task) -> CollationKey:
    return collation_key(task.title)
