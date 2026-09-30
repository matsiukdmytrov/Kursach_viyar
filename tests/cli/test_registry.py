import pytest

from personal_assistant.cli.registry import Registry


def _noop(_ctx, _args) -> str:
    return "ok"


@pytest.fixture
def registry() -> Registry:
    reg = Registry()
    reg.add("help", _noop, summary="Довідка", group="Загальні", aliases=("?",))
    reg.add("add contact", _noop, summary="Новий контакт", group="Контакти", usage="<ім'я>")
    reg.add("add note", _noop, summary="Нова нотатка", group="Нотатки")
    reg.add("list contacts", _noop, summary="Усі контакти", group="Контакти")
    return reg


class TestRegistration:
    def test_duplicate_name_is_a_programming_error(self, registry):
        with pytest.raises(ValueError, match="help"):
            registry.add("help", _noop, summary="…", group="Загальні")

    def test_alias_also_occupies_the_namespace(self, registry):
        with pytest.raises(ValueError):
            registry.add("?", _noop, summary="…", group="Загальні")

    def test_names_include_aliases(self, registry):
        assert "?" in registry.names()

    def test_groups_keep_registration_order(self, registry):
        assert list(registry.groups()) == ["Загальні", "Контакти", "Нотатки"]

    def test_signature_joins_name_and_usage(self, registry):
        command, _ = registry.resolve("add contact Іван")
        assert command.signature == "add contact <ім'я>"


class TestResolve:
    def test_prefers_the_longest_match(self, registry):
        command, args = registry.resolve("add contact Іван 0671234567")
        assert command.name == "add contact"
        assert args == ["Іван", "0671234567"]

    def test_single_word_command(self, registry):
        command, args = registry.resolve("help")
        assert command.name == "help"
        assert args == []

    def test_alias_resolves_to_the_same_command(self, registry):
        command, _ = registry.resolve("?")
        assert command.name == "help"

    def test_is_case_insensitive(self, registry):
        command, _ = registry.resolve("ADD Contact Іван")
        assert command.name == "add contact"

    @pytest.mark.parametrize("text", ["", "   ", "казна-що"])
    def test_unknown_input_returns_none(self, registry, text):
        assert registry.resolve(text) is None


class TestSuggest:
    def test_typo_yields_the_intended_command(self, registry):
        assert "help" in registry.suggest("hepl")

    def test_partial_command_suggests_continuations(self, registry):
        suggestions = registry.suggest("add")
        assert "add contact" in suggestions
        assert "add note" in suggestions

    def test_two_word_typo_is_matched(self, registry):
        assert "add contact" in registry.suggest("add contct Іван")

    def test_nothing_similar_gives_no_suggestions(self, registry):
        assert registry.suggest("zzzzzzzz") == []

    def test_respects_the_limit(self, registry):
        assert len(registry.suggest("add", limit=1)) == 1
