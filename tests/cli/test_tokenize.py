from personal_assistant.cli.registry import tokenize


class TestTokenize:
    def test_splits_on_whitespace(self):
        assert tokenize("add contact Іван") == ["add", "contact", "Іван"]

    def test_quoted_value_stays_one_token(self):
        assert tokenize('add contact "Іван Петренко"') == ["add", "contact", "Іван Петренко"]

    def test_single_quotes_work_too(self):
        assert tokenize("add contact 'Іван Петренко'") == ["add", "contact", "Іван Петренко"]

    def test_backslashes_are_preserved(self):
        # Шляхи Windows не мають руйнуватись — це знадобиться команді сортування файлів.
        assert tokenize(r"sort files C:\Users\name") == ["sort", "files", r"C:\Users\name"]

    def test_hash_is_not_a_comment(self):
        assert tokenize("add tag #work") == ["add", "tag", "#work"]

    def test_unbalanced_quote_falls_back_to_plain_split(self):
        assert tokenize('add contact "Іван') == ["add", "contact", '"Іван']

    def test_empty_string(self):
        assert tokenize("   ") == []
