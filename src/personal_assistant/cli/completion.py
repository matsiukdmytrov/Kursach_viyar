"""Автодоповнення та підказки під час введення.

Доповнюються не лише назви команд, а й аргументи: імена контактів,
заголовки нотаток і задач, теги, статуси, шляхи. Усе це описано в реєстрі
командою, а не зашито тут, тому нова фіча отримує доповнення разом зі своєю
реєстрацією.
"""

from collections.abc import Callable, Iterable, Iterator
from typing import TYPE_CHECKING

from prompt_toolkit.application import get_app
from prompt_toolkit.completion import CompleteEvent, Completer, Completion, PathCompleter
from prompt_toolkit.document import Document

from personal_assistant.cli.registry import Registry, tokenize

if TYPE_CHECKING:
    from personal_assistant.context import AppContext

#: Скільки варіантів показувати для одного аргументу.
MAX_SUGGESTIONS = 30

_QUOTES = "\"'"


def split_at_cursor(text: str) -> tuple[str, str]:
    """Ділить рядок на завершену частину і фрагмент, який зараз набирають.

    Пробіли всередині лапок не рахуються межею слова: у `add contact "Іван
    Пет` фрагментом є `"Іван Пет`, а не `Пет`.
    """
    quote = ""
    start = 0

    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ""
        elif char in _QUOTES:
            quote = char
        elif char.isspace():
            start = index + 1

    return text[:start], text[start:]


def unquote(fragment: str) -> str:
    """Прибирає відкриваючу лапку з фрагмента, що набирається."""
    return fragment[1:] if fragment[:1] in _QUOTES else fragment


def quote_if_needed(value: str) -> str:
    """Бере значення в лапки, якщо без них воно розпалося б на кілька слів."""
    return f'"{value}"' if any(char.isspace() for char in value) else value


class AssistantCompleter(Completer):
    """Доповнює назви команд та їх аргументи."""

    def __init__(self, registry: Registry, ctx: "AppContext") -> None:
        self.registry = registry
        self.ctx = ctx
        self._paths = PathCompleter(expanduser=True)

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        text = document.text_before_cursor
        completed, fragment = split_at_cursor(text)

        yield from self._command_completions(text, completed, fragment)
        yield from self._argument_completions(completed, fragment, complete_event)

    # ------------------------------------------------------------- команди

    def _command_completions(
        self, text: str, completed: str, fragment: str
    ) -> Iterator[Completion]:
        """Назви команд.

        Пропонуються навіть тоді, коли коротша команда вже збіглася: після
        `find no` треба показати `find notes`, а не лише аргументи `find`.
        """
        typed = [*tokenize(completed), unquote(fragment)]
        prefix = " ".join(part for part in typed if part).casefold()

        indent = len(text) - len(text.lstrip())
        start_position = -(len(text) - indent)

        for name in self.registry.names():
            if name.startswith(prefix) and name != prefix:
                command, _ = self.registry.resolve(name) or (None, [])
                yield Completion(
                    name,
                    start_position=start_position,
                    display=name,
                    display_meta=command.summary if command else "",
                )

    # ------------------------------------------------------------ аргументи

    def _argument_completions(
        self, completed: str, fragment: str, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        resolved = self.registry.resolve(completed)
        if resolved is None:
            return

        command, args = resolved
        argument = command.argument_at(len(args))
        if argument is None:
            return

        needle = unquote(fragment)
        if argument.path:
            yield from self._path_completions(needle, complete_event)
            return

        if argument.values is None:
            return

        for value in _matching(argument.values(self.ctx, args), needle):
            yield Completion(
                quote_if_needed(value),
                start_position=-len(fragment),
                display=value,
                display_meta=argument.label,
            )

    def _path_completions(self, needle: str, complete_event: CompleteEvent) -> Iterator[Completion]:
        sub_document = Document(needle, len(needle))
        yield from self._paths.get_completions(sub_document, complete_event)


def _matching(values: Iterable[str], needle: str) -> list[str]:
    """Варіанти, що містять набране; ті, що починаються з нього, — першими."""
    folded = needle.casefold()
    if not folded:
        return list(values)[:MAX_SUGGESTIONS]

    starts: list[str] = []
    contains: list[str] = []
    for value in values:
        lowered = value.casefold()
        if lowered.startswith(folded):
            starts.append(value)
        elif folded in lowered:
            contains.append(value)

    return [*starts, *contains][:MAX_SUGGESTIONS]


#: Що показує нижній рядок, поки команду не впізнано.
DEFAULT_HINT = "Tab — доповнення   ↑↓ — історія   help — перелік команд"


def make_toolbar(registry: Registry) -> Callable[[], str]:
    """Повертає функцію нижнього рядка підказки для prompt_toolkit."""

    def toolbar() -> str:
        return describe(registry, get_app().current_buffer.text) or DEFAULT_HINT

    return toolbar


def describe(registry: Registry, text: str) -> str:
    """Підказка для рядка, який зараз набирають."""
    completed, _ = split_at_cursor(text)
    resolved = registry.resolve(completed) or registry.resolve(text)
    if resolved is None:
        return ""

    command, args = resolved
    hint = f"{command.signature} — {command.summary}"

    argument = command.argument_at(len(args))
    return f"{hint}   ▸ зараз: {argument.label}" if argument else hint
