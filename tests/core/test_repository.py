from pathlib import Path
from uuid import UUID, uuid4

import pytest

from personal_assistant.core.errors import ConflictError, NotFoundError
from personal_assistant.core.repository import Repository
from personal_assistant.core.storage import JsonStore
from personal_assistant.features.notes.models import Note


@pytest.fixture
def repo(tmp_path: Path) -> Repository[Note]:
    return Repository(JsonStore(tmp_path / "notes.json", Note))


class TestCrud:
    def test_add_and_require(self, repo):
        note = repo.add(Note(title="Перша"))
        assert repo.require(note.id) is note

    def test_add_rejects_duplicate_id(self, repo):
        note = repo.add(Note(title="Перша"))
        with pytest.raises(ConflictError):
            repo.add(note)

    def test_require_missing_raises(self, repo):
        with pytest.raises(NotFoundError):
            repo.require(uuid4())

    def test_get_missing_returns_none(self, repo):
        assert repo.get(uuid4()) is None

    def test_delete_returns_removed_entity(self, repo):
        note = repo.add(Note(title="Перша"))
        assert repo.delete(note.id) is note
        assert len(repo) == 0

    def test_delete_missing_raises(self, repo):
        with pytest.raises(NotFoundError):
            repo.delete(uuid4())

    def test_all_preserves_insertion_order(self, repo):
        titles = ["Третя", "Перша", "Друга"]
        for title in titles:
            repo.add(Note(title=title))
        assert [note.title for note in repo.all()] == titles

    def test_supports_iteration_and_membership(self, repo):
        note = repo.add(Note(title="Перша"))
        assert list(repo) == [note]
        assert note.id in repo
        assert uuid4() not in repo

    def test_find_applies_predicate(self, repo):
        repo.add(Note(title="Робота", tags=["work"]))
        repo.add(Note(title="Дім"))
        found = repo.find(lambda note: note.has_tag("work"))
        assert [note.title for note in found] == ["Робота"]


class TestResolve:
    def test_finds_by_full_uuid(self, repo):
        note = repo.add(Note(title="Перша"))
        assert repo.resolve(str(note.id)) is note

    def test_finds_by_short_prefix(self, repo):
        note = repo.add(Note(title="Перша"))
        assert repo.resolve(note.short_id) is note

    def test_ignores_case(self, repo):
        note = repo.add(Note(title="Перша"))
        assert repo.resolve(note.short_id.upper()) is note

    def test_missing_prefix_raises(self, repo):
        repo.add(Note(title="Перша"))
        with pytest.raises(NotFoundError):
            repo.resolve("ffffffff")

    def test_empty_reference_raises(self, repo):
        with pytest.raises(NotFoundError):
            repo.resolve("   ")

    def test_ambiguous_prefix_raises_and_lists_candidates(self, repo):
        # Явні id зі спільним початком: покладатись на випадкові UUID не можна.
        repo.add(Note(id=UUID("abcdef00-0000-4000-8000-000000000001"), title="Перша"))
        repo.add(Note(id=UUID("abcdef00-0000-4000-8000-000000000002"), title="Друга"))

        with pytest.raises(ConflictError, match="abcdef00"):
            repo.resolve("abcdef")

    def test_full_uuid_is_unambiguous_even_with_shared_prefix(self, repo):
        wanted = repo.add(Note(id=UUID("abcdef00-0000-4000-8000-000000000001"), title="Перша"))
        repo.add(Note(id=UUID("abcdef00-0000-4000-8000-000000000002"), title="Друга"))

        assert repo.resolve(str(wanted.id)) is wanted


class TestPersistence:
    def test_saved_state_is_reloaded(self, tmp_path):
        store: JsonStore[Note] = JsonStore(tmp_path / "notes.json", Note)
        repo = Repository(store)
        repo.add(Note(title="Збережена"))
        repo.save()

        reloaded = Repository.from_store(store)
        assert [note.title for note in reloaded.all()] == ["Збережена"]

    def test_clear_empties_collection(self, repo):
        repo.add(Note(title="Перша"))
        repo.clear()
        assert repo.all() == []
