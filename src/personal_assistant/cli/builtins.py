"""Вбудовані команди REPL: привітання, довідка, вихід."""

from typing import TYPE_CHECKING

from personal_assistant.cli.registry import Argument, Registry
from personal_assistant.cli.signals import ExitRequested

if TYPE_CHECKING:
    from personal_assistant.context import AppContext

GROUP = "Загальні"


def register(registry: Registry) -> None:
    """Реєструє вбудовані команди.

    Довідка будується з самого реєстру, тому обробник замикається на нього —
    інакше довелося б тримати окремий текст і синхронізувати його руками.
    """

    def show_help(_ctx: "AppContext", args: list[str]) -> str:
        if args:
            return _help_for(registry, " ".join(args))
        return _help_all(registry)

    def _command_values(_ctx: "AppContext", _args: list[str]) -> list[str]:
        return registry.names()

    def hello(_ctx: "AppContext", _args: list[str]) -> str:
        return "Вітаю! Чим можу допомогти? Введи 'help', щоб побачити перелік команд."

    def quit_app(_ctx: "AppContext", _args: list[str]) -> str:
        raise ExitRequested

    registry.add(
        "help",
        show_help,
        summary="Перелік команд або довідка по одній команді",
        group=GROUP,
        usage="[команда]",
        aliases=("?",),
        arguments=(Argument("[команда]", values=_command_values),),
    )
    registry.add("hello", hello, summary="Привітання", group=GROUP)
    registry.add(
        "exit",
        quit_app,
        summary="Вийти (дані зберігаються автоматично)",
        group=GROUP,
        aliases=("quit", "close", "good bye"),
    )


def _help_all(registry: Registry) -> str:
    groups = registry.groups()
    width = max((len(cmd.signature) for cmd in registry.commands), default=0)

    lines: list[str] = []
    for group, commands in groups.items():
        lines.append(f"\n{group}")
        lines.append("─" * len(group))
        lines.extend(f"  {cmd.signature:<{width}}  {cmd.summary}" for cmd in commands)

    lines.append("\nПідказка: Tab доповнює команду, ↑/↓ гортає історію.")
    return "\n".join(lines).lstrip("\n")


def _help_for(registry: Registry, name: str) -> str:
    resolved = registry.resolve(name)
    if resolved is None:
        hints = registry.suggest(name)
        tail = f" Можливо: {', '.join(hints)}." if hints else ""
        return f"Команди '{name}' не існує.{tail}"

    command, _ = resolved
    lines = [f"{command.signature}", f"  {command.summary}", f"  Розділ: {command.group}"]
    if command.aliases:
        lines.append(f"  Аліаси: {', '.join(command.aliases)}")
    return "\n".join(lines)
