"""Імпорт і експорт контактів у JSON та CSV.

Формат обміну навмисно відрізняється від того, що лежить у сховищі: тут немає
ні ідентифікаторів, ні службових дат, а дати записані так, як їх вводить
людина. Це файл для обміну й ручного редагування, а не резервна копія —
резервною копією є сам `data/contacts.json`.

Через це імпорт зіставляє записи за іменем, а не за ідентифікатором.
"""

import csv
import io
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from personal_assistant.core.dates import format_date
from personal_assistant.core.errors import (
    NotFoundError,
    PersonalAssistantError,
    StorageError,
    ValidationError,
)
from personal_assistant.core.repository import Repository
from personal_assistant.core.storage import atomic_write_bytes
from personal_assistant.core.validation import build
from personal_assistant.features.contacts.models import Contact
from personal_assistant.features.contacts.service import FIELD_LABELS

#: Колонки файлу обміну, у цьому порядку.
EXPORT_FIELDS = ("name", "phones", "email", "address", "birthday", "favorite")

#: Чим розділені телефони всередині однієї комірки.
PHONE_SEPARATOR = ";"

#: Excel впізнає UTF-8 у CSV лише за BOM, тому пишемо саме з ним.
CSV_ENCODING = "utf-8-sig"

#: Роздільники, серед яких шукаємо той, яким збережено чужий файл.
CSV_DELIMITERS = ",;\t"

#: Що вважаємо ствердною відповіддю в колонці «обраний».
TRUE_VALUES = frozenset({"так", "yes", "true", "1", "+", "y", "т"})


class ImportMode(StrEnum):
    """Що робити із записом, який уже є в книзі."""

    SKIP = "skip"
    REPLACE = "replace"
    MERGE = "merge"

    @classmethod
    def parse(cls, value: str) -> "ImportMode":
        normalized = value.strip().casefold()
        try:
            return cls(normalized)
        except ValueError as exc:
            allowed = ", ".join(mode.value for mode in cls)
            raise ValidationError(f"Невідомий режим '{value}'. Доступні: {allowed}.") from exc


@dataclass(slots=True)
class ImportResult:
    """Підсумок імпорту."""

    added: int = 0
    replaced: int = 0
    merged: int = 0
    skipped: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)

    @property
    def total_applied(self) -> int:
        return self.added + self.replaced + self.merged


# ------------------------------------------------------------------- експорт


def to_row(contact: Contact) -> dict[str, str]:
    """Перетворює контакт на рядок файлу обміну."""
    return {
        "name": contact.name,
        "phones": PHONE_SEPARATOR.join(contact.phones),
        "email": contact.email or "",
        "address": contact.address or "",
        "birthday": format_date(contact.birthday) if contact.birthday else "",
        "favorite": "так" if contact.favorite else "ні",
    }


def export_contacts(contacts: list[Contact], path: Path, *, force: bool = False) -> int:
    """Записує контакти у файл, формат визначається розширенням."""
    if path.exists() and not force:
        raise ValidationError(
            f"Файл {path} вже існує. Додай слово 'force', щоб перезаписати, або вкажи іншу назву."
        )

    rows = [to_row(contact) for contact in contacts]
    suffix = path.suffix.lower()

    if suffix == ".json":
        payload = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
    elif suffix == ".csv":
        payload = _csv_payload(rows)
    else:
        raise ValidationError(
            f"Невідомий формат '{suffix or path.name}'. Підтримуються .json і .csv."
        )

    atomic_write_bytes(path, payload)
    return len(rows)


