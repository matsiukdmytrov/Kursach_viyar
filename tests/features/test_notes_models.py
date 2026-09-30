import pytest
from pydantic import ValidationError as PydanticValidationError

from personal_assistant.core.errors import ValidationError
from personal_assistant.features.notes.models import Note, normalize_tag


class TestNormalizeTag:
    @pytest.mark.parametrize("raw", ["work", "#work", "Work", "  #WORK  "])
    def test_variants_collapse_to_one_tag(self, raw):
        assert normalize_tag(raw) == "work"

    def test_spaces_and_underscores_become_hyphens(self):
        assert normalize_tag("Робочі Справи") == "робочі-справи"
        assert normalize_tag("to_do") == "to-do"

    def test_keeps_cyrillic(self):
        assert normalize_tag("Дім") == "дім"

    @pytest.mark.parametrize("raw", ["", "#", "   ", "!!!"])
    def test_rejects_empty_result(self, raw):
        with pytest.raises(ValidationError):
            normalize_tag(raw)


class TestNoteValidation:
    def test_title_is_required(self):
        with pytest.raises(PydanticValidationError):
            Note(title="")

    def test_tags_are_normalised_on_creation(self):
        assert Note(title="N", tags=["#Work", "Дім"]).tags == ["work", "дім"]

    def test_tags_must_be_a_list(self):
        with pytest.raises(PydanticValidationError):
            Note(title="N", tags="work")

    def test_duplicate_tags_are_collapsed(self):
        assert Note(title="N", tags=["work", "#WORK"]).tags == ["work"]


class TestTags:
    def test_add_tag_returns_true_once(self):
        note = Note(title="N")
        assert note.add_tag("#Work") is True
        assert note.add_tag("work") is False
        assert note.tags == ["work"]

    def test_add_tag_updates_timestamp(self):
        note = Note(title="N")
        before = note.updated_at
        note.add_tag("work")
        assert note.updated_at >= before

    def test_remove_tag(self):
        note = Note(title="N", tags=["work", "дім"])
        assert note.remove_tag("#WORK") is True
        assert note.remove_tag("work") is False
        assert note.tags == ["дім"]

    def test_has_tag_ignores_formatting(self):
        assert Note(title="N", tags=["work"]).has_tag("#Work")


class TestSearchAndSort:
    @pytest.mark.parametrize("query", ["зустріч", "ЗУСТРІЧ", "реліз", "work"])
    def test_matches_title_text_and_tags(self, query):
        note = Note(title="Зустріч", text="Обговорити реліз", tags=["work"])
        assert note.matches(query)

    def test_empty_query_matches_nothing(self):
        assert not Note(title="Зустріч").matches("")

    def test_untagged_notes_sort_last(self):
        tagged = Note(title="A", tags=["work"])
        untagged = Note(title="B")
        assert sorted([untagged, tagged], key=lambda n: n.sort_key)[0] is tagged
