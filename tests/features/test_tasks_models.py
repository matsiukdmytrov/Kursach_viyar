from datetime import date

import pytest
from pydantic import ValidationError as PydanticValidationError

from personal_assistant.core.errors import ValidationError
from personal_assistant.features.tasks.models import Task, TaskStatus


class TestTaskStatus:
    def test_covers_exactly_the_statuses_from_the_spec(self):
        assert [s.value for s in TaskStatus] == ["new", "in_progress", "done", "cancelled"]

    def test_serialises_as_plain_string(self):
        assert TaskStatus.IN_PROGRESS == "in_progress"

    @pytest.mark.parametrize("raw", ["in_progress", "in-progress", "IN PROGRESS", " In_Progress "])
    def test_parse_accepts_loose_input(self, raw):
        assert TaskStatus.parse(raw) is TaskStatus.IN_PROGRESS

    def test_parse_rejects_unknown_and_lists_options(self):
        with pytest.raises(ValidationError, match="cancelled"):
            TaskStatus.parse("майже готово")

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (TaskStatus.NEW, True),
            (TaskStatus.IN_PROGRESS, True),
            (TaskStatus.DONE, False),
            (TaskStatus.CANCELLED, False),
        ],
    )
    def test_is_open(self, status, expected):
        assert status.is_open is expected


class TestTaskValidation:
    def test_title_is_required(self):
        with pytest.raises(PydanticValidationError):
            Task(title="  ")

    def test_defaults_to_new(self):
        assert Task(title="Купити хліб").status is TaskStatus.NEW

    def test_status_accepts_loose_string(self):
        assert Task(title="T", status="in-progress").status is TaskStatus.IN_PROGRESS

    def test_due_date_accepts_dd_mm_yyyy(self):
        assert Task(title="T", due_date="01.09.2026").due_date == date(2026, 9, 1)

    def test_due_date_accepts_a_date_object(self):
        assert Task(title="T", due_date=date(2026, 9, 1)).due_date == date(2026, 9, 1)

    def test_blank_due_date_becomes_none(self):
        assert Task(title="T", due_date="").due_date is None


class TestTaskBehaviour:
    def test_set_status_reports_change(self):
        task = Task(title="T")
        assert task.set_status("done") is True
        assert task.set_status(TaskStatus.DONE) is False
        assert task.status is TaskStatus.DONE

    def test_set_status_updates_timestamp(self):
        task = Task(title="T")
        before = task.updated_at
        task.set_status("done")
        assert task.updated_at >= before

    def test_overdue_open_task(self):
        task = Task(title="T", due_date="01.01.2026")
        assert task.is_overdue(today=date(2026, 2, 1))

    def test_closed_task_is_never_overdue(self):
        task = Task(title="T", due_date="01.01.2026", status="done")
        assert not task.is_overdue(today=date(2026, 2, 1))

    def test_task_without_due_date_is_never_overdue(self):
        assert not Task(title="T").is_overdue(today=date(2026, 2, 1))

    def test_empty_query_matches_nothing(self):
        assert not Task(title="Купити хліб").matches("  ")

    @pytest.mark.parametrize("query", ["хліб", "ХЛІБ", "магазин"])
    def test_matches_title_and_description(self, query):
        task = Task(title="Купити хліб", description="У магазині біля дому")
        assert task.matches(query)
