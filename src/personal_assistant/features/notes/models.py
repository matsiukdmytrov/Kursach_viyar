"""Модель нотатки та нормалізація тегів."""

import re
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from personal_assistant.core.entity import Entity
from personal_assistant.core.errors import ValidationError
from personal_assistant.core.text import CollationKey, collapse_whitespace, collation_key

#: Межі довжини — щоб заголовок не ламав верстку списку нотаток.
MAX_TITLE_LENGTH = 120
MAX_TAG_LENGTH = 40

_TAG_SEPARATORS = re.compile(r"[\s_]+")
_TAG_FORBIDDEN = re.compile(r"[^\w\-]", re.UNICODE)


def normalize_tag(value: str) -> str:
    """Зводить тег до канонічного вигляду: `#Робочі Справи` -> `робочі-справи`.

    Без нормалізації `#Work`, `work` і `#work` були б трьома різними тегами,
    і сортування та пошук за тегами розсипались би.
    """
    tag = value.strip().lstrip("#").casefold()
    tag = _TAG_SEPARATORS.sub("-", tag)
    tag = _TAG_FORBIDDEN.sub("", tag).strip("-")

    if not tag:
        raise ValidationError(f"Тег '{value}' порожній або складається лише з розділювачів.")
    if len(tag) > MAX_TAG_LENGTH:
        raise ValidationError(f"Тег задовгий: максимум {MAX_TAG_LENGTH} символів.")
    return tag


class Note(Entity):
    """Текстова нотатка з набором тегів."""

    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH, description="Заголовок нотатки")
    text: str = ""
    tags: list[str] = Field(default_factory=list)

    @field_validator("title", mode="before")
    @classmethod
    def _clean_title(cls, value: Any) -> Any:
        return collapse_whitespace(value) if isinstance(value, str) else value

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [normalize_tag(tag) if isinstance(tag, str) else tag for tag in value]

    @model_validator(mode="after")
    def _dedupe_tags(self) -> Self:
        """Прибирає повторення, зберігаючи порядок додавання."""
        unique = list(dict.fromkeys(self.tags))
        if unique != self.tags:
            self.__dict__["tags"] = unique
        return self

    # -------------------------------------------------------------- поведінка

    def has_tag(self, tag: str) -> bool:
        """Чи має нотатка такий тег (порівняння за нормалізованим виглядом)."""
        return normalize_tag(tag) in self.tags

    def add_tag(self, tag: str) -> bool:
        """Додає тег. Повертає False, якщо він уже був."""
        normalized = normalize_tag(tag)
        if normalized in self.tags:
            return False
        self.tags = [*self.tags, normalized]
        self.touch()
        return True

    def remove_tag(self, tag: str) -> bool:
        """Прибирає тег. Повертає False, якщо його не було."""
        normalized = normalize_tag(tag)
        if normalized not in self.tags:
            return False
        self.tags = [item for item in self.tags if item != normalized]
        self.touch()
        return True

    def matches(self, query: str) -> bool:
        """Чи згадується `query` в заголовку, тексті або тегах."""
        needle = query.strip().casefold()
        if not needle:
            return False
        return (
            needle in self.title.casefold()
            or needle in self.text.casefold()
            or any(needle in tag for tag in self.tags)
        )

    @property
    def sort_key(self) -> tuple[int, CollationKey, CollationKey]:
        """Ключ сортування за тегами; нотатки без тегів ідуть у кінець.

        Перший елемент відділяє нетеговані нотатки, решта — українська
        колація: сортувати теги звичайним порівнянням рядків так само хибно,
        як і імена.
        """
        if not self.tags:
            return 1, (), collation_key(self.title)
        first_tag = min(self.tags, key=collation_key)
        return 0, collation_key(first_tag), collation_key(self.title)
