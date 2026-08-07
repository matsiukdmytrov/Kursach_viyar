from __future__ import annotations

import os
import pickle
from collections import UserDict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Set, Tuple


# ===========================================================================
# ДЕКОРАТОР
# ===========================================================================
def input_error(func: Callable[..., str]) -> Callable[..., str | None]:
    def inner(*args, **kwargs) -> str | None:
        try:
            return func(*args, **kwargs)
        except KeyError as e:
            return f"ERR: Contact {e} not found."
        except ValueError as e:
            return f"ERR: Invalid data — {e}."
        except IndexError as e:
            return f"ERR: Missing arguments — {e}. Type 'help' for usage guide."

    return inner


# ===========================================================================
# БЛОК МОДЕЛЕЙ (OOP)
# ===========================================================================
class Field:
    """Базовий клас для всіх полів запису."""

    _value: Any  # підкласи (Phone, Birthday) зберігають різні типи (str, date)

    def __init__(self, value: str) -> None:
        self.value = value

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, v: str) -> None:
        self._value = v

    def __str__(self) -> str:
        return str(self._value)


class Name(Field):
    """Обов'язкове поле — ім'я контакту."""

    def __init__(self, value: str) -> None:
        if not value.strip():
            raise ValueError("Name cannot be empty.")
        super().__init__(value)


class Phone(Field):
    """
    Необов'язкове поле — номер телефону.
    Валідація через setter: рівно 10 цифр.
    """

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, phone: str) -> None:
        if not phone.isdigit() or len(phone) != 10:
            raise ValueError(
                f"'{phone}' is not valid. Phone must contain exactly 10 digits."
            )
        self._value = phone


class Birthday(Field):
    """
    Необов'язкове поле — дата народження.
    Валідація через setter: формат DD.MM.YYYY.
    Зберігається як datetime.date.
    """

    _DATE_FORMAT = "%d.%m.%Y"
    _value: date

    @property
    def value(self) -> date:
        return self._value

    @value.setter
    def value(self, bday: str) -> None:
        try:
            self._value = datetime.strptime(bday, self._DATE_FORMAT).date()
        except ValueError:
            raise ValueError(
                f"'{bday}' is not valid. Birthday must be in DD.MM.YYYY format."
            )

    def __str__(self) -> str:
        return self._value.strftime(self._DATE_FORMAT)


class Record:
    """
    Запис контакту: ім'я + список телефонів + необов'язковий день народження.
    """

    def __init__(self, name: str, birthday: str | None = None) -> None:
        self.name: Name = Name(name)
        self.phones: List[Phone] = []
        self.birthday: Birthday | None = Birthday(birthday) if birthday else None

    # --- телефони ---

    def add_phone(self, phone: str) -> None:
        if self.find_phone(phone):
            raise ValueError(f"Phone {phone} already exists for '{self.name.value}'.")
        self.phones.append(Phone(phone))

    def remove_phone(self, phone: str) -> None:
        found: Phone | None = self.find_phone(phone)
        if found is None:
            raise ValueError(f"Phone {phone} not found for '{self.name.value}'.")
        self.phones.remove(found)

    def edit_phone(self, old_phone: str, new_phone: str) -> None:
        found: Phone | None = self.find_phone(old_phone)
        if found is None:
            raise ValueError(f"Phone {old_phone} not found for '{self.name.value}'.")
        found.value = new_phone

    def find_phone(self, phone: str) -> Phone | None:
        return next((p for p in self.phones if p.value == phone), None)

    # --- день народження ---

    def add_birthday(self, birthday: str) -> None:
        self.birthday = Birthday(birthday)

    def days_to_birthday(self, _today: date | None = None) -> int | None:
        """Повертає кількість днів до наступного дня народження (0 = сьогодні)."""
        if self.birthday is None:
            return None
        today: date = _today or date.today()
        bday: date = self.birthday.value
        try:
            next_bday = bday.replace(year=today.year)
        except ValueError:
            next_bday = date(today.year, 3, 1)
        if next_bday < today:
            try:
                next_bday = bday.replace(year=today.year + 1)
            except ValueError:
                next_bday = date(today.year + 1, 3, 1)
        return (next_bday - today).days

    def __str__(self) -> str:
        phones_str: str = "; ".join(p.value for p in self.phones)
        bday_str = f", birthday: {self.birthday}" if self.birthday else ""
        return f"Contact name: {self.name.value}, phones: {phones_str}{bday_str}"


