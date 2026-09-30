"""REPL: читає рядок, знаходить команду, друкує відповідь.

Дані зберігаються у `finally`, тому Ctrl+C, Ctrl+D і навіть незловлена
помилка не залишають користувача без збережених змін.
"""

import sys
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory

from personal_assistant.cli.bootstrap import build_registry
from personal_assistant.cli.completion import AssistantCompleter, make_toolbar
from personal_assistant.cli.registry import Registry
from personal_assistant.cli.signals import ExitRequested
from personal_assistant.context import AppContext
from personal_assistant.core.errors import PersonalAssistantError

if TYPE_CHECKING:
    from prompt_toolkit.history import History

PROMPT = "pa> "
BANNER = "Персональний помічник. Введи 'help' для переліку команд, 'exit' — щоб вийти."


def dispatch(registry: Registry, ctx: AppContext, text: str) -> str:
    """Виконує один рядок введення і повертає текст для показу."""
    if not text.strip():
        return ""

    resolved = registry.resolve(text)
    if resolved is None:
        hints = registry.suggest(text)
        tail = f" Можливо, ви мали на увазі: {', '.join(hints)}?" if hints else ""
        return f"Невідома команда '{text.strip()}'.{tail}"

    command, args = resolved
    if len(args) < command.min_args:
        return f"Замало аргументів. Використання: {command.signature}"

    try:
        return command.handler(ctx, args)
    except PersonalAssistantError as exc:
        return f"Помилка: {exc.message}"


def _make_session(ctx: AppContext, registry: Registry) -> PromptSession[str] | None:
    """Готує сесію prompt_toolkit; повертає None, якщо термінала немає.

    Без термінала (пайп, CI, тести) prompt_toolkit не працює — там читаємо
    звичайним `input()`.
    """
    if not sys.stdin.isatty():
        return None

    history: History | None = None
    try:
        ctx.settings.data_dir.mkdir(parents=True, exist_ok=True)
        history = FileHistory(str(ctx.settings.history_file))
    except OSError:
        history = None  # історія — приємний бонус, а не привід не запуститись

    return PromptSession(
        message=PROMPT,
        history=history,
        completer=AssistantCompleter(registry, ctx),
        complete_while_typing=True,
        auto_suggest=AutoSuggestFromHistory(),
        bottom_toolbar=make_toolbar(registry),
    )


def _read(session: PromptSession[str] | None) -> str:
    if session is not None:
        return session.prompt()
    line = input(PROMPT)
    print(line)  # відлуння, щоб протокол сесії читався у пайпі
    return line


def run() -> int:
    """Запускає REPL. Повертає код виходу процесу."""
    registry = build_registry()

    try:
        ctx = AppContext.create()
    except PersonalAssistantError as exc:
        print(f"Не вдалося прочитати збережені дані.\n{exc.message}")
        return 1

    session = _make_session(ctx, registry)

    print(BANNER)
    try:
        while True:
            try:
                text = _read(session)
            except KeyboardInterrupt:
                continue  # Ctrl+C скасовує рядок, але не застосунок
            except EOFError:
                break

            try:
                output = dispatch(registry, ctx, text)
            except ExitRequested:
                break

            if output:
                print(output)
    finally:
        ctx.save_all()
        print("Дані збережено. До зустрічі!")

    return 0
