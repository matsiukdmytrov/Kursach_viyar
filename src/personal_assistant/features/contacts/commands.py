"""CLI-команди книги контактів.

Обробники нічого не друкують — вони повертають рядок. Через це кожну команду
можна перевірити тестом без емуляції термінала.
"""

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from personal_assistant.cli.registry import Argument, Registry
from personal_assistant.core.dates import DATE_FORMAT_HINT, format_date
from personal_assistant.core.errors import PersonalAssistantError, ValidationError
from personal_assistant.core.text import EMPTY, format_table, join_or_dash, pluralise, value_or_dash
from personal_assistant.features.contacts import portability, service
from personal_assistant.features.contacts.models import Contact
from personal_assistant.features.contacts.portability import ImportMode, ImportResult

if TYPE_CHECKING:
    from personal_assistant.context import AppContext

GROUP = "Контакти"
#: Обмін даними виділено в окремий розділ довідки — так само, як у ТЗ.
GROUP_PORTABILITY = "Імпорт та експорт"
STAR = "★"

#: Скільки помилкових рядків показувати після імпорту.
MAX_REPORTED_ERRORS = 10

#: Слово, яким користувач дозволяє перезапис наявного файлу.
FORCE_WORD = "force"


def register(registry: Registry) -> None:
    """Підключає команди контактів до реєстру."""
    registry.add(
        "add contact",
        _add_contact,
        summary="Створити контакт",
        group=GROUP,
        usage="<ім'я> [телефон]",
        min_args=1,
        arguments=(Argument("<ім'я>"), Argument("[телефон]")),
    )
    registry.add(
        "list contacts",
        _list_contacts,
        summary="Показати всі контакти",
        group=GROUP,
        aliases=("contacts",),
    )
    registry.add(
        "show contact",
        _show_contact,
        summary="Показати один контакт повністю",
        group=GROUP,
        usage="<контакт>",
        min_args=1,
        arguments=(Argument("<контакт>", values=_contact_values),),
    )
    registry.add(
        "find contacts",
        _find_contacts,
        summary="Пошук за іменем, номером, email чи адресою",
        group=GROUP,
        usage="<запит>",
        min_args=1,
        aliases=("find",),
        arguments=(Argument("<запит>"),),
    )
    registry.add(
        "rename contact",
        _rename_contact,
        summary="Змінити ім'я контакту",
        group=GROUP,
        usage="<контакт> <нове ім'я>",
        min_args=2,
        arguments=(Argument("<контакт>", values=_contact_values), Argument("<нове ім'я>")),
    )
    registry.add(
        "delete contact",
        _delete_contact,
        summary="Видалити контакт",
        group=GROUP,
        usage="<контакт>",
        min_args=1,
        arguments=(Argument("<контакт>", values=_contact_values),),
    )
    registry.add(
        "add phone",
        _add_phone,
        summary="Додати номер телефону",
        group=GROUP,
        usage="<контакт> <телефон>",
        min_args=2,
        arguments=(Argument("<контакт>", values=_contact_values), Argument("<телефон>")),
    )
    registry.add(
        "remove phone",
        _remove_phone,
        summary="Прибрати номер телефону",
        group=GROUP,
        usage="<контакт> <телефон>",
        min_args=2,
        arguments=(
            Argument("<контакт>", values=_contact_values),
            Argument("<телефон>", values=_phone_values),
        ),
    )
    registry.add(
        "set email",
        _set_email,
        summary="Записати email (порожнє значення очищає поле)",
        group=GROUP,
        usage="<контакт> [email]",
        min_args=1,
        arguments=(Argument("<контакт>", values=_contact_values), Argument("[email]")),
    )
    registry.add(
        "set address",
        _set_address,
        summary="Записати адресу (порожнє значення очищає поле)",
        group=GROUP,
        usage="<контакт> [адреса]",
        min_args=1,
        arguments=(Argument("<контакт>", values=_contact_values), Argument("[адреса]")),
    )
    registry.add(
        "set birthday",
        _set_birthday,
        summary=f"Записати дату народження у форматі {DATE_FORMAT_HINT}",
        group=GROUP,
        usage="<контакт> [дата]",
        min_args=1,
        arguments=(Argument("<контакт>", values=_contact_values), Argument("[дата]")),
    )
    registry.add(
        "birthdays",
        _birthdays,
        summary="Хто святкує найближчими днями",
        group=GROUP,
        usage=f"[днів, типово {service.DEFAULT_BIRTHDAY_WINDOW}]",
        arguments=(Argument("[днів]"),),
    )
    registry.add(
        "favorite",
        _favorite,
        summary="Позначити контакт обраним",
        group=GROUP,
        usage="<контакт>",
        min_args=1,
        arguments=(Argument("<контакт>", values=_contact_values),),
    )
    registry.add(
        "unfavorite",
        _unfavorite,
        summary="Зняти позначку «обраний»",
        group=GROUP,
        usage="<контакт>",
        min_args=1,
        arguments=(Argument("<контакт>", values=_contact_values),),
    )
    registry.add(
        "list favorites",
        _list_favorites,
        summary="Показати обрані контакти",
        group=GROUP,
        aliases=("favorites",),
    )
    registry.add(
        "export contacts",
        _export_contacts,
        summary="Зберегти контакти у .json або .csv",
        group=GROUP_PORTABILITY,
        usage=f"<файл> [{FORCE_WORD}]",
        min_args=1,
        arguments=(
            Argument("<файл>", path=True),
            Argument("[force]", values=_force_word),
        ),
    )
    registry.add(
        "import contacts",
        _import_contacts,
        summary="Прочитати контакти з .json або .csv",
        group=GROUP_PORTABILITY,
        usage=f"<файл> [{' | '.join(mode.value for mode in ImportMode)}]",
        min_args=1,
        arguments=(
            Argument("<файл>", path=True),
            Argument("[режим]", values=_import_modes),
        ),
    )


