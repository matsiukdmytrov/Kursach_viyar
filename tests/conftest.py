"""Спільні фікстури: усе працює у тимчасовій теці, справжні дані не чіпаються."""

from pathlib import Path

import pytest

from personal_assistant.context import AppContext
from personal_assistant.core.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
def ctx(settings: Settings) -> AppContext:
    return AppContext.create(settings)
