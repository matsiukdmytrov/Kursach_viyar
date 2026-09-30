"""Реєстр команд — єдине джерело правди про CLI.

З цього реєстру автоматично будуються диспетчер, довідка `help`,
автодоповнення та підказки «можливо, ви мали на увазі». Додати команду —
означає описати її тут один раз; жодних паралельних списків, які треба
синхронізувати вручну, у проєкті немає.
"""

import difflib
import shlex
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from personal_assistant.context import AppContext

#: Обробник команди: отримує контекст і решту слів рядка, повертає текст відповіді.
type Handler = Callable[["AppContext", list[str]], str]

#: Джерело значень для автодоповнення аргументу. Отримує контекст і вже
#: набрані аргументи — щоб `remove phone Іван <Tab>` міг показати номери саме
#: цього контакту.
type ArgumentValues = Callable[["AppContext", list[str]], Iterable[str]]

#: Наскільки схожим має бути введене слово, щоб пропонувати його як виправлення.
SUGGESTION_CUTOFF = 0.6


def tokenize(text: str) -> list[str]:
    """Розбиває рядок на аргументи, поважаючи лапки.

    Імена контактів складаються з кількох слів, тому `add contact "Іван
    Петренко"` має давати один аргумент, а не два. Екранування зворотним
    слешем навмисно вимкнене: інакше шлях `C:\\Users\\name` втратив би
    роздільники ще до того, як його побачить команда сортування файлів.
    """
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        # Незакрита лапка — краще віддати щось розумне, ніж впасти.
        return text.split()


@dataclass(frozen=True, slots=True)
class Argument:
    """Чим доповнювати один позиційний аргумент команди."""

    label: str
    """Як аргумент називається у підказці: `<контакт>`, `<тека>`."""

    values: "ArgumentValues | None" = None
    """Звідки брати варіанти; None — варіантів немає."""

    path: bool = False
    """Доповнювати шляхами файлової системи."""


@dataclass(frozen=True, slots=True)
class Command:
    """Опис однієї команди CLI."""

    name: str
    handler: "Handler"
    summary: str
    group: str
    usage: str = ""
    aliases: tuple[str, ...] = ()
    min_args: int = 0
    arguments: tuple[Argument, ...] = ()

    def argument_at(self, index: int) -> "Argument | None":
        """Опис аргументу за позицією або None, якщо їх стільки не буває."""
        return self.arguments[index] if 0 <= index < len(self.arguments) else None

    @property
    def signature(self) -> str:
        """Рядок для довідки: назва разом з очікуваними аргументами."""
        return f"{self.name} {self.usage}".strip()

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


@dataclass(slots=True)
class Registry:
    """Колекція команд із розбором введеного рядка."""

    _by_name: dict[str, Command] = field(default_factory=dict)
    _commands: list[Command] = field(default_factory=list)
    _max_words: int = 1

    def register(self, command: Command) -> None:
        """Додає команду. Повторна назва — це помилка програміста, не користувача."""
        for name in command.all_names:
            key = name.casefold()
            if key in self._by_name:
                raise ValueError(f"Команда '{name}' вже зареєстрована.")
            self._by_name[key] = command
            self._max_words = max(self._max_words, len(key.split()))
        self._commands.append(command)

    def add(
        self,
        name: str,
        handler: "Handler",
        *,
        summary: str,
        group: str,
        usage: str = "",
        aliases: tuple[str, ...] = (),
        min_args: int = 0,
        arguments: tuple[Argument, ...] = (),
    ) -> None:
        """Скорочення для `register(Command(...))`."""
        self.register(
            Command(
                name=name,
                handler=handler,
                summary=summary,
                group=group,
                usage=usage,
                aliases=aliases,
                min_args=min_args,
                arguments=arguments,
            )
        )

    # ------------------------------------------------------------- доступ

    @property
    def commands(self) -> list[Command]:
        """Команди в порядку реєстрації."""
        return list(self._commands)

    def names(self) -> list[str]:
        """Усі назви та аліаси — основа для автодоповнення."""
        return sorted(self._by_name)

    def groups(self) -> dict[str, list[Command]]:
        """Команди, згруповані за розділом, у порядку появи розділів."""
        grouped: dict[str, list[Command]] = {}
        for command in self._commands:
            grouped.setdefault(command.group, []).append(command)
        return grouped

    # ------------------------------------------------------------- розбір

    def resolve(self, text: str) -> tuple[Command, list[str]] | None:
        """Знаходить команду в рядку, віддаючи перевагу найдовшому збігу.

        `add` і `add contact` можуть існувати одночасно, тому спершу пробуємо
        збіг із трьох слів, потім із двох, потім з одного.
        """
        words = tokenize(text)
        if not words:
            return None

        for size in range(min(self._max_words, len(words)), 0, -1):
            key = " ".join(words[:size]).casefold()
            command = self._by_name.get(key)
            if command is not None:
                return command, words[size:]
        return None

    def suggest(self, text: str, limit: int = 3) -> list[str]:
        """Найближчі за написанням команди для повідомлення про помилку."""
        words = text.split()
        if not words:
            return []

        candidates = self.names()
        attempts = [" ".join(words[:size]).casefold() for size in range(min(2, len(words)), 0, -1)]

        matches: list[str] = []
        for attempt in attempts:
            for match in difflib.get_close_matches(
                attempt, candidates, n=limit, cutoff=SUGGESTION_CUTOFF
            ):
                if match not in matches:
                    matches.append(match)

        # Команди, що починаються з введеного слова, теж корисні: `add` -> `add contact`.
        prefix = words[0].casefold()
        for name in candidates:
            if name.startswith(prefix) and name not in matches:
                matches.append(name)

        return matches[:limit]