# ----------------------------------------------- джерела для автодоповнення


def _contact_values(ctx: "AppContext", _args: list[str]) -> list[str]:
    return [contact.name for contact in service.listing(ctx.contacts)]


def _phone_values(ctx: "AppContext", args: list[str]) -> list[str]:
    """Номери саме того контакту, якого вже вказали першим аргументом."""
    if not args:
        return []
    try:
        return service.resolve(ctx.contacts, args[0]).phones
    except PersonalAssistantError:
        return []


def _force_word(_ctx: "AppContext", _args: list[str]) -> list[str]:
    return [FORCE_WORD]


def _import_modes(_ctx: "AppContext", _args: list[str]) -> list[str]:
    return [mode.value for mode in ImportMode]


# --------------------------------------------------------------- обробники


def _add_contact(ctx: "AppContext", args: list[str]) -> str:
    name, *rest = args
    # Номер, введений без лапок, приїжджає кількома токенами: "067 123 45 67".
    phone = " ".join(rest) if rest else None
    contact = service.create(ctx.contacts, name, phone)
    suffix = f" з номером {contact.phones[0]}" if contact.phones else ""
    return f"Контакт '{contact.name}' створено{suffix}."


def _list_contacts(ctx: "AppContext", _args: list[str]) -> str:
    contacts = service.listing(ctx.contacts)
    if not contacts:
        return "Книга контактів порожня. Почни з 'add contact <ім'я>'."
    return _contacts_table(contacts)


def _show_contact(ctx: "AppContext", args: list[str]) -> str:
    contact = service.resolve(ctx.contacts, " ".join(args))
    return _contact_details(contact)


def _find_contacts(ctx: "AppContext", args: list[str]) -> str:
    query = " ".join(args)
    found = service.search(ctx.contacts, query)
    if not found:
        return f"За запитом '{query}' нічого не знайдено."
    return _contacts_table(found)


def _rename_contact(ctx: "AppContext", args: list[str]) -> str:
    reference, *rest = args
    contact = service.resolve(ctx.contacts, reference)
    old_name = contact.name
    service.rename(ctx.contacts, contact, " ".join(rest))
    return f"Контакт '{old_name}' перейменовано на '{contact.name}'."