def _csv_payload(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(EXPORT_FIELDS), lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode(CSV_ENCODING)


# -------------------------------------------------------------------- імпорт


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Читає файл обміну, формат визначається розширенням."""
    if not path.exists():
        raise NotFoundError(f"Файлу {path} не існує.")
    if path.is_dir():
        raise ValidationError(f"'{path}' — це тека, а не файл.")

    suffix = path.suffix.lower()
    if suffix == ".json":
        return _read_json(path)
    if suffix == ".csv":
        return _read_csv(path)
    raise ValidationError(f"Невідомий формат '{suffix or path.name}'. Підтримуються .json і .csv.")


def _read_json(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding=CSV_ENCODING))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"Не вдалося прочитати {path}: {exc}") from exc

    if not isinstance(data, list):
        raise ValidationError(f"У файлі {path} очікувався список контактів.")
    return [item for item in data if isinstance(item, dict)]


def _read_csv(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding=CSV_ENCODING)
    except (OSError, UnicodeDecodeError) as exc:
        raise StorageError(f"Не вдалося прочитати {path}: {exc}") from exc

    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=_sniff_delimiter(text))
    return [dict(row) for row in reader]


def _sniff_delimiter(text: str) -> str:
    """Визначає роздільник CSV.

    Excel з українською локаллю зберігає CSV через `;`, а не через кому.
    Файл, підготовлений колегою, має імпортуватись без ручного редагування.
    """
    sample = "\n".join(text.splitlines()[:5])
    try:
        return csv.Sniffer().sniff(sample, delimiters=CSV_DELIMITERS).delimiter
    except csv.Error:
        return ","


def import_contacts(
    repo: Repository[Contact],
    rows: list[dict[str, Any]],
    mode: ImportMode = ImportMode.SKIP,
) -> ImportResult:
    """Додає контакти з прочитаних рядків.

    Помилковий рядок не перериває імпорт: він потрапляє до переліку помилок,
    а решта файлу застосовується. Інакше один зіпсований запис у кінці
    великого файлу знецінював би всю операцію.
    """
    result = ImportResult()

    for index, row in enumerate(rows, start=2):  # рядок 1 — заголовок
        try:
            candidate = _build_contact(row)
        except PersonalAssistantError as exc:
            result.errors.append((index, exc.message))
            continue

        existing = _find_by_name(repo, candidate.name)
        if existing is None:
            repo.add(candidate)
            result.added += 1
        elif mode is ImportMode.SKIP:
            result.skipped += 1
        elif mode is ImportMode.REPLACE:
            _replace(existing, candidate)
            result.replaced += 1
        else:
            _merge(existing, candidate)
            result.merged += 1

    return result


def _build_contact(row: dict[str, Any]) -> Contact:
    name = str(row.get("name") or "").strip()
    if not name:
        raise ValidationError("порожнє ім'я")

    return build(
        Contact,
        FIELD_LABELS,
        name=name,
        phones=_split_phones(row.get("phones")),
        email=_clean(row.get("email")),
        address=_clean(row.get("address")),
        birthday=_clean(row.get("birthday")),
        favorite=_parse_bool(row.get("favorite")),
    )


def _split_phones(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    return [part.strip() for part in str(value).split(PHONE_SEPARATOR) if part.strip()]


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in TRUE_VALUES


def _find_by_name(repo: Repository[Contact], name: str) -> Contact | None:
    matches = repo.find(lambda contact: contact.name.casefold() == name.casefold())
    return matches[0] if matches else None


def _replace(existing: Contact, incoming: Contact) -> None:
    """Повністю замінює поля наявного контакту, зберігаючи ідентифікатор."""
    for name in ("phones", "email", "address", "birthday", "favorite"):
        setattr(existing, name, getattr(incoming, name))
    existing.touch()


def _merge(existing: Contact, incoming: Contact) -> None:
    """Дописує те, чого бракує, не стираючи наявних даних."""
    merged_phones = list(dict.fromkeys([*existing.phones, *incoming.phones]))
    if merged_phones != existing.phones:
        existing.phones = merged_phones

    for name in ("email", "address", "birthday"):
        if getattr(existing, name) is None and getattr(incoming, name) is not None:
            setattr(existing, name, getattr(incoming, name))

    if incoming.favorite:
        existing.favorite = True

    existing.touch()
