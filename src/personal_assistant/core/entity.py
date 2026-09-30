"""Базова сутність, від якої успадковуються всі доменні моделі."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

#: Скільки перших символів UUID показуємо користувачеві та приймаємо у командах.
SHORT_ID_LENGTH = 8


def utc_now() -> datetime:
    """Поточний момент у UTC (виділено окремо, щоб тести могли підмінити)."""
    return datetime.now(UTC)


class Entity(BaseModel):
    """Спільні поля будь-якого збереженого запису.

    Ключем скрізь є UUID, а не ім'я чи заголовок: інакше двох однойменних
    контактів не існує, а перейменування перетворюється на «видалити й
    створити». Користувачеві повний UUID не показуємо — для команд вистачає
    короткого префікса (`short_id`).
    """

    model_config = ConfigDict(validate_assignment=True, str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def short_id(self) -> str:
        """Скорочений ідентифікатор для виводу та введення в CLI."""
        return str(self.id)[:SHORT_ID_LENGTH]

    def touch(self) -> None:
        """Позначає запис як щойно змінений."""
        self.updated_at = utc_now()