def _delete_contact(ctx: "AppContext", args: list[str]) -> str:
    contact = service.delete(ctx.contacts, " ".join(args))
    return f"Контакт '{contact.name}' видалено."


def _add_phone(ctx: "AppContext", args: list[str]) -> str:
    contact, phone = _contact_and_phone(ctx, args)
    added = service.add_phone(contact, phone)
    return f"Контакту '{contact.name}' додано номер {added}."


def _remove_phone(ctx: "AppContext", args: list[str]) -> str:
    contact, phone = _contact_and_phone(ctx, args)
    removed = service.remove_phone(contact, phone)
    return f"У контакту '{contact.name}' прибрано номер {removed}."


def _set_email(ctx: "AppContext", args: list[str]) -> str:
    return _set(ctx, args, field="email", label="Email")


def _set_address(ctx: "AppContext", args: list[str]) -> str:
    return _set(ctx, args, field="address", label="Адресу")


def _set_birthday(ctx: "AppContext", args: list[str]) -> str:
    return _set(ctx, args, field="birthday", label="Дату народження")


def _birthdays(ctx: "AppContext", args: list[str]) -> str:
    days = _parse_days(args)
    entries = service.upcoming_birthdays(ctx.contacts, days)
    if not entries:
        return f"Найближчі {days} {pluralise(days, 'день', 'дні', 'днів')} іменинників немає."

    rows = [
        [
            _days_left(entry.days_left),
            format_date(entry.when),
            entry.contact.name,
            join_or_dash(entry.contact.phones),
        ]
        for entry in entries
    ]
    return format_table(rows, headers=["Коли", "Дата", "Ім'я", "Телефони"])


def _favorite(ctx: "AppContext", args: list[str]) -> str:
    contact = service.resolve(ctx.contacts, " ".join(args))
    if not service.set_favorite(contact, favorite=True):
        return f"Контакт '{contact.name}' уже в обраних."
    return f"Контакт '{contact.name}' додано до обраних."


def _unfavorite(ctx: "AppContext", args: list[str]) -> str:
    contact = service.resolve(ctx.contacts, " ".join(args))
    if not service.set_favorite(contact, favorite=False):
        return f"Контакт '{contact.name}' і так не був обраним."
    return f"Контакт '{contact.name}' прибрано з обраних."


def _list_favorites(ctx: "AppContext", _args: list[str]) -> str:
    contacts = service.favorites(ctx.contacts)
    if not contacts:
        return "Обраних контактів немає. Познач когось командою 'favorite <контакт>'."
    return _contacts_table(contacts)


def _export_contacts(ctx: "AppContext", args: list[str]) -> str:
    path, force = _split_force(args)

    contacts = service.listing(ctx.contacts)
    if not contacts:
        return "Книга контактів порожня — експортувати нічого."

    count = portability.export_contacts(contacts, path, force=force)
    return f"Збережено {_plural_contacts(count)} у {path}."


def _import_contacts(ctx: "AppContext", args: list[str]) -> str:
    path, mode_word = _split_path_and_mode(args)
    mode = ImportMode.parse(mode_word) if mode_word else ImportMode.SKIP

    rows = portability.read_rows(path)
    if not rows:
        return f"У файлі {path} немає жодного запису."

    result = portability.import_contacts(ctx.contacts, rows, mode)
    return _import_report(result, mode)


# ------------------------------------------------------------------ службове


def _split_force(args: list[str]) -> tuple[Path, bool]:
    """Відділяє слово `force` від шляху, який могли ввести без лапок."""
    if len(args) > 1 and args[-1].casefold() == FORCE_WORD:
        return _path(args[:-1]), True
    return _path(args), False


def _split_path_and_mode(args: list[str]) -> tuple[Path, str]:
    """Відділяє необов'язковий режим від шляху, який могли ввести без лапок.

    Розв'язуємо неоднозначність за файловою системою, а не за переліком
    відомих слів: інакше `import contacts data.json мerge` з одруківкою
    приклеїв би це слово до шляху й поскаржився на відсутній файл замість
    того, щоб сказати «невідомий режим».
    """
    full = _path(args)
    if len(args) == 1 or full.exists():
        return full, ""

    without_last = _path(args[:-1])
    if without_last.exists():
        return without_last, args[-1]

    # Ні той, ні той шлях не існує — хай про це скаже читання файлу.
    return full, ""


