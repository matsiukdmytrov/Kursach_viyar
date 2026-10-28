"""Сервіс курсів: розбір відповіді НБУ, кеш, конвертація."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from personal_assistant.core.errors import NotFoundError, ValidationError
from personal_assistant.features.currency.service import (
    CurrencyService,
    ExchangeServiceError,
    normalize_code,
    parse_amount,
    parse_rates,
)

DAY = date(2026, 10, 27)

PAYLOAD = [
    {"r030": 840, "txt": "Долар США", "rate": 41.5, "cc": "USD", "exchangedate": "27.10.2026"},
    {"r030": 978, "txt": "Євро", "rate": 48.25, "cc": "EUR", "exchangedate": "27.10.2026"},
    {"r030": 985, "txt": "Злотий", "rate": 11.3, "cc": "PLN", "exchangedate": "27.10.2026"},
]


class FakeFetcher:
    def __init__(self, payload=PAYLOAD):
        self.payload = payload
        self.calls: list[date] = []

    def __call__(self, on_date: date):
        self.calls.append(on_date)
        return self.payload


@pytest.fixture
def fetcher():
    return FakeFetcher()


@pytest.fixture
def service(fetcher):
    return CurrencyService(fetcher)


class TestParseRates:
    def test_reads_codes(self):
        assert set(parse_rates(PAYLOAD, DAY)) == {"USD", "EUR", "PLN"}

    def test_keeps_rate_as_decimal(self):
        assert parse_rates(PAYLOAD, DAY)["USD"].rate == Decimal("41.5")

    def test_reads_publication_date(self):
        assert parse_rates(PAYLOAD, date(2000, 1, 1))["EUR"].on_date == DAY

    def test_skips_broken_items(self):
        payload = [*PAYLOAD, {"cc": "XXX"}, "сміття", {"cc": "BAD", "rate": "abc"}]
        assert set(parse_rates(payload, DAY)) == {"USD", "EUR", "PLN"}

    def test_rejects_non_list(self):
        with pytest.raises(ExchangeServiceError):
            parse_rates({"message": "error"}, DAY)


class TestService:
    def test_rate_by_code(self, service):
        assert service.rate("usd", DAY).rate == Decimal("41.5")

    def test_rate_by_alias(self, service):
        assert service.rate("євро", DAY).code == "EUR"

    def test_hryvnia_is_one(self, service):
        assert service.rate("грн", DAY).rate == 1

    def test_unknown_currency(self, service):
        with pytest.raises(NotFoundError):
            service.rate("ZZZ", DAY)

    def test_caches_per_date(self, service, fetcher):
        service.rate("USD", DAY)
        service.rate("EUR", DAY)
        assert fetcher.calls == [DAY]

    def test_empty_answer_is_not_found(self):
        with pytest.raises(NotFoundError):
            CurrencyService(FakeFetcher([])).rates(DAY)

    def test_rejects_far_future(self, service):
        with pytest.raises(ValidationError):
            service.rates(date.today() + timedelta(days=5))

    def test_allows_tomorrow(self, service):
        service.rates(date.today() + timedelta(days=1))


class TestConvert:
    def test_foreign_to_hryvnia(self, service):
        result, _, _ = service.convert(Decimal(100), "USD", "UAH", DAY)
        assert result == Decimal("4150.00")

    def test_hryvnia_to_foreign(self, service):
        result, _, _ = service.convert(Decimal(4150), "грн", "$", DAY)
        assert result == Decimal("100.00")

    def test_cross_rate(self, service):
        result, _, _ = service.convert(Decimal(100), "EUR", "USD", DAY)
        assert result == Decimal("116.27")


class TestParsing:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [("100", "100"), ("99,90", "99.90"), ("1_000", "1000"), ("0.5", "0.5")],
    )
    def test_amount(self, text, expected):
        assert parse_amount(text) == Decimal(expected)

    @pytest.mark.parametrize("text", ["abc", "-5", "nan", "inf"])
    def test_bad_amount(self, text):
        with pytest.raises(ValidationError):
            parse_amount(text)

    @pytest.mark.parametrize(
        ("text", "expected"), [("usd", "USD"), ("Долар", "USD"), ("€", "EUR"), ("грн", "UAH")]
    )
    def test_code(self, text, expected):
        assert normalize_code(text) == expected