class AddressBook(UserDict[str, Record]):
    """
    Адресна книга — успадковується від UserDict.
    Підтримує: пагінацію (iterator), пошук (search),
    збереження та завантаження з файлу (save/load).
    """

    _path: str = str(
        Path(__file__).resolve().parent.parent / "reserv_files" / "address_book.pkl"
    )

    # --- пагінація ---

    def iterator(self, n: int) -> Generator[List[Record], None, None]:
        """Генератор, що повертає записи порціями по n штук."""
        records = list(self.data.values())
        for i in range(0, len(records), n):
            yield records[i : i + n]

    # --- пошук ---

    def search(self, query: str) -> List[Record]:
        """
        Повертає всі записи, де query зустрічається (без урахування регістру)
        в імені або у будь-якому номері телефону.
        """
        q = query.lower()
        return [
            r
            for r in self.data.values()
            if q in r.name.value.lower() or any(q in p.value for p in r.phones)
        ]

    # --- базові операції ---

    def add_record(self, record: Record) -> None:
        self.data[record.name.value] = record

    def find(self, name: str) -> Record | None:
        return self.data.get(name)

    def delete(self, name: str) -> None:
        if name not in self.data:
            raise KeyError(f"'{name}'")
        del self.data[name]

    # --- збереження / завантаження ---

    def save(self, path: str | None = None) -> None:
        """
        Зберігає адресну книгу у бінарний файл через pickle.
        Запис атомарний: спочатку у тимчасовий файл, потім заміна,
        щоб збій під час запису не знищив попередні дані.
        За замовчуванням пише у reserv_files/address_book.pkl в корені проекту.
        """
        save_path = path or self._path
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        tmp_path = f"{save_path}.tmp"
        with open(tmp_path, "wb") as f:
            pickle.dump(self.data, f)
        os.replace(tmp_path, save_path)

    @classmethod
    def load(cls, path: str | None = None) -> "AddressBook":
        """
        Завантажує адресну книгу з файлу.
        Якщо файл не існує або пошкоджений — повертає порожню книгу.
        """
        load_path = path or cls._path
        book = cls()
        p = Path(load_path)
        if p.exists():
            try:
                with open(load_path, "rb") as f:
                    book.data = pickle.load(f)
            except (pickle.UnpicklingError, EOFError, AttributeError, ValueError):
                print(
                    f"WARN: could not read '{load_path}' — starting with an empty book."
                )
        return book


# ===========================================================================
# ХЕНДЛЕРИ
# ===========================================================================
@input_error
def create_contact(book: AddressBook, args: List[str]) -> str:
    name, phone = args[0], args[1]
    if book.find(name):
        return f"Contact '{name}' already exists. Use 'add phone {name} <phone>' to add a number."
    record: Record = Record(name)
    record.add_phone(phone)
    book.add_record(record)
    return f"Contact '{name}' created with phone {phone}."


@input_error
def add_phone(book: AddressBook, args: List[str]) -> str:
    name, phone = args[0], args[1]
    record: Record | None = book.find(name)
    if record is None:
        raise KeyError(f"'{name}'")
    record.add_phone(phone)
    return f"Phone {phone} added to '{name}'. Total: {len(record.phones)}."


@input_error
def update_phone(book: AddressBook, args: List[str]) -> str:
    name, old_phone, new_phone = args[0], args[1], args[2]
    record: Record | None = book.find(name)
    if record is None:
        raise KeyError(f"'{name}'")
    record.edit_phone(old_phone, new_phone)
    return f"Phone updated for '{name}': {old_phone} → {new_phone}."


@input_error
def search_contact(book: AddressBook, args: List[str]) -> str:
    """Точний пошук за іменем."""
    name: str = args[0]
    record: Record | None = book.find(name)
    if record is None:
        raise KeyError(f"'{name}'")
    phones: str = "\n  ".join(
        f"{i + 1}. {p.value}" for i, p in enumerate(record.phones)
    )
    return (
        f"Contact '{name}':\n  {phones}"
        if phones
        else f"Contact '{name}' has no phones."
    )


@input_error
def find_contacts(book: AddressBook, args: List[str]) -> str:
    """Пошук за частиною імені або номера телефону."""
    query: str = args[0]
    results: List[Record] = book.search(query)
    if not results:
        return f"No contacts found matching '{query}'."
    lines = [f"  {i}. {record}" for i, record in enumerate(results, 1)]
    return f"Found {len(results)} contact(s) for '{query}':\n" + "\n".join(lines)


@input_error
def remove_phone(book: AddressBook, args: List[str]) -> str:
    name, phone = args[0], args[1]
    record: Record | None = book.find(name)
    if record is None:
        raise KeyError(f"'{name}'")
    record.remove_phone(phone)
    if not record.phones:
        book.delete(name)
        return f"Last phone removed. Contact '{name}' deleted."
    return f"Phone {phone} removed from '{name}'."


@input_error
def delete_contact(book: AddressBook, args: List[str]) -> str:
    name: str = args[0]
    book.delete(name)
    return f"Contact '{name}' deleted."


