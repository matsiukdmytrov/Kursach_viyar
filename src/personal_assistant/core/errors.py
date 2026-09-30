"""Ієрархія помилок застосунку.

CLI ловить лише `PersonalAssistantError` і показує `.message` користувачеві,
тому будь-яка помилка, яку користувач має побачити у зрозумілому вигляді,
повинна успадковуватись саме звідси. Усе інше — це баг, і воно має впасти
з трейсбеком.
"""


class PersonalAssistantError(Exception):
    """Базова помилка, яку CLI показує користувачеві як текст."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(PersonalAssistantError):
    """Дані не пройшли перевірку (телефон, email, дата тощо)."""


class NotFoundError(PersonalAssistantError):
    """Запис із такими ознаками не знайдено."""


class ConflictError(PersonalAssistantError):
    """Запис суперечить наявним даним (напр. дублікат)."""


class StorageError(PersonalAssistantError):
    """Не вдалося прочитати або записати файл даних."""
