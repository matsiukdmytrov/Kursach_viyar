from pathlib import Path

import pytest

from personal_assistant.core.errors import ConflictError, NotFoundError, ValidationError
from personal_assistant.core.repository import Repository
from personal_assistant.core.storage import JsonStore
from personal_assistant.features.notes import service
from personal_assistant.features.notes.models import Note


@pytest.fixture
def repo(tmp_path: Path) -> Repository[Note]:
    return Repository(JsonStore(tmp_path / "notes.json", Note))


@pytest.fixture
def filled(repo: Repository[Note]) -> Repository[Note]:
    service.create(repo, "Зустріч з командою", "Обговорити реліз", ["робота"])
    service.create(repo, "Купити продукти", "хліб, молоко", ["дім"])
    service.create(repo, "Ідея для проєкту", tags=["робота"])
    return repo


class TestCreate:
    def test_returns_stored_note(self, repo):
        note = service.create(repo, "Зустріч")
        assert repo.require(note.id) is note

    def test_tags_are_normalised(self, repo):
        note = service.create(repo, "Зустріч", tags=["#Робота", "ДІМ"])
        assert note.tags == ["робота", "дім"]

    def test_blank_title_rejected(self, repo):
        with pytest.raises(ValidationError):
            service.create(repo, "   ")

    def test_duplicate_titles_are_allowed(self, repo):
        # На відміну від контактів: дві нотатки «Зустріч» — нормальна ситуація.
        service.create(repo, "Зустріч")
        service.create(repo, "Зустріч")
        assert len(repo) == 2

    def test_overlong_title_is_user_facing(self, repo):
        with pytest.raises(ValidationError):
            service.create(repo, "Я" * 200)


class TestResolve:
    def test_exact_title(self, filled):
        assert service.resolve(filled, "Купити продукти").title == "Купити продукти"

    def test_by_word(self, filled):
        assert service.resolve(filled, "Зустріч").title == "Зустріч з командою"

    def test_by_short_id(self, filled):
        note = filled.all()[0]
        assert service.resolve(filled, note.short_id) is note

    def test_unknown(self, filled):
        with pytest.raises(NotFoundError, match="Нотатку"):
            service.resolve(filled, "Немає")

    def test_ambiguous_candidates_include_identifiers(self, repo):
        # Самих заголовків тут замало — вони однакові.
        service.create(repo, "Зустріч")
        service.create(repo, "Зустріч")
        with pytest.raises(ConflictError) as exc_info:
            service.resolve(repo, "Зустріч")
        assert exc_info.value.message.count("[") == 2


class TestTags:
    def test_add_tag_returns_canonical_form(self, filled):
        note = service.resolve(filled, "Купити")
        assert service.add_tag(note, "#Важливе") == "важливе"

    def test_add_existing_tag_rejected(self, filled):
        note = service.resolve(filled, "Купити")
        with pytest.raises(ConflictError):
            service.add_tag(note, "ДІМ")

    def test_remove_tag(self, filled):
        note = service.resolve(filled, "Купити")
        assert service.remove_tag(note, "#Дім") == "дім"
        assert note.tags == []

    def test_remove_missing_tag(self, filled):
        note = service.resolve(filled, "Купити")
        with pytest.raises(NotFoundError):
            service.remove_tag(note, "робота")

    def test_invalid_tag_is_user_facing(self, filled):
        note = service.resolve(filled, "Купити")
        with pytest.raises(ValidationError):
            service.add_tag(note, "###")


class TestSearchAndFilter:
    def test_search_covers_title_text_and_tags(self, filled):
        assert [n.title for n in service.search(filled, "реліз")] == ["Зустріч з командою"]
        assert [n.title for n in service.search(filled, "молоко")] == ["Купити продукти"]
        assert len(service.search(filled, "робота")) == 2

    def test_blank_query_rejected(self, filled):
        with pytest.raises(ValidationError):
            service.search(filled, "  ")

    def test_by_tag_ignores_formatting(self, filled):
        assert len(service.by_tag(filled, "#РОБОТА")) == 2

    def test_by_tag_with_no_matches(self, filled):
        assert service.by_tag(filled, "невідомий") == []

    def test_tag_counts_are_alphabetical_and_correct(self, filled):
        assert service.tag_counts(filled) == [("дім", 1), ("робота", 2)]

    def test_tag_counts_on_empty_repository(self, repo):
        assert service.tag_counts(repo) == []


class TestOrdering:
    def test_listing_puts_recently_updated_first(self, filled):
        oldest = service.resolve(filled, "Зустріч")
        service.edit(oldest, "оновлений текст")
        assert service.listing(filled)[0] is oldest

    def test_sorted_by_tag_groups_by_first_tag(self, filled):
        titles = [note.title for note in service.sorted_by_tag(filled)]
        # #дім < #робота, а всередині #робота — за заголовком: «З» перед «І».
        assert titles == ["Купити продукти", "Зустріч з командою", "Ідея для проєкту"]

    def test_untagged_notes_go_last(self, repo):
        service.create(repo, "Без тегів")
        service.create(repo, "З тегом", tags=["робота"])
        assert [n.title for n in service.sorted_by_tag(repo)] == ["З тегом", "Без тегів"]

    def test_tag_order_follows_the_ukrainian_alphabet(self, repo):
        service.create(repo, "Я", tags=["ялинка"])
        service.create(repo, "І", tags=["іній"])
        service.create(repo, "Ґ", tags=["ґанок"])
        assert [n.title for n in service.sorted_by_tag(repo)] == ["Ґ", "І", "Я"]


class TestEditing:
    def test_edit_replaces_text(self, filled):
        note = service.resolve(filled, "Купити")
        service.edit(note, "новий текст")
        assert note.text == "новий текст"

    def test_edit_updates_timestamp(self, filled):
        note = service.resolve(filled, "Купити")
        before = note.updated_at
        service.edit(note, "новий текст")
        assert note.updated_at >= before

    def test_rename_keeps_identifier(self, filled):
        note = service.resolve(filled, "Купити")
        original_id = note.id
        service.rename(note, "Список покупок")
        assert note.title == "Список покупок"
        assert note.id == original_id

    def test_rename_to_blank_rejected(self, filled):
        note = service.resolve(filled, "Купити")
        with pytest.raises(ValidationError):
            service.rename(note, "   ")

    def test_delete(self, filled):
        service.delete(filled, "Купити")
        assert len(filled) == 2