@input_error
def list_contacts(book: AddressBook, args: List[str]) -> str:
    if not book.data:
        return "No contacts saved yet. Use 'create contact <name> <phone>' to add one."
    lines: List[str] = [f"  {i}. {record}" for i, record in enumerate(book.values(), 1)]
    return "All contacts:\n" + "\n".join(lines)


@input_error
def add_birthday(book: AddressBook, args: List[str]) -> str:
    name, bday = args[0], args[1]
    record: Record | None = book.find(name)
    if record is None:
        raise KeyError(f"'{name}'")
    record.add_birthday(bday)
    return f"Birthday {bday} set for '{name}'."


@input_error
def birthday_cmd(book: AddressBook, args: List[str]) -> str:
    name: str = args[0]
    record: Record | None = book.find(name)
    if record is None:
        raise KeyError(f"'{name}'")
    days = record.days_to_birthday()
    if days is None:
        return f"Contact '{name}' has no birthday set."
    if days == 0:
        return f"Today is {name}'s birthday!"
    return f"{days} day(s) until {name}'s birthday."


def hello(book: AddressBook, args: List[str]) -> str:
    return "Hello! Type 'help' to see all available commands."


# ===========================================================================
# ДОВІДКА
# ===========================================================================
HELP_TEXT: str = """
╔══════════════════════════════════════════════════════════════════════╗
║                       AVAILABLE COMMANDS                             ║
╠══════════════════════════════════════════════════════════════════════╣
║  hello                                    — greeting                 ║
║  create contact <name> <phone>            — add new contact          ║
║  add phone <name> <phone>                 — add extra phone          ║
║  update phone <name> <old> <new>          — change phone number      ║
║  remove phone <name> <phone>              — delete one phone         ║
║  delete contact <name>                    — delete contact           ║
║  search <name>                            — exact search by name     ║
║  find <query>                             — search by name or phone  ║
║  list contacts                            — show all contacts        ║
║  add birthday <name> <DD.MM.YYYY>         — set birthday             ║
║  birthday <name>                          — days to next birthday    ║
╠══════════════════════════════════════════════════════════════════════╣
║  exit  |  close  |  good bye              — quit (auto-saves)        ║
╚══════════════════════════════════════════════════════════════════════╝
  Tip: phone must be exactly 10 digits  |  names are case-sensitive
  Data is saved automatically on exit.
"""


def show_help(book: AddressBook, args: List[str]) -> str:
    return HELP_TEXT


# ===========================================================================
# ТАБЛИЦЯ КОМАНД
# ===========================================================================
COMMANDS: Dict[str, Callable[[AddressBook, List[str]], str | None]] = {
    "hello": hello,
    "help": show_help,
    "create contact": create_contact,
    "add phone": add_phone,
    "add birthday": add_birthday,
    "update phone": update_phone,
    "remove phone": remove_phone,
    "delete contact": delete_contact,
    "search": search_contact,
    "find": find_contacts,
    "list contacts": list_contacts,
    "birthday": birthday_cmd,
}

EXIT_COMMANDS: Set[str] = {"exit", "close", "good bye"}
TWO_WORD_KEYS: Set[str] = {k for k in list(COMMANDS) + list(EXIT_COMMANDS) if " " in k}


# ===========================================================================
# ПАРСЕР
# ===========================================================================
def parse_input(user_input: str) -> Tuple[str, List[str]]:
    parts: List[str] = user_input.strip().split()
    if not parts:
        return "", []
    two_word: str = f"{parts[0].lower()} {parts[1].lower()}" if len(parts) >= 2 else ""
    if two_word in TWO_WORD_KEYS:
        return two_word, parts[2:]
    return parts[0].lower(), parts[1:]


# ===========================================================================
# ГОЛОВНИЙ ЦИКЛ
# ===========================================================================
def main() -> None:
    book: AddressBook = AddressBook.load()

    contacts_count = len(book.data)
    print("Welcome to the Assistant Bot!")
    if contacts_count:
        print(f"Loaded {contacts_count} contact(s) from disk.")
    print("Type 'help' to see all available commands.\n")

    try:
        while True:
            user_input: str = input(">>> ")
            if not user_input.strip():
                continue
            command, args = parse_input(user_input)
            if command in EXIT_COMMANDS:
                print("Address book saved. Good bye!")
                break
            handler: Callable[[AddressBook, List[str]], str | None] | None = (
                COMMANDS.get(command)
            )
            if handler is None:
                print(
                    f"Unknown command '{command}'. Type 'help' to see available commands."
                )
            else:
                print(handler(book, args))
    except (KeyboardInterrupt, EOFError):
        print("\nInterrupted — saving address book...")
    finally:
        # Дані зберігаються за будь-якого сценарію виходу, включно з Ctrl+C
        book.save()


if __name__ == "__main__":
    main()