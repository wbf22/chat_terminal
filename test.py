import sys
import tty
import termios
import shutil

def get_char():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

print("Press 'q' to quit.")
input = []
x = 0
y = 0


def new_line():
    sys.stdout.write(ch)
    y += 1

def to_next_line_start(width):
    sys.stdout.write(f"\x1b[{width}D")
    sys.stdout.write('\x1b[B')
    sys.stdout.flush()
    global x
    global y
    x = 0
    y += 1

while True:
    
    ch = get_char()
    if ch == '\r': ch = '\n'

    size = shutil.get_terminal_size()
    width = size.columns
    height = size.lines

    # esc chars
    if ch == '\x1b':
        next = get_char()
        # arrows
        if next == '[':
            direction = get_char()
            should_write = False
            # up
            if direction == 'A':
                if y != 0:
                    should_write = True
                    y -= 1
            # down
            elif direction == 'B':
                should_write = True
                y += 1
            # right
            elif direction == 'C':
                if x < width:
                    should_write = True
                    x += 1
                else:
                    to_next_line_start(width)
            # left
            elif direction == 'D':
                if x != 0:
                    should_write = True
                    x -= 1

            if should_write:
                sys.stdout.write(ch)
                sys.stdout.write(next)
                sys.stdout.write(direction)
    # new lines
    elif ch == '\n':
        new_line()
    # all other characters
    else:
        sys.stdout.write(ch)
        if (x < width):
            x += 1
        else:
            y += 1
            x = 1

    
    if ch == 'q':
        break