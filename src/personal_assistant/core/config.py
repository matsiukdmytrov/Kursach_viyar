"""Налаштування застосунку.

Читаються один раз із оточення (з підтримкою `.env`) і кешуються. Тести
скидають кеш через `get_settings.cache_clear()` або будують `Settings`
напряму — глобального стану, який не можна перевизначити, тут немає.
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

#: Корінь репозиторію: .../src/personal_assistant/core/config.py -> вгору на 4
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseModel):
    """Значення, які застосунок бере з оточення."""

    model_config = {"frozen": True}

    data_dir: Path = Field(description="Тека, у якій лежать JSON-файли даних")
    anthropic_api_key: str | None = Field(
        default=None,
        description="Ключ Claude API; якщо None — AI працює на локальних евристиках",
    )

    @property
    def contacts_file(self) -> Path:
        return self.data_dir / "contacts.json"

    @property
    def notes_file(self) -> Path:
        return self.data_dir / "notes.json"

    @property
    def tasks_file(self) -> Path:
        return self.data_dir / "tasks.json"

    @property
    def history_file(self) -> Path:
        """Історія введених команд для prompt_toolkit."""
        return self.data_dir / ".command_history"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Повертає налаштування застосунку (кешовані на весь процес)."""
    load_dotenv(PROJECT_ROOT / ".env")

    raw_dir = os.getenv("PA_DATA_DIR")
    data_dir = Path(raw_dir).expanduser() if raw_dir else PROJECT_ROOT / "data"

    return Settings(
        data_dir=data_dir.resolve(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
    )
