"""Композиційний корінь: збирає налаштування та репозиторії в один об'єкт.

Це єдине місце, яке знає одразу про всі фічі. Самі фічі одна про одну не
знають і спілкуються лише через `AppContext`, тому винести будь-яку з них в
окремий репозиторій — це прибрати один рядок звідси.
"""

from dataclasses import dataclass
from typing import Self

from personal_assistant.core.config import Settings, get_settings
from personal_assistant.core.repository import Repository
from personal_assistant.core.storage import JsonStore
from personal_assistant.features.contacts.models import Contact
from personal_assistant.features.notes.models import Note
from personal_assistant.features.tasks.models import Task


@dataclass(slots=True)
class AppContext:
    """Стан застосунку, який отримує кожен обробник команди."""

    settings: Settings
    contacts: Repository[Contact]
    notes: Repository[Note]
    tasks: Repository[Task]

    @classmethod
    def create(cls, settings: Settings | None = None) -> Self:
        """Читає всі файли даних і збирає контекст."""
        settings = settings or get_settings()
        return cls(
            settings=settings,
            contacts=Repository.from_store(JsonStore(settings.contacts_file, Contact)),
            notes=Repository.from_store(JsonStore(settings.notes_file, Note)),
            tasks=Repository.from_store(JsonStore(settings.tasks_file, Task)),
        )

    def save_all(self) -> None:
        """Скидає на диск усі колекції."""
        self.contacts.save()
        self.notes.save()
        self.tasks.save()
