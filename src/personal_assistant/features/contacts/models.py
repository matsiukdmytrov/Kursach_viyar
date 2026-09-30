"""Модель контакту та валідація його полів."""

import re
from datetime import date
from typing import Annotated, Any, Self

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, Field, field_validator, model_validator

from personal_assistant.core.dates import coerce_date, next_occurrence
from personal_assistant.core.entity import Entity
from personal_assistant.core.errors import ValidationError
from personal_assistant.core.text import collapse_whitespace
from personal_assistant.features.contacts.blocked_domains import BLOCKED_MESSAGE, is_blocked

#: Код України для номерів, введених у національному форматі.
UKRAINE_CODE = "38"

#: Межі довжини полів. Потрібні не з формальних міркувань, а щоб вставлений
#: помилково абзац не перетворив таблицю контактів на нечитабельне полотно.
MAX_NAME_LENGTH = 100
MAX_ADDRESS_LENGTH = 200
_DIGITS_ONLY = re.compile(r"\D")


def normalize_phone(value: str) -> str:
    """Зводить будь-який прийнятний запис номера до вигляду `+380671234567`.

    Користувач вводить номери як завгодно — `067 123-45-67`, `(067) 1234567`,
    `+380671234567`. Зберігати їх у різному вигляді не можна: тоді пошук за
    номером і перевірка на дублікати не працюють.
    """
    raw = value.strip()
    if not raw:
        raise ValidationError("Номер телефону не може бути порожнім.")

    international = raw.startswith("+")
    digits = _DIGITS_ONLY.sub("", raw)

    if not digits:
        raise ValidationError(f"У номері '{value}' немає жодної цифри.")

    if international:
        if not 8 <= len(digits) <= 15:
            raise ValidationError(
                f"Міжнародний номер '{value}' має містити від 8 до 15 цифр, а не {len(digits)}."
            )
        return f"+{digits}"

    if len(digits) == 10 and digits.startswith("0"):
        return f"+{UKRAINE_CODE}{digits}"

    if len(digits) == 12 and digits.startswith(UKRAINE_CODE):
        return f"+{digits}"

    raise ValidationError(
        f"Не вдалося розпізнати номер '{value}'. "
        "Приклади прийнятних форматів: 0671234567, +380671234567, +1 202 555 0123."
    )


def normalize_email(value: str) -> str:
    """Перевіряє адресу і зводить її до канонічного вигляду.

    Власна обгортка потрібна заради повідомлення: `EmailStr` кидає англомовний
    технічний текст, який у списку помилок поруч з українськими виглядає як
    збій, а не як підказка.
    """
    raw = value.strip()
    try:
        # Без перевірки DNS: застосунок має працювати без мережі.
        validated = validate_email(raw, check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValidationError(
            f"'{value}' не схоже на email-адресу. Приклад: ivan@example.com"
        ) from exc

    # Перевіряємо обидві форми домену: кирилична адреса могла приїхати як
    # `пошта.рф`, так і в punycode — і це той самий домен.
    if is_blocked(validated.domain) or is_blocked(validated.ascii_domain):
        raise ValidationError(BLOCKED_MESSAGE)

    return str(validated.normalized)


PhoneNumber = Annotated[str, AfterValidator(normalize_phone)]
EmailAddress = Annotated[str, AfterValidator(normalize_email)]


class Contact(Entity):
    """Запис у книзі контактів."""

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH, description="Ім'я контакту")
    phones: list[PhoneNumber] = Field(default_factory=list)
    email: EmailAddress | None = None
    address: str | None = Field(default=None, max_length=MAX_ADDRESS_LENGTH)
    birthday: date | None = None
    favorite: bool = False

    @field_validator("birthday", mode="before")
    @classmethod
    def _accept_dd_mm_yyyy(cls, value: Any) -> Any:
        """Дозволяє і ввід `DD.MM.YYYY`, і ISO-формат зі сховища."""
        return coerce_date(value) if isinstance(value, str) else value

    @field_validator("birthday")
    @classmethod
    def _reject_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("дата народження не може бути в майбутньому")
        return value

    @field_validator("name", mode="before")
    @classmethod
    def _clean_name(cls, value: Any) -> Any:
        """Зводить переноси рядків і табуляції в імені до звичайних пробілів."""
        return collapse_whitespace(value) if isinstance(value, str) else value

    @field_validator("address", "email", mode="before")
    @classmethod
    def _clean_optional(cls, value: Any) -> Any:
        """Порожній рядок з CLI означає «поле не задано», а не «порожнє значення»."""
        if not isinstance(value, str):
            return value
        cleaned = collapse_whitespace(value)
        return cleaned or None

    @model_validator(mode="after")
    def _dedupe_phones(self) -> Self:
        """Прибирає повторені номери, зберігаючи порядок додавання."""
        unique = list(dict.fromkeys(self.phones))
        if unique != self.phones:
            # присвоєння через __dict__, щоб не запускати валідацію повторно
            self.__dict__["phones"] = unique
        return self

    # -------------------------------------------------------------- поведінка

    def has_phone(self, phone: str) -> bool:
        """Чи є такий номер у контакту (порівняння за нормалізованим виглядом)."""
        return normalize_phone(phone) in self.phones

    def days_to_birthday(self, today: date | None = None) -> int | None:
        """Скільки днів лишилось до найближчого дня народження."""
        if self.birthday is None:
            return None
        today = today or date.today()
        return (next_occurrence(self.birthday, today) - today).days

    def matches(self, query: str) -> bool:
        """Чи згадується `query` в імені, номерах, email або адресі."""
        needle = query.strip().casefold()
        if not needle:
            return False

        haystack = [self.name, self.email or "", self.address or "", *self.phones]
        if any(needle in field.casefold() for field in haystack):
            return True

        # Пошук за номером має працювати і тоді, коли його ввели в іншому форматі.
        digits = _DIGITS_ONLY.sub("", needle)
        return bool(digits) and any(digits in phone for phone in self.phones)
