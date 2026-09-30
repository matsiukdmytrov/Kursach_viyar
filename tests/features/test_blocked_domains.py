"""Перевірка блокування поштових доменів держави-агресора."""

import pytest

from personal_assistant.core.errors import ValidationError
from personal_assistant.features.contacts.blocked_domains import BLOCKED_MESSAGE, is_blocked
from personal_assistant.features.contacts.models import Contact, normalize_email


class TestZones:
    @pytest.mark.parametrize(
        "domain",
        [
            "mail.ru",
            "bk.ru",
            "list.ru",
            "inbox.ru",
            "yandex.ru",
            "ya.ru",
            "rambler.ru",
            "ok.ru",
            "narod.ru",
            "pochta.ru",
            "krovatka.su",
            "mail.su",
            "example.moscow",
            "example.tatar",
        ],
    )
    def test_russian_zones_are_blocked(self, domain):
        assert is_blocked(domain)

    @pytest.mark.parametrize(
        "domain",
        ["пошта.рф", "почта.рф", "example.москва", "example.рус", "example.дети"],
    )
    def test_cyrillic_zones_are_blocked(self, domain):
        assert is_blocked(domain)

    @pytest.mark.parametrize(
        "domain",
        [
            "xn--80a1acny.xn--p1ai",
            "example.xn--80adxhks",
            "example.xn--p1acf",
            "example.xn--d1acj3b",
        ],
    )
    def test_punycode_form_is_blocked_too(self, domain):
        assert is_blocked(domain)

    def test_subdomains_are_blocked(self):
        assert is_blocked("smtp.mail.ru")
        assert is_blocked("a.b.c.ru")

    def test_case_is_ignored(self):
        assert is_blocked("MAIL.RU")

    def test_trailing_dot_is_ignored(self):
        assert is_blocked("mail.ru.")


class TestBelarusianZones:
    @pytest.mark.parametrize(
        "domain",
        ["tut.by", "mail.by", "open.by", "example.by", "example.бел", "example.xn--90ais"],
    )
    def test_blocked(self, domain):
        assert is_blocked(domain)

    def test_subdomains_are_blocked(self):
        assert is_blocked("smtp.tut.by")

    def test_similar_names_are_not_blocked(self):
        # Збіг має бути по межі крапки: `.by` не робить `goodby.com` забороненим.
        assert not is_blocked("goodby.com")
        assert not is_blocked("standby.org")


class TestServicesOutsideRussianZones:
    @pytest.mark.parametrize(
        "domain",
        ["yandex.com", "yandex.by", "yandex.kz", "yandex.com.tr", "vk.com", "fromru.com"],
    )
    def test_blocked(self, domain):
        assert is_blocked(domain)

    def test_subdomain_of_such_a_service(self):
        assert is_blocked("mail.yandex.com")


class TestAllowed:
    @pytest.mark.parametrize(
        "domain",
        [
            "gmail.com",
            "ukr.net",
            "i.ua",
            "meta.ua",
            "example.com",
            "example.org",
            "outlook.com",
            "proton.me",
            # Німецький провайдер — схожа назва не привід блокувати.
            "mail.com",
            # Збіг має бути по межі крапки, а не по підрядку.
            "notyandex.com",
            "myru.com",
            "peru.com",
            "example.ru.com",
        ],
    )
    def test_not_blocked(self, domain):
        assert not is_blocked(domain)

    def test_empty_domain_is_not_blocked(self):
        assert not is_blocked("   ")


class TestEmailValidation:
    @pytest.mark.parametrize(
        "address",
        ["ivan@mail.ru", "ivan@yandex.com", "ivan@пошта.рф", "ivan@xn--80a1acny.xn--p1ai"],
    )
    def test_normalize_email_rejects_with_the_agreed_message(self, address):
        with pytest.raises(ValidationError) as exc_info:
            normalize_email(address)
        assert exc_info.value.message == BLOCKED_MESSAGE

    def test_allowed_address_passes(self):
        assert normalize_email("ivan@ukr.net") == "ivan@ukr.net"

    def test_contact_cannot_be_created_with_such_an_email(self):
        with pytest.raises(ValidationError, match=BLOCKED_MESSAGE):
            Contact(name="Іван", email="ivan@mail.ru")

    def test_malformed_address_still_reports_the_format_error(self):
        # Заборона доменів не має перехоплювати звичайну помилку формату.
        with pytest.raises(ValidationError, match="не схоже на email"):
            normalize_email("не-пошта")
