"""Колекція сутностей поверх `JsonStore`.

Тримає записи в пам'яті у `dict[UUID, Entity]` (порядок вставки зберігається)
і вміє скидати їх на диск. Уся робота фіч із даними йде через цей клас, тому
жодна фіча не знає, у якому саме форматі все лежить.
"""

from collections.abc import Callable, Iterator
from uuid import UUID

from personal_assistant.core.entity import Entity
from personal_assistant.core.errors import ConflictError, NotFoundError
from personal_assistant.core.storage import JsonStore


class Repository[EntityT: Entity]:
    """CRUD-операції над однією колекцією записів."""

    def __init__(self, store: JsonStore[EntityT], items: list[EntityT] | None = None) -> None:
        self._store = store
        self._items: dict[UUID, EntityT] = {item.id: item for item in items or []}

    @classmethod
    def from_store(cls, store: JsonStore[EntityT]) -> "Repository[EntityT]":
        """Створює репозиторій, одразу прочитавши файл."""
        return cls(store, store.load())

    # ------------------------------------------------------------------ read

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[EntityT]:
        return iter(self._items.values())

    def __contains__(self, entity_id: UUID) -> bool:
        return entity_id in self._items

    def all(self) -> list[EntityT]:
        """Усі записи в порядку додавання."""
        return list(self._items.values())

    def get(self, entity_id: UUID) -> EntityT | None:
        """Запис за ідентифікатором або None."""
        return self._items.get(entity_id)

    def require(self, entity_id: UUID) -> EntityT:
        """Запис за ідентифікатором; кидає `NotFoundError`, якщо його немає."""
        entity = self._items.get(entity_id)
        if entity is None:
            raise NotFoundError(f"Запис {entity_id} не знайдено.")
        return entity

    def find(self, predicate: Callable[[EntityT], bool]) -> list[EntityT]:
        """Усі записи, що задовольняють умову."""
        return [item for item in self._items.values() if predicate(item)]

    def resolve(self, reference: str) -> EntityT:
        """Знаходить запис за повним UUID або за коротким префіксом.

        Користувач у CLI набирає `delete note 3f2a1b8c`, а не весь UUID, тому
        префікс має бути повноцінним способом адресації. Неоднозначний
        префікс — це помилка, а не «візьмемо перший збіг».
        """
        reference = reference.strip().lower()
        if not reference:
            raise NotFoundError("Не вказано ідентифікатор запису.")

        matches = [item for item in self._items.values() if str(item.id).startswith(reference)]

        if not matches:
            raise NotFoundError(f"Запис з ідентифікатором '{reference}' не знайдено.")
        if len(matches) > 1:
            found = ", ".join(sorted(item.short_id for item in matches))
            raise ConflictError(
                f"Префікс '{reference}' підходить кільком записам: {found}. Уточни ідентифікатор."
            )
        return matches[0]

    # ----------------------------------------------------------------- write

    def add(self, entity: EntityT) -> EntityT:
        """Додає новий запис."""
        if entity.id in self._items:
            raise ConflictError(f"Запис {entity.short_id} вже існує.")
        self._items[entity.id] = entity
        return entity

    def delete(self, entity_id: UUID) -> EntityT:
        """Видаляє запис і повертає його."""
        entity = self._items.pop(entity_id, None)
        if entity is None:
            raise NotFoundError(f"Запис {entity_id} не знайдено.")
        return entity

    def clear(self) -> None:
        """Прибирає всі записи (потрібно для імпорту в режимі overwrite)."""
        self._items.clear()

    def save(self) -> None:
        """Скидає поточний стан на диск."""
        self._store.save(self._items.values())
