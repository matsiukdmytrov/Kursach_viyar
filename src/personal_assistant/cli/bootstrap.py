"""Складання реєстру команд із усіх фіч.

Кожна фіча підключається одним рядком. Порядок реєстрації визначає порядок
розділів у `help`.
"""


from personal_assistant.cli import builtins
from personal_assistant.cli.registry import Registry
from personal_assistant.features.contacts import commands as contacts_commands
from personal_assistant.features.currency import commands as currency_commands
from personal_assistant.features.files import commands as files_commands
from personal_assistant.features.notes import commands as notes_commands
from personal_assistant.features.tasks import commands as tasks_commands
from personal_assistant.features.weather import commands as weather_commands


def build_registry() -> Registry:
    """Створює реєстр з усіма доступними командами."""
    registry = Registry()
    builtins.register(registry)
    contacts_commands.register(registry)
    notes_commands.register(registry)
    tasks_commands.register(registry)
    files_commands.register(registry)
    weather_commands.register(registry)
    currency_commands.register(registry)
    # Фази 6–9: import/export, AI, зовнішні API
    return registry
