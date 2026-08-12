from __future__ import annotations
import re
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


# ===========================================================================
# ПАРСЕР ЛОКАЛЬНИЙ - відділяє перше слово - звернення до "блоку" ()
# ===========================================================================
def parse_input(user_input: str) -> Tuple[str,str]:
    parts: List[str] = user_input.strip().split()
    if not parts:
        return "",""

    if len(parts) < 2:
        return parts[0],""

    return parts[0],re.sub(rf"\b{parts[0]}\b\s*", "", user_input)#user_input.replace(parts[1],"")



def main() -> None:
    book: AddressBook = AddressBook.load()

    COMMANDS = bookEntity.COMMANDS
    EXIT_COMMANDS = bookEntity.EXIT_COMMANDS

    list_for_completer = ["AddressBook " + item for item in list(COMMANDS.keys())]
    list_for_completer = list_for_completer + list(EXIT_COMMANDS)

    completer = WordCompleter(list_for_completer)
    command_completer = WordCompleter(list_for_completer,ignore_case=True)

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
            rozdil, user_input_parsed = parse_input(user_input)

            if rozdil in EXIT_COMMANDS:
                print("Address book saved. Good bye!")
                sys.exit()  # break
            if rozdil == "AddressBook":
                bookEntity.working_module(user_input_parsed, book)
            #else:
            #   break
                #    command, args = bookEntity.parse_input(user_input_parsed)
                #if command in EXIT_COMMANDS:
                #    print("Address book saved. Good bye!")
                #    break
                #handler: Callable[[AddressBook, List[str]], str | None] | None = (
                #    COMMANDS.get(command)
                #)
                #if handler is None:
                #    print(
                #        f"Unknown command '{command}'. Type 'help' to see available commands."
                #    )
                #else:
            #    print(handler(book, args))
    except (KeyboardInterrupt, EOFError):
        print("\nInterrupted — saving address book...")
    finally:
        # Дані зберігаються за будь-якого сценарію виходу, включно з Ctrl+C
        book.save()

if __name__ == "__main__":
    main()