def _path(parts: list[str]) -> Path:
    return Path(" ".join(parts)).expanduser()


def _import_report(result: ImportResult, mode: ImportMode) -> str:
    parts = [f"додано {result.added}"]
    if result.replaced:
        parts.append(f"замінено {result.replaced}")
    if result.merged:
        parts.append(f"доповнено {result.merged}")
    if result.skipped:
        parts.append(f"пропущено {result.skipped}")

    lines = [f"Імпорт завершено (режим '{mode.value}'): {', '.join(parts)}."]

    if result.skipped and mode is ImportMode.SKIP:
        lines.append(
            "Пропущені — це контакти, які вже є в книзі. "
            f"Щоб оновити їх, повтори з режимом '{ImportMode.REPLACE.value}' "
            f"або '{ImportMode.MERGE.value}'."
        )

    if result.errors:
        lines.append(f"\nНе вдалося прочитати {len(result.errors)} рядків:")
        for row, message in result.errors[:MAX_REPORTED_ERRORS]:
            lines.append(f"  рядок {row}: {message}")
        hidden = len(result.errors) - MAX_REPORTED_ERRORS
        if hidden > 0:
            lines.append(f"  …і ще {hidden}.")

    return "\n".join(lines)


def _plural_contacts(count: int) -> str:
    return f"{count} {pluralise(count, 'контакт', 'контакти', 'контактів')}"


def _contact_and_phone(ctx: "AppContext", args: list[str]) -> tuple[Contact, str]:
    """Розбирає `<контакт> <телефон>`, де номер міг приїхати кількома токенами."""
    reference, *rest = args
    return service.resolve(ctx.contacts, reference), " ".join(rest)


def _set(ctx: "AppContext", args: list[str], *, field: str, label: str) -> str:
    """Спільна логіка для `set email`, `set address` і `set birthday`."""
    reference, *rest = args
    contact = service.resolve(ctx.contacts, reference)
    value = " ".join(rest).strip()

    service.set_field(contact, field, value or None)
    if not value:
        return f"{label} контакту '{contact.name}' очищено."

    stored = getattr(contact, field)
    shown = format_date(stored) if isinstance(stored, date) else value_or_dash(stored)
    return f"{label} контакту '{contact.name}' записано: {shown}."


def _parse_days(args: list[str]) -> int:
    if not args:
        return service.DEFAULT_BIRTHDAY_WINDOW
    try:
        return int(args[0])
    except ValueError as exc:
        raise ValidationError(f"'{args[0]}' — це не кількість днів.") from exc


def _days_left(days: int) -> str:
    if days == 0:
        return "сьогодні"
    if days == 1:
        return "завтра"
    return f"через {days} {pluralise(days, 'день', 'дні', 'днів')}"


def _contacts_table(contacts: list[Contact]) -> str:
    rows = [
        [
            STAR if contact.favorite else " ",
            contact.name,
            join_or_dash(contact.phones),
            value_or_dash(contact.email),
            format_date(contact.birthday) if contact.birthday else EMPTY,
        ]
        for contact in contacts
    ]
    return format_table(rows, headers=[" ", "Ім'я", "Телефони", "Email", "Народження"])


def _contact_details(contact: Contact) -> str:
    birthday = EMPTY
    if contact.birthday:
        days = contact.days_to_birthday()
        birthday = (
            f"{format_date(contact.birthday)} ({_days_left(days)})" if days is not None else ""
        )

    rows = [
        ["Телефони:", join_or_dash(contact.phones)],
        ["Email:", value_or_dash(contact.email)],
        ["Адреса:", value_or_dash(contact.address)],
        ["Народження:", birthday],
        ["Ідентифікатор:", contact.short_id],
    ]
    title = f"{contact.name} {STAR}" if contact.favorite else contact.name
    body = "\n".join(f"  {line}" for line in format_table(rows).splitlines())
    return f"{title}\n{body}"
