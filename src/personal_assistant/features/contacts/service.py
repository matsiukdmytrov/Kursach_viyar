"""Бізнес-логіка книги контактів.

Тут живуть правила, які не належать окремому запису: як знайти контакт за
тим, що набрав користувач, чи можна створити тезку, кого показувати у списку
іменинників. CLI лише передає сюди рядки й друкує результат.
"""

from dataclasses import dataclass
from datetime import date

from personal_assistant.core.dates import next_occurrence
from personal_assistant.core.errors import ConflictError, NotFoundError, ValidationError
from personal_assistant.core.lookup import EntityNames, resolve_by_text
from personal_assistant.core.repository import Repository
from personal_assistant.core.text import CollationKey, collation_key
from personal_assistant.core.validation import assign, build
from personal_assistant.features.contacts.models import Contact, normalize_phone

#: Скільки днів охоплює `birthdays` без аргументу.
DEFAULT_BIRTHDAY_WINDOW = 7
#: Верхня межа вікна — далі список перестає бути корисним.
MAX_BIRTHDAY_WINDOW = 365

#: Як звертатись до контакту в повідомленнях про помилки пошуку.
CONTACT_NAMES = EntityNames(
    accusative="Контакт",
    plural_dative="контактам",
    hint="Уточни ім'я.",
)

#: Назви полів для повідомлень про помилки валідації.
FIELD_LABELS = {
    "name": "ім'я",
    "phones": "телефон",
    "email": "email",
    "address": "адреса",
    "birthday": "дата народження",
}


@dataclass(frozen=True, slots=True)
class UpcomingBirthday:
    """Контакт разом із датою найближчого дня народження."""

    contact: Contact
    when: date
    days_left: int


# --------------------------------------------------------------------- пошук


def resolve(repo: Repository[Contact], reference: str) -> Contact:
    """Знаходить контакт за іменем, його частиною або ідентифікатором."""
    return resolve_by_text(
        repo,
        reference,
        text_of=lambda contact: contact.name,
        names=CONTACT_NAMES,
    )


def search(repo: Repository[Contact], query: str) -> list[Contact]:
    """Контакти, у яких запит трапляється в будь-якому полі."""
    if not query.strip():
        raise ValidationError("Порожній запит нічого не шукає.")
    return sorted(repo.find(lambda contact: contact.matches(query)), key=_by_name)


def favorites(repo: Repository[Contact]) -> list[Contact]:
    """Обрані контакти в алфавітному порядку."""
    return sorted(repo.find(lambda contact: contact.favorite), key=_by_name)


def listing(repo: Repository[Contact]) -> list[Contact]:
    """Усі контакти: спершу обрані, далі за алфавітом."""
    return sorted(repo.all(), key=lambda contact: (not contact.favorite, _by_name(contact)))


def upcoming_birthdays(
    repo: Repository[Contact],
    days: int = DEFAULT_BIRTHDAY_WINDOW,
    today: date | None = None,
) -> list[UpcomingBirthday]:
    """Контакти, у яких день народження настане протягом `days` днів.

    Сьогоднішній день входить у вікно: іменинника логічно бачити саме в його
    день, а не лише напередодні.
    """
    if days < 0:
        raise ValidationError("Кількість днів не може бути від'ємною.")
    if days > MAX_BIRTHDAY_WINDOW:
        raise ValidationError(f"Максимальне вікно — {MAX_BIRTHDAY_WINDOW} днів.")

    today = today or date.today()
    found: list[UpcomingBirthday] = []

    for contact in repo.all():
        if contact.birthday is None:
            continue
        when = next_occurrence(contact.birthday, today)
        days_left = (when - today).days
        if days_left <= days:
            found.append(UpcomingBirthday(contact=contact, when=when, days_left=days_left))

    return sorted(found, key=lambda entry: (entry.days_left, _by_name(entry.contact)))


# ------------------------------------------------------------------- зміни


def create(
    repo: Repository[Contact],
    name: str,
    phone: str | None = None,
) -> Contact:
    """Створює контакт.

    Тезок не допускаємо: імена — основний спосіб адресації в CLI, і два «Іван
    Петренко» зробили б половину команд неоднозначними.
    """
    clean_name = name.strip()
    if not clean_name:
        raise ValidationError("Ім'я контакту не може бути порожнім.")

    if repo.find(lambda contact: contact.name.casefold() == clean_name.casefold()):
        raise ConflictError(
            f"Контакт '{clean_name}' уже існує. Додай уточнення до імені або зміни наявний запис."
        )

    contact = build(
        Contact,
        FIELD_LABELS,
        name=clean_name,
        phones=[phone] if phone else [],
    )
    return repo.add(contact)


def rename(repo: Repository[Contact], contact: Contact, new_name: str) -> None:
    """Перейменовує контакт, зберігаючи його ідентифікатор."""
    clean_name = new_name.strip()
    if not clean_name:
        raise ValidationError("Ім'я контакту не може бути порожнім.")

    if clean_name.casefold() == contact.name.casefold():
        assign(contact, "name", clean_name, FIELD_LABELS)  # зміна лише регістру
        contact.touch()
        return

    if repo.find(lambda other: other.name.casefold() == clean_name.casefold()):
        raise ConflictError(f"Контакт '{clean_name}' уже існує.")

    assign(contact, "name", clean_name, FIELD_LABELS)
    contact.touch()


def delete(repo: Repository[Contact], reference: str) -> Contact:
    """Видаляє контакт і повертає видалений запис."""
    contact = resolve(repo, reference)
    return repo.delete(contact.id)


def add_phone(contact: Contact, phone: str) -> str:
    """Додає номер. Повертає його канонічний вигляд."""
    target = normalize_phone(phone)
    if target in contact.phones:
        raise ConflictError(f"Номер {target} вже записаний у контакту '{contact.name}'.")

    assign(contact, "phones", [*contact.phones, target], FIELD_LABELS)
    contact.touch()
    return target


def remove_phone(contact: Contact, phone: str) -> str:
    """Прибирає номер. Повертає його канонічний вигляд."""
    target = normalize_phone(phone)
    if target not in contact.phones:
        raise NotFoundError(f"У контакту '{contact.name}' немає номера {target}.")

    assign(contact, "phones", [p for p in contact.phones if p != target], FIELD_LABELS)
    contact.touch()
    return target


def set_field(contact: Contact, field: str, value: str | None) -> None:
    """Записує email, адресу або дату народження."""
    if field not in {"email", "address", "birthday"}:
        raise ValidationError(f"Поле '{field}' не можна змінити цією командою.")

    assign(contact, field, value, FIELD_LABELS)
    contact.touch()


def set_favorite(contact: Contact, favorite: bool) -> bool:
    """Позначає контакт обраним. Повертає False, якщо стан не змінився."""
    if contact.favorite is favorite:
        return False
    contact.favorite = favorite
    contact.touch()
    return True


# ------------------------------------------------------------------ службове


def _by_name(contact: Contact) -> CollationKey:
    return collation_key(contact.name)
