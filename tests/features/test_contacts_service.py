from datetime import date
from pathlib import Path

import pytest

from personal_assistant.core.errors import ConflictError, NotFoundError, ValidationError
from personal_assistant.core.repository import Repository
from personal_assistant.core.storage import JsonStore
from personal_assistant.features.contacts import service
from personal_assistant.features.contacts.models import Contact


@pytest.fixture
def repo(tmp_path: Path) -> Repository[Contact]:
    return Repository(JsonStore(tmp_path / "contacts.json", Contact))


@pytest.fixture
def book(repo: Repository[Contact]) -> Repository[Contact]:
    service.create(repo, "Іван Петренко", "0671234567")
    service.create(repo, "Марія Коваль")
    return repo


class TestCreate:
    def test_returns_stored_contact(self, repo):
        contact = service.create(repo, "Іван Петренко")
        assert repo.require(contact.id) is contact

    def test_normalises_the_phone(self, repo):
        contact = service.create(repo, "Іван", "067 123 45 67")
        assert contact.phones == ["+380671234567"]

    def test_blank_name_rejected(self, repo):
        with pytest.raises(ValidationError):
            service.create(repo, "   ")

    def test_invalid_phone_becomes_a_user_facing_error(self, repo):
        # Найважливіше: помилка pydantic не має протікати назовні.
        with pytest.raises(ValidationError):
            service.create(repo, "Іван", "не-номер")

    def test_duplicate_name_rejected_regardless_of_case(self, repo):
        service.create(repo, "Іван Петренко")
        with pytest.raises(ConflictError):
            service.create(repo, "іван петренко")


class TestResolve:
    def test_exact_name(self, book):
        assert service.resolve(book, "Іван Петренко").name == "Іван Петренко"

    def test_is_case_insensitive(self, book):
        assert service.resolve(book, "іван петренко").name == "Іван Петренко"

    def test_by_word_of_the_name(self, book):
        assert service.resolve(book, "Петренко").name == "Іван Петренко"

    def test_exact_name_wins_over_a_longer_neighbour(self, repo):
        service.create(repo, "Іван")
        service.create(repo, "Іванна Шевченко")
        assert service.resolve(repo, "Іван").name == "Іван"

    def test_word_match_wins_over_substring(self, repo):
        service.create(repo, "Іван Петренко")
        service.create(repo, "Іванна Шевченко")
        assert service.resolve(repo, "Іван").name == "Іван Петренко"

    def test_substring_used_when_no_word_matches(self, book):
        assert service.resolve(book, "овал").name == "Марія Коваль"

    def test_ambiguous_substring_lists_candidates(self, repo):
        service.create(repo, "Іван Петренко")
        service.create(repo, "Іванна Шевченко")
        with pytest.raises(ConflictError, match="Іванна Шевченко"):
            service.resolve(repo, "ван")

    def test_by_short_id(self, book):
        contact = book.all()[0]
        assert service.resolve(book, contact.short_id) is contact

    def test_unknown_reference(self, book):
        with pytest.raises(NotFoundError):
            service.resolve(book, "Ніхто")

    def test_blank_reference(self, book):
        with pytest.raises(NotFoundError):
            service.resolve(book, "  ")

    def test_hex_looking_name_still_found_by_name(self, repo):
        # 'Fedde' складається з hex-символів, але це ім'я, а не ідентифікатор.
        service.create(repo, "Fedde")
        assert service.resolve(repo, "Fedde").name == "Fedde"


class TestPhones:
    def test_add_phone_returns_canonical_form(self, book):
        contact = service.resolve(book, "Марія Коваль")
        assert service.add_phone(contact, "050 111 22 33") == "+380501112233"

    def test_add_existing_phone_rejected_in_any_format(self, book):
        contact = service.resolve(book, "Іван Петренко")
        with pytest.raises(ConflictError):
            service.add_phone(contact, "+380671234567")

    def test_invalid_phone_is_user_facing(self, book):
        contact = service.resolve(book, "Іван Петренко")
        with pytest.raises(ValidationError):
            service.add_phone(contact, "абв")

    def test_remove_phone(self, book):
        contact = service.resolve(book, "Іван Петренко")
        assert service.remove_phone(contact, "067 123 45 67") == "+380671234567"
        assert contact.phones == []

    def test_remove_missing_phone(self, book):
        contact = service.resolve(book, "Марія Коваль")
        with pytest.raises(NotFoundError):
            service.remove_phone(contact, "0501112233")


class TestFields:
    def test_set_email(self, book):
        contact = service.resolve(book, "Іван Петренко")
        service.set_field(contact, "email", "ivan@example.com")
        assert contact.email == "ivan@example.com"

    def test_invalid_email_is_user_facing(self, book):
        contact = service.resolve(book, "Іван Петренко")
        with pytest.raises(ValidationError):
            service.set_field(contact, "email", "не-пошта")

    def test_clearing_a_field(self, book):
        contact = service.resolve(book, "Іван Петренко")
        service.set_field(contact, "address", "Львів")
        service.set_field(contact, "address", None)
        assert contact.address is None

    def test_birthday_accepts_dd_mm_yyyy(self, book):
        contact = service.resolve(book, "Іван Петренко")
        service.set_field(contact, "birthday", "07.03.1990")
        assert contact.birthday == date(1990, 3, 7)

    def test_unknown_field_rejected(self, book):
        contact = service.resolve(book, "Іван Петренко")
        with pytest.raises(ValidationError):
            service.set_field(contact, "favorite", "так")


