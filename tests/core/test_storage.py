from pathlib import Path

import pytest

from personal_assistant.core.errors import StorageError
from personal_assistant.core.storage import JsonStore
from personal_assistant.features.notes.models import Note


@pytest.fixture
def store(tmp_path: Path) -> JsonStore[Note]:
    return JsonStore(tmp_path / "nested" / "notes.json", Note)


class TestLoad:
    def test_missing_file_gives_empty_list(self, store):
        assert store.load() == []

    def test_empty_file_gives_empty_list(self, store):
        store.path.parent.mkdir(parents=True)
        store.path.write_text("   ", encoding="utf-8")
        assert store.load() == []

    def test_corrupted_file_raises_with_path_in_message(self, store):
        store.path.parent.mkdir(parents=True)
        store.path.write_text("{not json", encoding="utf-8")
        with pytest.raises(StorageError, match=r"notes\.json"):
            store.load()


class TestSave:
    def test_round_trip_preserves_fields(self, store):
        note = Note(title="Зустріч", text="Обговорити реліз", tags=["Робота"])
        store.save([note])

        (restored,) = store.load()
        assert restored.id == note.id
        assert restored.title == "Зустріч"
        assert restored.tags == ["робота"]

    def test_creates_missing_directories(self, store):
        store.save([])
        assert store.path.exists()

    def test_writes_cyrillic_readably(self, store):
        store.save([Note(title="Нотатка")])
        assert "Нотатка" in store.path.read_text(encoding="utf-8")

    def test_leaves_no_temporary_file_behind(self, store):
        store.save([Note(title="Нотатка")])
        assert list(store.path.parent.glob("*.tmp")) == []

    def test_overwrites_previous_content(self, store):
        store.save([Note(title="Перша")])
        store.save([Note(title="Друга")])

        (only,) = store.load()
        assert only.title == "Друга"
