"""Точка входу: `pa` або `python -m personal_assistant`."""

import sys

from personal_assistant.cli.app import run


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