class TestRenameAndDelete:
    def test_rename(self, book):
        contact = service.resolve(book, "Іван Петренко")
        service.rename(book, contact, "Іван Коваленко")
        assert contact.name == "Іван Коваленко"

    def test_rename_keeps_the_identifier(self, book):
        contact = service.resolve(book, "Іван Петренко")
        original_id = contact.id
        service.rename(book, contact, "Іван Коваленко")
        assert contact.id == original_id

    def test_rename_to_an_existing_name_rejected(self, book):
        contact = service.resolve(book, "Іван Петренко")
        with pytest.raises(ConflictError):
            service.rename(book, contact, "Марія Коваль")

    def test_changing_only_the_case_is_allowed(self, book):
        contact = service.resolve(book, "Іван Петренко")
        service.rename(book, contact, "ІВАН ПЕТРЕНКО")
        assert contact.name == "ІВАН ПЕТРЕНКО"

    def test_rename_to_blank_rejected(self, book):
        contact = service.resolve(book, "Іван Петренко")
        with pytest.raises(ValidationError):
            service.rename(book, contact, "   ")

    def test_delete_removes_from_repository(self, book):
        service.delete(book, "Іван Петренко")
        assert len(book) == 1


class TestFavorites:
    def test_marking_and_unmarking(self, book):
        contact = service.resolve(book, "Іван Петренко")
        assert service.set_favorite(contact, favorite=True) is True
        assert service.set_favorite(contact, favorite=True) is False
        assert service.set_favorite(contact, favorite=False) is True

    def test_listing_is_alphabetical(self, book):
        for name in ("Іван Петренко", "Марія Коваль"):
            service.set_favorite(service.resolve(book, name), favorite=True)
        assert [c.name for c in service.favorites(book)] == ["Іван Петренко", "Марія Коваль"]

    def test_listing_puts_favorites_first(self, book):
        service.set_favorite(service.resolve(book, "Марія Коваль"), favorite=True)
        assert [c.name for c in service.listing(book)] == ["Марія Коваль", "Іван Петренко"]


class TestSearch:
    def test_finds_by_phone_in_another_format(self, book):
        assert [c.name for c in service.search(book, "067 123 45 67")] == ["Іван Петренко"]

    def test_finds_by_partial_name(self, book):
        assert [c.name for c in service.search(book, "коваль")] == ["Марія Коваль"]

    def test_blank_query_rejected(self, book):
        with pytest.raises(ValidationError):
            service.search(book, "   ")

    def test_no_matches_gives_empty_list(self, book):
        assert service.search(book, "zzzz") == []


class TestUpcomingBirthdays:
    @pytest.fixture
    def with_birthdays(self, repo):
        service.create(repo, "Сьогодні").birthday = date(1990, 5, 10)
        service.create(repo, "Через тиждень").birthday = date(1990, 5, 17)
        service.create(repo, "Через місяць").birthday = date(1990, 6, 10)
        service.create(repo, "Без дати")
        return repo

    def test_includes_today(self, with_birthdays):
        entries = service.upcoming_birthdays(with_birthdays, 7, today=date(2026, 5, 10))
        assert entries[0].contact.name == "Сьогодні"
        assert entries[0].days_left == 0

    def test_window_boundary_is_inclusive(self, with_birthdays):
        names = [
            e.contact.name
            for e in service.upcoming_birthdays(with_birthdays, 7, today=date(2026, 5, 10))
        ]
        assert names == ["Сьогодні", "Через тиждень"]

    def test_contacts_without_birthday_are_skipped(self, with_birthdays):
        entries = service.upcoming_birthdays(with_birthdays, 365, today=date(2026, 5, 10))
        assert "Без дати" not in [e.contact.name for e in entries]

    def test_sorted_by_days_left(self, with_birthdays):
        entries = service.upcoming_birthdays(with_birthdays, 60, today=date(2026, 5, 10))
        assert [e.days_left for e in entries] == sorted(e.days_left for e in entries)

    def test_reports_the_actual_celebration_date(self, with_birthdays):
        entries = service.upcoming_birthdays(with_birthdays, 7, today=date(2026, 5, 10))
        assert entries[0].when == date(2026, 5, 10)

    def test_negative_window_rejected(self, repo):
        with pytest.raises(ValidationError):
            service.upcoming_birthdays(repo, -1)

    def test_oversized_window_rejected(self, repo):
        with pytest.raises(ValidationError, match="365"):
            service.upcoming_birthdays(repo, 400)

    def test_zero_days_means_today_only(self, with_birthdays):
        entries = service.upcoming_birthdays(with_birthdays, 0, today=date(2026, 5, 10))
        assert [e.contact.name for e in entries] == ["Сьогодні"]
