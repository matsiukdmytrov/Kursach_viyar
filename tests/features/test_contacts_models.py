from datetime import date, timedelta

import pytest
from pydantic import ValidationError as PydanticValidationError

from personal_assistant.core.errors import ValidationError
from personal_assistant.features.contacts.models import Contact, normalize_phone


class TestNormalizePhone:
    @pytest.mark.parametrize(
        "raw",
        ["0671234567", "067 123 45 67", "(067) 123-45-67", "+380671234567", "380671234567"],
    )
    def test_ukrainian_numbers_share_one_canonical_form(self, raw):
        assert normalize_phone(raw) == "+380671234567"

    def test_keeps_foreign_international_numbers(self):
        assert normalize_phone("+1 202 555 0123") == "+12025550123"

    @pytest.mark.parametrize("raw", ["", "   ", "телефон", "12345", "06712345678"])
    def test_rejects_unrecognisable_input(self, raw):
        with pytest.raises(ValidationError):
            normalize_phone(raw)

    @pytest.mark.parametrize("raw", ["+1234567", "+1234567890123456"])
    def test_rejects_international_numbers_of_wrong_length(self, raw):
        with pytest.raises(ValidationError, match="від 8 до 15"):
            normalize_phone(raw)

    def test_error_message_shows_examples(self):
        with pytest.raises(ValidationError, match="0671234567"):
            normalize_phone("12345")


class TestContactValidation:
    def test_name_is_required(self):
        with pytest.raises(PydanticValidationError):
            Contact(name="   ")

    def test_phones_are_stored_normalised(self):
        contact = Contact(name="Іван", phones=["067 123 45 67"])
        assert contact.phones == ["+380671234567"]

    def test_duplicate_phones_are_collapsed(self):
        contact = Contact(name="Іван", phones=["0671234567", "+380671234567"])
        assert contact.phones == ["+380671234567"]

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError, match="не схоже на email"):
            Contact(name="Іван", email="не-пошта")

    def test_our_validators_reach_the_user_unwrapped(self):
        # `ValidationError` успадковує Exception, а не ValueError, тому pydantic
        # не загортає його у власну помилку — текст доходить до CLI як є.
        with pytest.raises(ValidationError, match="немає жодної цифри"):
            Contact(name="Іван", phones=["абв"])

    def test_pydantics_own_checks_still_raise_its_error(self):
        with pytest.raises(PydanticValidationError):
            Contact(name="Іван", favorite="можливо")

    def test_valid_email_accepted(self):
        assert Contact(name="Іван", email="ivan@example.com").email == "ivan@example.com"

    def test_name_whitespace_is_collapsed(self):
        assert Contact(name="Іван\n\tПетренко").name == "Іван Петренко"

    def test_address_whitespace_is_collapsed(self):
        assert Contact(name="Іван", address="Львів,\nвул. Шевченка").address == (
            "Львів, вул. Шевченка"
        )

    def test_overlong_name_rejected(self):
        with pytest.raises(PydanticValidationError):
            Contact(name="Я" * 101)

    def test_name_at_the_limit_accepted(self):
        assert len(Contact(name="Я" * 100).name) == 100

    @pytest.mark.parametrize("name", ["John Smith", "José Ñuñez", "Łukasz", "12345", "!!!", "🙂"])
    def test_any_script_or_symbol_is_accepted_as_a_name(self, name):
        # Валідація імені навмисно ліберальна: ТЗ вимагає перевіряти телефон
        # та email, а не диктувати, з яких символів складається ім'я.
        assert Contact(name=name).name == name

    def test_blank_optional_fields_become_none(self):
        contact = Contact(name="Іван", email="", address="  ")
        assert contact.email is None
        assert contact.address is None

    def test_birthday_accepts_dd_mm_yyyy(self):
        assert Contact(name="Іван", birthday="07.03.1990").birthday == date(1990, 3, 7)

    def test_birthday_in_the_future_rejected(self):
        tomorrow = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
        with pytest.raises(PydanticValidationError):
            Contact(name="Іван", birthday=tomorrow)

    def test_favourite_defaults_to_false(self):
        assert Contact(name="Іван").favorite is False


class TestContactBehaviour:
    def test_has_phone_compares_normalised_values(self):
        contact = Contact(name="Іван", phones=["+380671234567"])
        assert contact.has_phone("067 123 45 67")

    def test_days_to_birthday_without_birthday_is_none(self):
        assert Contact(name="Іван").days_to_birthday() is None

    def test_days_to_birthday_counts_forward(self):
        contact = Contact(name="Іван", birthday="10.05.1990")
        assert contact.days_to_birthday(today=date(2026, 5, 1)) == 9

    def test_birthday_today_is_zero_days(self):
        contact = Contact(name="Іван", birthday="10.05.1990")
        assert contact.days_to_birthday(today=date(2026, 5, 10)) == 0

    @pytest.mark.parametrize("query", ["іван", "ІВАН", "ivan@example", "Львів"])
    def test_matches_searches_every_field(self, query):
        contact = Contact(name="Іван", email="ivan@example.com", address="Львів")
        assert contact.matches(query)

    def test_matches_finds_phone_typed_in_another_format(self):
        contact = Contact(name="Іван", phones=["+380671234567"])
        assert contact.matches("067 123 45 67")

    def test_empty_query_matches_nothing(self):
        assert not Contact(name="Іван").matches("  ")
