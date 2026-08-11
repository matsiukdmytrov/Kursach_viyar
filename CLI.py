from __future__ import annotations

import os
import pickle

#import AddressBookEntity
import sys
from prompt_toolkit import prompt
from prompt_toolkit.clipboard import in_memory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import InMemoryHistory

from typing import Any, Callable, Dict, Generator, List, Set, Tuple

from subObjects.AddressBookEntity import AddressBook
import subObjects.AddressBookEntity as bookEntity


# Список слів для автодоповнення
#command_completer = WordCompleter([
#    'start', 'stop', 'restart', 'status', 'config', 'exit'
#], ignore_case=True)

#while True:
#    user_input = prompt('Введіть команду > ', completer=command_completer, auto_suggest=AutoSuggestFromHistory(), history=InMemoryHistory())
#    if user_input.strip() == 'exit':
#        break
#    print(f"Виконано: {user_input}")


#loc_address_book = subObjects.AddressBookEntity.AddressBook()

def main() -> None:
    book: AddressBook = AddressBook.load()

    COMMANDS = bookEntity.COMMANDS
    EXIT_COMMANDS = bookEntity.EXIT_COMMANDS

    command_completer = WordCompleter(list(COMMANDS.keys()),ignore_case=True)
        #['start', 'stop', 'restart', 'status', 'config', 'exit'
    #], ignore_case=True)

    contacts_count = len(book.data)
    print("Welcome to the Assistant Bot!")
    if contacts_count:
        print(f"Loaded {contacts_count} contact(s) from disk.")
    print("Type 'help' to see all available commands.\n")

    try:
        while True:
            user_input: str = prompt('Введіть команду > ', completer=command_completer, auto_suggest=AutoSuggestFromHistory(), history=InMemoryHistory())#input(">>> ")
            if not user_input.strip():
                continue
            command, args = bookEntity.parse_input(user_input)
            if command in EXIT_COMMANDS:
                print("Address book saved. Good bye!")
                break
            handler: Callable[[AddressBook, List[str]], str | None] | None = (
                COMMANDS.get(command)
            )
            if handler is None:
                print(
                    f"Unknown command '{command}'. Type 'help' to see available commands."
                )
            else:
                print(handler(book, args))
    except (KeyboardInterrupt, EOFError):
        print("\nInterrupted — saving address book...")
    finally:
        # Дані зберігаються за будь-якого сценарію виходу, включно з Ctrl+C
        book.save()

if __name__ == "__main__":
    main()