import curses
import os

def edit_input(stdscr, prompt="> "):
    curses.curs_set(1)  # Make cursor visible
    stdscr.clear()
    stdscr.addstr(0, 0, prompt)
    stdscr.refresh()

    input_chars = []  # List of characters for the current input
    cursor_pos = 0    # Cursor position within input_chars

    while True:
        # Display current input
        stdscr.move(0, len(prompt))
        stdscr.clrtoeol()  # Clear the current line after prompt
        stdscr.addstr(0, len(prompt), ''.join(input_chars))

        
        # Move cursor to the current position
        stdscr.move(0, len(prompt) + cursor_pos)
        stdscr.refresh()

        key = stdscr.getch()

        if key in (curses.KEY_ENTER, 10, 13):
            # Submit input
            break
        elif key == curses.KEY_LEFT:
            if cursor_pos > 0:
                cursor_pos -= 1
        elif key == curses.KEY_RIGHT:
            if cursor_pos < len(input_chars):
                cursor_pos += 1
        elif key == curses.KEY_BACKSPACE or key == 127:
            if cursor_pos > 0:
                del input_chars[cursor_pos - 1]
                cursor_pos -= 1
        elif key == curses.KEY_DC:
            # Delete key
            if cursor_pos < len(input_chars):
                del input_chars[cursor_pos]
        elif 32 <= key <= 126:
            # ASCII printable characters
            input_chars.insert(cursor_pos, chr(key))
            cursor_pos += 1
        # You can add more key handling here (e.g., Home, End)

    return ''.join(input_chars)

def main(stdscr):
    user_input = edit_input(stdscr, prompt="Type something: ")
    stdscr.clear()
    stdscr.addstr(0, 0, f"You typed: {user_input}")
    stdscr.getch()

if __name__ == "__main__":
    curses.wrapper(main)