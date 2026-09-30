"""JSON-сховище: читання та атомарний запис списку моделей.

Один файл — одна колекція. Запис іде через `atomic_write_bytes`, тому
перерваний процес не залишає обрізаний JSON.
"""

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from personal_assistant.core.errors import PersonalAssistantError, StorageError


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Записує файл через тимчасовий і `Path.replace`.

    Перерваний процес не залишає обрізаного файлу: на диску або старий вміст,
    або новий, третього стану немає.
    """
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(payload)
        tmp.replace(path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise StorageError(f"Не вдалося записати {path}: {exc}") from exc


class JsonStore[ModelT: BaseModel]:
    """Читає та пише `list[ModelT]` у JSON-файл.

    Параметризований типом моделі, тому одна реалізація обслуговує контакти,
    нотатки й задачі — жодна фіча не пише власний код серіалізації.
    """

    def __init__(self, path: Path, model: type[ModelT]) -> None:
        self.path = path
        self.model = model
        self._adapter: TypeAdapter[list[ModelT]] = TypeAdapter(list[model])  # type: ignore[valid-type]

    def load(self) -> list[ModelT]:
        """Повертає збережені записи; для відсутнього файлу — порожній список.

        Пошкоджений файл не ігнорується мовчки: краще зупинитись і сказати
        користувачеві, де лежить проблема, ніж стерти дані наступним записом.
        """
        if not self.path.exists():
            return []

        try:
            raw = self.path.read_bytes()
        except OSError as exc:
            raise StorageError(f"Не вдалося прочитати {self.path}: {exc}") from exc

        if not raw.strip():
            return []

        try:
            return self._adapter.validate_json(raw)
        except PersonalAssistantError as exc:
            # Файл цілий, але запис у ньому не проходить чинних правил —
            # наприклад, після того як правила стали суворішими. Причину тут
            # видно, і сказати її чесніше, ніж списати все на пошкодження.
            raise StorageError(
                f"Запис у файлі {self.path} не проходить перевірку.\n"
                f"{exc.message}\n"
                "Виправ або прибери цей запис у файлі."
            ) from exc
        except (PydanticValidationError, json.JSONDecodeError) as exc:
            # Технічні подробиці лишаються в ланцюжку винятків — користувачеві
            # від дампу pydantic користі немає, йому потрібен шлях і дія.
            raise StorageError(
                f"Файл даних пошкоджено: {self.path}. "
                "Перейменуй або видали його, щоб почати з чистого списку."
            ) from exc

    def save(self, items: Iterable[ModelT]) -> None:
        """Атомарно перезаписує файл переданими записами."""
        atomic_write_bytes(self.path, self._adapter.dump_json(list(items), indent=2))
