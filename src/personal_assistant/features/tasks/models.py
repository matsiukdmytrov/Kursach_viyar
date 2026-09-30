"""Модель задачі та її статуси."""

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from personal_assistant.core.dates import coerce_date
from personal_assistant.core.entity import Entity
from personal_assistant.core.errors import ValidationError
from personal_assistant.core.text import collapse_whitespace

#: Межа довжини заголовка — як і в нотатках, заради верстки списку.
MAX_TITLE_LENGTH = 120


class TaskStatus(StrEnum):
    """Статуси із технічного завдання.

    `StrEnum` обрано свідомо: значення дорівнює рядку, тому воно потрапляє в
    JSON як `"in_progress"` без жодного перетворення, а порівняння зі рядком
    з CLI працює напряму.
    """

    NEW = "new"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"

    @classmethod
    def parse(cls, value: str) -> "TaskStatus":
        """Розбирає статус, введений користувачем.

        Приймає і канонічне значення з ТЗ (`in_progress`), і його звичні
        варіанти написання (`in-progress`, `IN PROGRESS`), і український
        відповідник (`в роботі`) — той самий, що застосунок показує в таблиці.
        Незручно бачити «в роботі», а мусити вводити `in_progress`.
        """
        normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")

        synonym = _STATUS_SYNONYMS.get(normalized)
        if synonym is not None:
            return synonym

        try:
            return cls(normalized)
        except ValueError as exc:
            allowed = ", ".join(status.value for status in cls)
            raise ValidationError(f"Невідомий статус '{value}'. Доступні: {allowed}.") from exc

    @property
    def label(self) -> str:
        """Українська назва для виводу."""
        return _STATUS_LABELS[self]

    @property
    def is_open(self) -> bool:
        """Чи задача ще в роботі."""
        return self in {TaskStatus.NEW, TaskStatus.IN_PROGRESS}


#: Що показуємо користувачеві замість канонічного значення.
_STATUS_LABELS = {
    TaskStatus.NEW: "нова",
    TaskStatus.IN_PROGRESS: "в роботі",
    TaskStatus.DONE: "виконано",
    TaskStatus.CANCELLED: "скасовано",
}

#: Що приймаємо на вводі додатково до канонічних значень.
_STATUS_SYNONYMS = {
    "нова": TaskStatus.NEW,
    "нове": TaskStatus.NEW,
    "todo": TaskStatus.NEW,
    "в_роботі": TaskStatus.IN_PROGRESS,
    "вроботі": TaskStatus.IN_PROGRESS,
    "робота": TaskStatus.IN_PROGRESS,
    "progress": TaskStatus.IN_PROGRESS,
    "виконано": TaskStatus.DONE,
    "готово": TaskStatus.DONE,
    "зроблено": TaskStatus.DONE,
    "скасовано": TaskStatus.CANCELLED,
    "відмінено": TaskStatus.CANCELLED,
}


class Task(Entity):
    """Запис у списку задач."""

    title: str = Field(
        min_length=1, max_length=MAX_TITLE_LENGTH, description="Короткий опис задачі"
    )
    description: str = ""
    status: TaskStatus = TaskStatus.NEW
    due_date: date | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _clean_title(cls, value: Any) -> Any:
        return collapse_whitespace(value) if isinstance(value, str) else value

    @field_validator("status", mode="before")
    @classmethod
    def _accept_loose_status(cls, value: Any) -> Any:
        return TaskStatus.parse(value) if isinstance(value, str) else value

    @field_validator("due_date", mode="before")
    @classmethod
    def _accept_dd_mm_yyyy(cls, value: Any) -> Any:
        if isinstance(value, str):
            return coerce_date(value) if value.strip() else None
        return value

    # -------------------------------------------------------------- поведінка

    def set_status(self, status: TaskStatus | str) -> bool:
        """Змінює статус. Повертає False, якщо він і так був таким."""
        new_status = TaskStatus.parse(status) if isinstance(status, str) else status
        if new_status is self.status:
            return False
        self.status = new_status
        self.touch()
        return True

    def is_overdue(self, today: date | None = None) -> bool:
        """Чи прострочена задача (закриті задачі простроченими не вважаються)."""
        if self.due_date is None or not self.status.is_open:
            return False
        return self.due_date < (today or date.today())

    def matches(self, query: str) -> bool:
        """Чи згадується `query` в заголовку або описі."""
        needle = query.strip().casefold()
        if not needle:
            return False
        return needle in self.title.casefold() or needle in self.description.casefold()
