import sys

import pytest
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory

from personal_assistant.cli.app import _make_session, dispatch
from personal_assistant.cli.bootstrap import build_registry
from personal_assistant.cli.completion import DEFAULT_HINT, AssistantCompleter, make_toolbar
from personal_assistant.cli.registry import Registry
from personal_assistant.cli.signals import ExitRequested
from personal_assistant.core.errors import ValidationError


@pytest.fixture
def registry() -> Registry:
    return build_registry()


class TestDispatch:
    def test_blank_input_produces_no_output(self, registry, ctx):
        assert dispatch(registry, ctx, "   ") == ""

    def test_known_command_runs(self, registry, ctx):
        assert "help" in dispatch(registry, ctx, "hello")

    def test_help_lists_registered_commands(self, registry, ctx):
        output = dispatch(registry, ctx, "help")
        assert "hello" in output
        assert "exit" in output

    def test_help_for_one_command(self, registry, ctx):
        assert "Аліаси" in dispatch(registry, ctx, "help exit")

    def test_help_for_unknown_command_suggests(self, registry, ctx):
        assert "Можливо" in dispatch(registry, ctx, "help hepl")

    def test_unknown_command_suggests_correction(self, registry, ctx):
        output = dispatch(registry, ctx, "hepl")
        assert "Невідома команда" in output
        assert "help" in output

    def test_exit_signal_propagates(self, registry, ctx):
        with pytest.raises(ExitRequested):
            dispatch(registry, ctx, "exit")

    @pytest.mark.parametrize("alias", ["quit", "close", "good bye"])
    def test_exit_aliases(self, registry, ctx, alias):
        with pytest.raises(ExitRequested):
            dispatch(registry, ctx, alias)

    def test_user_facing_errors_are_shown_not_raised(self, registry, ctx):
        def failing(_ctx, _args):
            raise ValidationError("телефон некоректний")

        registry.add("boom", failing, summary="…", group="Тест")
        assert dispatch(registry, ctx, "boom") == "Помилка: телефон некоректний"

    def test_unexpected_errors_still_propagate(self, registry, ctx):
        def failing(_ctx, _args):
            raise RuntimeError("баг")

        registry.add("boom", failing, summary="…", group="Тест")
        with pytest.raises(RuntimeError):
            dispatch(registry, ctx, "boom")


class TestSessionWiring:
    """Проводка prompt_toolkit має бути живою, а не декларацією в коді."""

    def test_no_session_without_a_terminal(self, registry, ctx):
        # У пайпі та в тестах читаємо звичайним input().
        assert _make_session(ctx, registry) is None

    def test_session_uses_our_completer_and_toolbar(self, registry, ctx, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        session = _make_session(ctx, registry)

        assert session is not None
        assert isinstance(session.completer, AssistantCompleter)
        assert isinstance(session.auto_suggest, AutoSuggestFromHistory)
        assert callable(session.bottom_toolbar)

    def test_history_is_stored_next_to_the_data(self, registry, ctx, monkeypatch, settings):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        session = _make_session(ctx, registry)

        assert session is not None
        assert isinstance(session.history, FileHistory)
        assert str(settings.history_file) == session.history.filename

    def test_toolbar_reflects_the_registry(self, registry, ctx):
        toolbar = make_toolbar(registry)
        # Поза застосунком prompt_toolkit буфер порожній, тож бачимо типову підказку.
        assert toolbar() == DEFAULT_HINT
