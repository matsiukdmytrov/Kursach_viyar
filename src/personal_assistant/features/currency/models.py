"""Курс однієї валюти до гривні на конкретну дату."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

#: Гривня — базова валюта НБУ: усі курси в довіднику подано відносно неї,
#: а сама вона в довіднику відсутня.
BASE_CODE = "UAH"
BASE_NAME = "Українська гривня"


@dataclass(frozen=True, slots=True)
class Rate:
    """Скільки гривень коштує одна одиниця валюти.

    Курс зберігається як `Decimal`, а не `float`: при конвертації сум
    `float` дає хвости на кшталт `4149.999999`, які видно користувачу.
    """

    code: str
    name: str
    rate: Decimal
    on_date: date

    @classmethod
    def base(cls, on_date: date) -> "Rate":
        """Гривня як «курс» 1:1 — щоб конвертація з/у UAH не була окремим випадком."""
        return cls(code=BASE_CODE, name=BASE_NAME, rate=Decimal(1), on_date=on_date)
