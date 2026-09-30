from datetime import date
from pathlib import Path

import pytest

from personal_assistant.core.errors import ConflictError, NotFoundError, ValidationError
from personal_assistant.core.repository import Repository
from personal_assistant.core.storage import JsonStore
from personal_assistant.features.tasks import service
from personal_assistant.features.tasks.models import Task, TaskStatus


@pytest.fixture
def repo(tmp_path: Path) -> Repository[Task]:
    return Repository(JsonStore(tmp_path / "tasks.json", Task))


@pytest.fixture
def filled(repo: Repository[Task]) -> Repository[Task]:
    service.create(repo, "Здати проєкт", "Фінальна версія", "01.09.2026")
    service.create(repo, "Полагодити баг", "Падає при старті", "01.01.2026")
    service.create(repo, "Купити молоко")
    return repo


class TestCreate:
    def test_starts_as_new(self, repo):
        assert service.create(repo, "Задача").status is TaskStatus.NEW

    def test_due_date_is_parsed(self, repo):
        assert service.create(repo, "Задача", due_date="01.09.2026").due_date == date(2026, 9, 1)

    def test_blank_title_rejected(self, repo):
        with pytest.raises(ValidationError):
            service.create(repo, "   ")

    def test_invalid_due_date_is_user_facing(self, repo):
        with pytest.raises(ValidationError):
            service.create(repo, "Задача", due_date="32.13.2026")

    def test_duplicate_titles_allowed(self, repo):
        service.create(repo, "Задача")
        service.create(repo, "Задача")
        assert len(repo) == 2


class TestResolve:
    def test_by_word(self, filled):
        assert service.resolve(filled, "Полагодити").title == "Полагодити баг"

    def test_by_identifier(self, filled):
        task = filled.all()[0]
        assert service.resolve(filled, task.short_id) is task

    def test_unknown(self, filled):
        with pytest.raises(NotFoundError, match="Задачу"):
            service.resolve(filled, "Немає")

    def test_ambiguous_lists_identifiers(self, repo):
        service.create(repo, "Задача")
        service.create(repo, "Задача")
        with pytest.raises(ConflictError, match="задачам"):
            service.resolve(repo, "Задача")


class TestStatus:
    def test_set_status_reports_change(self, filled):
        task = service.resolve(filled, "Купити")
        assert service.set_status(task, "done") is True
        assert service.set_status(task, "done") is False

    def test_ukrainian_synonym_accepted(self, filled):
        task = service.resolve(filled, "Купити")
        service.set_status(task, "в роботі")
        assert task.status is TaskStatus.IN_PROGRESS

    def test_unknown_status_is_user_facing(self, filled):
        task = service.resolve(filled, "Купити")
        with pytest.raises(ValidationError):
            service.set_status(task, "майже готово")

    def test_status_counts_skip_empty_statuses(self, filled):
        assert service.status_counts(filled) == [(TaskStatus.NEW, 3)]

    def test_status_counts_follow_declaration_order(self, filled):
        service.set_status(service.resolve(filled, "Купити"), "done")
        service.set_status(service.resolve(filled, "Полагодити"), "in_progress")
        assert [status for status, _ in service.status_counts(filled)] == [
            TaskStatus.NEW,
            TaskStatus.IN_PROGRESS,
            TaskStatus.DONE,
        ]


class TestDueDate:
    def test_set_and_clear(self, filled):
        task = service.resolve(filled, "Купити")
        service.set_due_date(task, "25.08.2026")
        assert task.due_date == date(2026, 8, 25)
        service.set_due_date(task, None)
        assert task.due_date is None

    def test_invalid_value_is_user_facing(self, filled):
        task = service.resolve(filled, "Купити")
        with pytest.raises(ValidationError):
            service.set_due_date(task, "колись")

    def test_overdue_lists_only_open_tasks(self, filled):
        today = date(2026, 6, 1)
        assert [t.title for t in service.overdue(filled, today)] == ["Полагодити баг"]

        service.set_status(service.resolve(filled, "Полагодити"), "done")
        assert service.overdue(filled, today) == []


class TestOrdering:
    def test_open_tasks_come_first(self, filled):
        service.set_status(service.resolve(filled, "Полагодити"), "done")
        titles = [task.title for task in service.listing(filled)]
        assert titles[-1] == "Полагодити баг"

    def test_open_tasks_are_sorted_by_due_date(self, filled):
        titles = [task.title for task in service.listing(filled)]
        assert titles[:2] == ["Полагодити баг", "Здати проєкт"]

    def test_tasks_without_due_date_go_last_in_their_group(self, filled):
        titles = [task.title for task in service.listing(filled)]
        assert titles[2] == "Купити молоко"

    def test_same_due_date_falls_back_to_the_alphabet(self, repo):
        service.create(repo, "Ялинка", due_date="01.09.2026")
        service.create(repo, "Іній", due_date="01.09.2026")
        service.create(repo, "Ґанок", due_date="01.09.2026")
        assert [t.title for t in service.listing(repo)] == ["Ґанок", "Іній", "Ялинка"]

    def test_filtering_by_status(self, filled):
        service.set_status(service.resolve(filled, "Купити"), "done")
        assert [t.title for t in service.listing(filled, TaskStatus.DONE)] == ["Купити молоко"]

    def test_filtering_with_no_matches(self, filled):
        assert service.listing(filled, TaskStatus.CANCELLED) == []


class TestSearchAndEditing:
    def test_search_covers_title_and_description(self, filled):
        assert [t.title for t in service.search(filled, "падає")] == ["Полагодити баг"]

    def test_blank_query_rejected(self, filled):
        with pytest.raises(ValidationError):
            service.search(filled, "  ")

    def test_edit_replaces_description(self, filled):
        task = service.resolve(filled, "Купити")
        service.edit(task, "2 літри")
        assert task.description == "2 літри"

    def test_rename_keeps_identifier(self, filled):
        task = service.resolve(filled, "Купити")
        original_id = task.id
        service.rename(task, "Купити кефір")
        assert task.title == "Купити кефір"
        assert task.id == original_id

    def test_rename_to_blank_rejected(self, filled):
        task = service.resolve(filled, "Купити")
        with pytest.raises(ValidationError):
            service.rename(task, "   ")

    def test_delete(self, filled):
        service.delete(filled, "Купити")
        assert len(filled) == 2
