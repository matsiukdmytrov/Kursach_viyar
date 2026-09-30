"""Спільний фундамент, від якого залежать усі фічі."""

from personal_assistant.core.config import Settings, get_settings
from personal_assistant.core.entity import Entity
from personal_assistant.core.errors import (
    ConflictError,
    NotFoundError,
    PersonalAssistantError,
    StorageError,
    ValidationError,
)
from personal_assistant.core.repository import Repository
from personal_assistant.core.storage import JsonStore

__all__ = [
    "ConflictError",
    "Entity",
    "JsonStore",
    "NotFoundError",
    "PersonalAssistantError",
    "Repository",
    "Settings",
    "StorageError",
    "ValidationError",
    "get_settings",
]
