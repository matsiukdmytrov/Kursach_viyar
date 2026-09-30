"""Міст між помилками pydantic і помилками, які бачить користувач.

Pydantic кидає власний `ValidationError` з англомовним технічним описом. Якщо
не перехопити його тут, будь-який кривий ввід у REPL завершиться трейсбеком,
бо `cli/app.py` навмисно ловить лише `PersonalAssistantError`.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from personal_assistant.core.errors import ValidationError

#: Префікс, який pydantic додає до повідомлень із наших власних валідаторів.
_VALUE_ERROR_PREFIX = "Value error, "

#: Технічні коди pydantic, для яких свій текст зрозуміліший за оригінальний.
_KNOWN_MESSAGES = {
    "string_too_short": "значення не може бути порожнім",
    "missing": "значення обов'язкове",
    "value_error": "",
}


def build[ModelT: BaseModel](
    model: type[ModelT],
    labels: Mapping[str, str] | None = None,
    **fields: Any,
) -> ModelT:
    """Створює модель, перетворюючи помилки pydantic на зрозумілі користувачу."""
    try:
        return model(**fields)
    except PydanticValidationError as exc:
        raise ValidationError(humanise(exc, labels)) from exc


def assign(
    entity: BaseModel, field: str, value: Any, labels: Mapping[str, str] | None = None
) -> None:
    """Присвоює поле моделі з `validate_assignment`, перекладаючи помилки."""
    try:
        setattr(entity, field, value)
    except PydanticValidationError as exc:
        raise ValidationError(humanise(exc, labels)) from exc


def humanise(exc: PydanticValidationError, labels: Mapping[str, str] | None = None) -> str:
    """Збирає з помилки pydantic одне речення для користувача."""
    labels = labels or {}
    parts: list[str] = []

    for error in exc.errors():
        field = _field_name(error.get("loc", ()), labels)
        message = _message(error)
        parts.append(f"{field}: {message}" if field else message)

    return "; ".join(parts) or "дані не пройшли перевірку"


def _field_name(loc: tuple[Any, ...], labels: Mapping[str, str]) -> str:
    if not loc:
        return ""
    # loc для елемента списку виглядає як ('phones', 0) — індекс не показуємо.
    head = str(loc[0])
    return labels.get(head, head)


def _message(error: Mapping[str, Any]) -> str:
    raw = str(error.get("msg", "")).strip()
    if raw.startswith(_VALUE_ERROR_PREFIX):
        return raw.removeprefix(_VALUE_ERROR_PREFIX)

    error_type = str(error.get("type", ""))
    if error_type == "string_too_long":
        limit = _context(error).get("max_length")
        return f"задовге значення (максимум {limit} символів)" if limit else "задовге значення"

    override = _KNOWN_MESSAGES.get(error_type)
    return override or raw


def _context(error: Mapping[str, Any]) -> Mapping[str, Any]:
    context = error.get("ctx")
    return context if isinstance(context, Mapping) else {}
