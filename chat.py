




from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import subprocess
import json
import sys
import argparse
import http.client
import termios
import threading
import time
import difflib
import re
import tty
from typing import Optional


OPEN_AI = 'open_ai'
ANTHROPIC = 'anthropic'
models = [
    "gpt-5.4",
    "gpt-5-mini",
    "gpt-5-nano",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5"
]

# define arguments
parser = argparse.ArgumentParser(description="A terminal app for accessing chat gpt")
parser.add_argument('-ok', '--open_ai_api_key', help='Your open-api key created at https://platform.openai.com/api-keys')
parser.add_argument('-ak', '--anthropic_api_key', help='Your anthropic api key created at https://platform.claude.com/settings/keys')
parser.add_argument('-m', '--model', default='gpt-5-nano', help='The api model you\'ll access. View models here https://platform.openai.com/docs/models')
parser.add_argument('-a', '--api', default=OPEN_AI, help=f'Which api your model name is from. Currenlty only \'{OPEN_AI}\' and \'{ANTHROPIC}\' are supported.')
parser.add_argument('-nc', '--no_commands', action='store_true', help='disable the running of commands by assistants')
parser.add_argument('-g', '--no_git_commands', action='store_true', help='disable the running of git commands by assistants')

parser.add_argument('-d', '--dir', help='The directory in which the AI can execute commands and edit files. The currently directory by default.')

args = parser.parse_args()

API = args.api
MODEL = args.model
OPEN_AI_API_KEY = args.open_ai_api_key
ANTHROPIC_API_KEY = args.anthropic_api_key
NO_COMMANDS = args.no_commands
NO_GIT_COMMANDS = args.no_git_commands



def move_cursor_back(n):
    sys.stdout.write(f"\033[{n}D")
    sys.stdout.flush()

ANSII_RESET = '\033[0m'
def color_code(r: int, g: int, b: int) -> str:
    return f'\033[38;2;{r};{g};{b}m'


# colors
# - rgb(0, 0, 0)
# - rgb(238, 244, 212)
# - rgb(218, 239, 179)
# - rgb(234, 158, 141)
# - rgb(214, 69, 80)

user_color = color_code(218, 239, 179)
assistant_color = color_code(214, 69, 80)
temperature_color = color_code(238, 244, 212)
model_color = color_code(234, 158, 141)
output_color = color_code(82, 82, 82)
error_color = color_code(200, 0, 0)

FILE_PATH = 'chat.md'
MEMORY_FILE_PATH = 'chat.json'
ASSISTANT = 'assistant'
USER = 'user'
AUTO_DIRECTORY = os.getcwd() if args.dir == None else args.dir
NO_QUESTIONS_IN_AUTO_MODE = False
MAX_ACTIONS = 24
HISTORY_LENGTH = 10
CONVERSATION_SUMMARY_RATE = 10

def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        if select.select([sys.stdin], [], [], 0.1)[0]: # wait 0.1s
            return sys.stdin.read(1)
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def loading_indicator(response_future):
    
    # Hide the cursor
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    # loop showing elapsed time
    start = time.time()
    length = 0
    cancelled = False
    while not response_future.done():
        elapsed = f"{(time.time() - start):.1f}"
        elapsed += 's'
        sys.stdout.write('\r\x1b[K')
        sys.stdout.write(output_color + "(ESC to cancel) " + temperature_color + elapsed + ANSII_RESET)
        sys.stdout.flush()
        length = len(elapsed)
        c = getch()
        if c is not None:
            if c == '\x1b':  # ESC
                cancelled = True
                break
        

    # clear line
    sys.stdout.write('\r\x1b[K')
    sys.stdout.flush()

    # show cursor
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()

    return cancelled

def print_and_save_ai_message_to_history(ai_message, error):

    input_to_model.append(
        {
            "role": ASSISTANT,
            "content": ai_message,
        }
    )

    # print out response
    print_s(
        assistant_color + 'ASSISTANT' + ANSII_RESET, 
        '(', 
        model_color + MODEL + ANSII_RESET,
        ')'
    )
    print_s()
    if (error):
        print_s(error_color + ai_message + ANSII_RESET)
    else:
        print_s(ai_message)
    print_s()

def strip_ansi(text):
    n_text = re.sub(r'[\x1b\033]\[[0-9;]*[a-zA-Z]', "", text)
    return n_text

history = []
def print_s(
    *values: object,
    sep: Optional[str] = " ",
    end: Optional[str] = "\n",
    file: Optional[str] = None,
    flush: bool = False,
):
    history.append(sep.join(strip_ansi(str(v)) for v in values) + (end or ""))
    print(*values, sep=sep, end=end, flush=flush, file=file)

USER_TAG = 'YOU: (hit enter twice to submit, type help for special commands, type \'vim\' to edit your prompt with vim)'
def print_and_save_user_input_to_history():

    # get prompt
    user_input = ''
    while user_input == '':
        print_s(user_color + USER_TAG + ANSII_RESET)
        print_s()
        user_input = user_prompt()

    print_s()

    return user_input

def write_history(history):
    with open(FILE_PATH, 'w') as file:
        file.write("".join(history))
        file.write("\n")

using_memory = False
memory = []
def load_memory():
    global memory, input_to_model
    with open(MEMORY_FILE_PATH, 'r') as file:
        content = file.read()
        try:
            memory = json.loads(content)
        except ValueError as e:
            print_s(f"{error_color}Error loading memories from {MEMORY_FILE_PATH}:\n{e}")

        mems = '\n'.join(memory)
        input_to_model[0] = {
            "content": f"Memories (conversation notes):\n{mems}",
            "role": ASSISTANT,
        }

def add_and_write_memory(new_mem):
    global memory, input_to_model

    if using_memory:
        if new_mem is not None:
            memory.append(new_mem)

        # limit the size of memory to a few memories, saving the first memory which can potentially be the latest repo summary
        if len(memory) > 10:
            first_memory = memory[0]
            memory = [first_memory] + memory[-10:]

        # write to file
        json_str = json.dumps(memory, indent=4)
        with open(MEMORY_FILE_PATH, 'w') as file:
            file.write(json_str)

        mems = '\n'.join(memory)
        input_to_model.insert(
            0, 
            {
                "content": f"Memories (conversation notes):\n{mems}",
                "role": ASSISTANT,
            }
        )

def promp_ai_for_memory():
    global input_to_model

    print_s()
    print_s(f"{output_color}having ai store memory for conversation{ANSII_RESET}\n")
    input_to_model.append(
        {
            "content": f"SYSTEM: The user has requested you make a memory of the current conversation to be saved for your reference. Please output the most important things for you to remember in a one line summary.",
            "role": USER,
        }
    )
    outputs, error = call_api(include_functions=False)
    input_to_model = input_to_model[:-1]
    new_mem = ''
    if not error:
        new_mem = outputs[0]['text']
        print_s(f"{assistant_color}New memory:\n {new_mem}{ANSII_RESET}")
        
    else:
        print_s(f"{error_color} Error: {outputs}{ANSII_RESET}")
    
    print_s()

    return new_mem

def smart_input():
    # keeps reading lines until the user hits double enter
    lines = []
    while True:
        rlist, _, _ = select.select([sys.stdin], [], [], 0.01)
        line = sys.stdin.readline().rstrip("\n")
        if not rlist:
            if line == "":
                break
        if line[-1] == "\x1b":
            if line == "\x1b":
                print(f"\033[1A\033[K", flush=True)
            else:
                print(f"\033[1A\033[{len(line)-1}C\033[K", flush=True)
            line = line[:-1]
        lines.append(line)

    return "\n".join(lines)

auto_prompt = ""
actions = 0
def user_prompt():
    global auto_prompt, NO_QUESTIONS_IN_AUTO_MODE, AUTO_DIRECTORY, input_to_model, memory, using_memory, API, MODEL
    
    user_input = smart_input()

    if user_input.strip() == 'vim':

        # clear last two lines
        print_s('\x1b[1A', end="")
        print_s('\x1b[K', end="")
        print_s('\x1b[1A', end="")
        print_s('\x1b[K', end="")
        sys.stdout.flush()
        
        # load history into file
        # write_history(history)

        # open vim for user
        subprocess.run(['vim', '+', FILE_PATH])
        p = Path(FILE_PATH)
        content = ''
        if p.exists():
            with open(FILE_PATH, 'r') as file:
                content = file.read()
            os.remove(FILE_PATH)

        # parse out last user input and store in user_input
        # last_message_start = content.rfind(USER_TAG)
        # user_input = content[last_message_start+37:]
        user_input = content
        print_s(user_input)
    elif user_input.strip() == 'quit' or user_input == 'q':
        if using_memory and len(input_to_model) > 1:
            new_mem = promp_ai_for_memory()
            add_and_write_memory(new_mem)
        exit(0)
    elif user_input.strip() == "save":
        print_s()
        print_s(user_color + "Save conversation to 'chat.md'? (y/n) ", end='')
        user_input = input()
        print_s()
        if (user_input == 'y'):
            write_history(history)
        exit(0)
    elif user_input.strip() == "dir":
        print_s()
        print_s(f"{assistant_color}SET ASSISTANT SANDBOX DIRECTORY{ANSII_RESET}\n")
        print_s(f"{model_color}directory: {ANSII_RESET}")
        AUTO_DIRECTORY = input()
        while not os.path.isdir(AUTO_DIRECTORY):
            print_s(f"{error_color}not a directory{ANSII_RESET}")
            AUTO_DIRECTORY = input()
        
        print_s()
        print_s(f"Assistant now sandboxed to {AUTO_DIRECTORY}\n")

        user_input = ''
    elif user_input.strip() == "auto":
        user_input = set_auto_mode(True)
    elif user_input.strip() == "summarize":
        print_s()
        print_s(f"{assistant_color}SUMMARIZING A DIRECTORY!{ANSII_RESET}\n")
        directory = input("Enter a directory path to summarize. (by default the current directory is used): ")
        print_s()
        if directory == "": directory = AUTO_DIRECTORY
        summarize_repo(directory)
        user_input = ''
    elif user_input.strip() == "model":
        print_s()
        print_s(f"{assistant_color}CHANGE MODEL{ANSII_RESET}\n")
        models_list = []
        for i, model in enumerate(models):
            models_list.append(f"[{i}] {model}")
        models_list.append("""
(or enter specific model name)
Docs: https://developers.openai.com/api/docs/models/all, https://platform.claude.com/docs/en/about-claude/pricing
""")
        models_str = "\n".join(models_list)
        print_s(f"{assistant_color}{models_str}{ANSII_RESET}")
        model = input()
        try:
            ind = int(model)
            MODEL = models[ind]
            API = OPEN_AI if ind < 3 else ANTHROPIC
        except ValueError:
            MODEL = model
            print_s(f"{model_color}api:\n[0] {OPEN_AI} (chatgpt)\n[1] {ANTHROPIC} (cluade)\n{ANSII_RESET}")
            api = input()
            if api == "1":
                API = ANTHROPIC
            else:
                API = OPEN_AI

            print_s()


        print_s()
        print_s(f"{assistant_color}using {MODEL} on {API}{ANSII_RESET}\n")

        define_model_functions()

        user_input = ''
    elif user_input.strip() == "notes":
        print_s()
        print_s(f"{assistant_color}ASSISTANT'S NOTES (This is what the assistant has written down about the current conversation and represents what they remember):{ANSII_RESET}\n")
        print_s(conversation_summary)
        print_s()
        user_input = ''
    elif user_input.strip() == "memory":
        print_s()
        print_s(f"{assistant_color}SAVE MEMORY{ANSII_RESET}\n")
        print_s(f"{model_color}[0] have model save memory of what is currently going on \n[1] manually enter something for the AI to remember\n[2] list existing memories \n[3] cancel \n{ANSII_RESET}")
        choice = input()
        new_mem = None
        if choice == "0":
            new_mem = promp_ai_for_memory()
        elif choice == "1":
            print_s(f"{assistant_color}enter custom memory:\n{ANSII_RESET}")
            new_mem = input()
            print_s(f"{assistant_color}New memory:\n {new_mem}{ANSII_RESET}")
        elif choice == "2":
            for i, mem in enumerate(memory):
                print_s(f"[{i}] - {output_color}{mem}{ANSII_RESET}")

            print_s(f"{assistant_color}enter a memory number from the list above to delete it, or hit enter to finish\n{ANSII_RESET}")
            indices_to_remove = []
            to_delete = input()
            while to_delete != '':
                had_error = False
                try:
                    to_delete = int(to_delete)
                    if to_delete < len(memory):
                        indices_to_remove.append(to_delete)
                        print_s(f"{output_color}Removed: [{to_delete}] - {memory[to_delete]}{ANSII_RESET}")
                    else:
                        had_error = True
                except ValueError:
                    had_error = True

                if had_error:
                    print_s(f"{error_color}Not a valid number or not in list above: {to_delete}{ANSII_RESET}")

            memory = [v for i, v in enumerate(memory) if i not in indices_to_remove]

        if choice != '3':
            using_memory = True
            add_and_write_memory(new_mem)
        
        print_s()
        user_input = ''
    elif user_input.strip() == "context":
        for i, message in enumerate(input_to_model):
            role = message["role"]
            content = message["content"]
            print_s(f"[{i}] - {model_color}{role}\n{output_color}{content}{ANSII_RESET}\n")
        user_input = ''
    elif user_input.strip() == "usage":
        # https://platform.claude.com/claude-code
        print_s(f"{model_color}Some apis don't expose usage statistics, so you'll have to log into the api dashboards to see this unfortunetly. \n\n{output_color}https://platform.claude.com/cost\nhttps://platform.openai.com/usage{ANSII_RESET}\n")
        user_input = ''
    elif user_input.strip() == "help":
        print_s(model_color)
        print_s("Help:")
        print_s("- auto (give the ai a task or list of tasks and tell it to complete them before it responds again. The ai will be constrained to the current directory or the directory specified with --dir)")
        print_s("- vim (open vim for editing your response. Remember to quit with 'ESC + :wq'!)")
        print_s("- quit or q (quit chat)")
        print_s("- save (save your conversation to a file)")
        print_s("- summarize (have the assistant read through a repo and summarize it for you)")
        print_s("- model (switch model being used)")
        print_s("- dir (sandbox the model to a certain directory. By default the current directory is used)")
        print_s("- notes (This is what the assistant has written down about the current conversation and represents what they remember)")
        print_s("- memory (Make or manage memories stored in this repo for persistant context)")
        print_s("- context (Outputs the models context, showing what is sent with each request. This list is periodically summarized to avoid sending to much with each request.)")
        print_s("- usage (Links for seeing usage in api dashboards)")
        print_s(ANSII_RESET)

        user_input = ''


    return user_input

def has_paths_outside_cwd(command):
    path_pattern = r'(?:\/[\w.\-\/]+|[A-Za-z]:\\[\w.\-\\]+|\.{0,2}\/[\w.\-\/]+|\w[\w.\-]*\/[\w.\-\/]*)'
    
    def is_outside_cwd(match):
        path = match.group(0)

        # Skip URLs
        start = match.start()
        preceding = command[max(0, start-8):start]
        if '://' in command[max(0, start-8):match.end()] or preceding.lower().endswith(('http:', 'https:')):
            return False
        
        try:
            resolved = (Path(AUTO_DIRECTORY) / path).absolute()
            resolved.relative_to(Path(AUTO_DIRECTORY).absolute())
            return False  # inside AUTO_DIRECTORY
        except ValueError:
            return True  # outside AUTO_DIRECTORY
    
    matches = re.finditer(path_pattern, command)
    return any(is_outside_cwd(m) for m in matches)

def is_command_in_directory(command: str) -> bool:
    sandbox = Path(AUTO_DIRECTORY).resolve()
    
    # find anything that looks like a path
    paths = re.findall(r'(?:^|\s)(/[^\s;|&>]+)', command)
    
    for path in paths:
        try:
            resolved = Path(path).resolve()
            if sandbox != resolved and sandbox not in resolved.parents:
                return False
        except Exception:
            return False
    
    return True

def add_line_numbers(text, start=1, sep="| "):
    """
    Prefix each line with a line number.

    Example:
        hello
        world
    ->
        1: hello
        2: world
    """
    lines = text.splitlines(keepends=True)
    spaces = len(str(len(lines)))
    return "".join(f"{i}{" " * (spaces-len(str(i))) + sep}{line}" for i, line in enumerate(lines, start=start))

def remove_line_numbers(text, sep="| "):
    """
    Remove line numbers added by add_line_numbers.

    Handles:
        1: hello
        23: world
    """
    pattern = re.compile(rf"^\s*\d+\s*{re.escape(sep)}")

    lines = text.splitlines(keepends=True)
    return "".join(pattern.sub("", line) for line in lines)

def get_and_show_diff(old_lines, new_lines):

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile='before',
        tofile='after',
        lineterm=''
    )

    # ANSI colors
    RED = '\033[31m'
    GREEN = '\033[32m'
    CYAN = '\033[36m'
    RESET = '\033[0m'

    for line in diff:
        if line.startswith('+') and not line.startswith('+++'):
            print_s(f"{GREEN}{line}{RESET}", end='')
        elif line.startswith('-') and not line.startswith('---'):
            print_s(f"{RED}{line}{RESET}", end='')
        elif line.startswith('@@'):
            print_s(f"{CYAN}{line}{RESET}", end='')
        else:
            print_s(line, end='')

    return ''.join(diff)

def edit_lines(path, start_line, end_line, contents):
    start_line = int(start_line)
    end_line = int(end_line)
    
    with open(path, 'r') as f:
        old_lines = f.readlines()
    
    # split contents into lines, preserving newlines
    new_lines = contents.splitlines(keepends=True)
    
    # ensure last line has newline if original file did
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'
    
    # create updated version
    updated_lines = old_lines[:]
    updated_lines[start_line-1:end_line] = new_lines
    
    # write updated file
    with open(path, 'w') as f:
        f.writelines(updated_lines)

    # ---- pretty print diff ----
    return get_and_show_diff(old_lines, updated_lines)

last_ai_file_view = {}
def update_last_ai_file_view(path: Path):
    path_key = str(path.resolve())
    # update last known AI baseline
    last_ai_file_view[path_key] = time.time()

def file_edited_since_last_ai_edit(path: Path):
    global last_ai_file_view

    path_key = str(path.resolve())


    # If we've seen this file before
    was_edited = False
    if path_key in last_ai_file_view:
        ai_edit_time = last_ai_file_view[path_key]

        stat = os.stat(path_key)
        modified_time = stat.st_mtime  # keep everything in unix timestamps

        # external modification detected (1000ms after assuming there was a delay between this and saving)
        if modified_time > ai_edit_time + 1: 
            was_edited = True

    return was_edited

def summarize_repo(directory):
    global input_to_model, memory, using_memory

    prompt = f"""
The user has requested you help them summarize and understand a directory they're working in: '{directory}' 
Look around that directory and get familiar with it. Then provide the user with a summary
with the most important details.

Your current directory: '{AUTO_DIRECTORY}'
    """
    input_to_model.append(
        {
            "content": prompt,
            "role": USER,
        }
    )
    done = False
    while not done:
        outputs, error = call_api()
        for output in outputs:
            type = output['type']
            if type == "text":
                # print ai message
                message = output['text']
                print_and_save_ai_message_to_history(message, False)

                # save as first memory
                using_memory = True
                memory.insert(0, message)
                add_and_write_memory(None)
                done = True

            elif type == "tool_use":
                name = output['name']
                args = output['input']
                tool_use_id = output['id']
                handle_function_call(name, args, tool_use_id, output)


    
def check_for_max_actions():
    global actions
    if actions > MAX_ACTIONS:
        print_s(f"{output_color}The assistant has made {actions} requests on this task. Would you like them to continue? (y/n){ANSII_RESET}")
        if input() == 'n':
            return False
        else:
            actions = 0    
    
    return True

def make_file_change_ai_message(p:Path):

    print_s(f"{error_color}The assistant hasn't seen the file since the most recent edits. Sending that now...{ANSII_RESET}")
    print_s()
    file_c = None
    with open(p, 'r') as file:
        file_c = file.read()
    file_c = add_line_numbers(file_c)
    return f"This file was edited since you last saw it, so your most recent edit won't be applied. New contents: \n\n{file_c}"

class TalkProcess:

    _master = 0
    _process = None


    def __init__(self, command, cwd) -> tuple[int, subprocess.Popen]:
        # kill last process if running
        if not self.is_finished():
            self.kill()
        
        # set up file descriptors and start process
        self._master, slave = pty.openpty()
        self._process = subprocess.Popen(
            command,
            cwd=cwd,
            shell=True,
            stdin=slave,
            stdout=slave,
            stderr=slave
        )

    def get_output(self) -> str:
        output = []
        while True:
            if select.select([self._master], [], [], 1)[0]:
                try:
                    chunk = os.read(self._master, 1024).decode()
                    output.append(chunk)
                except OSError:
                    break  # process has ended
            else:
                break  # no output, waiting for input

        return "".join(output)

    def send_input(self, user_input: str):
        os.write(self._master, (user_input + "\n").encode())

    def kill(self):
        if self._process != None:
            self._process.kill()

    def is_finished(self):
        return self._process != None and self._process.poll() != None

tools = []
def define_model_functions():
    global tools
    
    params_name = 'parameters' if API == OPEN_AI else 'input_schema'

    tools = [
        {
            "name": "run_command",
            "description": "Run a command in the working directory. (Avoid git commands or other more dangerous commands unless the user gives permission)",
            params_name: {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Command string with args"
                    }
                },
                "required": ["command"]
            }
        },
        {
            "name": "list_running_commands",
            "description": "If you launch multiple commands at once, this is useful to see how many commands are running"
        },
        {
            "name": "done",
            "description": "Sometimes the user may indicate they want you to complete a task without asking questions such as building and testing a program. Use this command to indicate you have finished a task like that. Not necessary for normal back and forth conversation.",
            params_name: {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "What you want to say to the user now that you're done"
                    }
                },
                "required": ["text"]
            }
        },
        {
            "name": "kill_command",
            "description": "Kill a command/process that is running. If multiple are running then the most recent command is killed",
            params_name: { "type": "object", "properties": {}}
        },
        {
            "name": "command_input",
            "description": "Send input to a currently running command/process",
            params_name: {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "input to be sent to currently running command"
                    }
                },
                "required": ["input"]
            }
        },
        {
            "name": "ls",
            "description": "List the files in a directory",
            params_name: {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory, e.g. /myfolder Use '.' or an empty string to see what's in the current directory"
                    }
                },
                "required": ["path"]
            }
        },
        {
            "name": "cat",
            "description": "Get the current contents of a file",
            params_name: {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file, e.g. /myfolder/myfile.txt"
                    }
                },
                "required": ["path"]
            }
        },
        {
            "name": "edit_lines",
            "description": "Replace lines with new content in a file",
            params_name: {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file, e.g. /myfolder/myfile.txt"
                    },
                    "start_line": {
                        "type": "string",
                        "description": "The start line to replace (inclusive)"
                    },
                    "end_line": {
                        "type": "string",
                        "description": "The end line to replace (exclusive)"
                    },
                    "contents": {
                        "type": "string",
                        "description": "The data that will replace the contents between 'start_line' and 'end_line'"
                    }
                },
                "required": ["path", "start_line", "end_line", "contents"]
            }
        },
        {
            "name": "write_file",
            "description": "Overwrite a file with new contents. Always provide the complete file contents in the 'contents' field — this field is mandatory and must never be omitted.",
            params_name: {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file, e.g. /myfolder/myfile.txt"
                    },
                    "contents": {
                        "type": "string",
                        "description": "The data that will replace the contents of the file"
                    }
                },
                "required": ["path", "contents"]
            }
        },
        {
            "name": "delete",
            "description": "Delete a file or folder (with it's contents)",
            params_name: {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory, e.g. /myfolder"
                    }
                },
                "required": ["path"]
            }
        },
        {
            "name": "add_memory",
            "description": "If you would like to write something down to remember, you can do so with this function. Your memories will be returned to you with each request.",
            params_name: {
                "type": "object",
                "properties": {
                    "memory": {
                        "type": "string",
                        "description": "What you'd like to remember"
                    }
                },
                "required": ["memory"]
            }
        }
    ]

    if NO_COMMANDS:
        tools = tools[1:]

    if API == OPEN_AI:
        for tool in tools:
            tool['type'] = 'function'

def set_auto_mode(set_on: bool, ai_done_response=''):
    global auto_prompt, NO_QUESTIONS_IN_AUTO_MODE, actions
    user_res = None
    if set_on:
        NO_QUESTIONS_IN_AUTO_MODE = True

        print_s(f'{model_color}In auto mode! Your ai helper will iterate in this directory until it believes it has achieved the goal you provide it. Once started, the model will continue it achieves it\'s goal or hits the max attempts limit{ANSII_RESET}')
        print_s()
        # MAX_ACTIONS = input(f"{user_color}Max api usage (number of requests)\n{ANSII_RESET}")
        # MAX_ACTIONS = int(MAX_ACTIONS)

        print_s(f"{user_color}Task for ai:{ANSII_RESET}")
        user_input = user_prompt()

        auto_prompt = f"""
You're working in a loop to complete the following user prompt:
{user_input}

You can call the provided functions to run commands, explore your sandboxed directory, and create
and edit files. We'll handle paths as relative to your sandboxed directory. The user won't respond to
you until you're done. 

Make sure to call the 'done' function to indicate you've finished.
        """
        user_res = auto_prompt

    else:
        NO_QUESTIONS_IN_AUTO_MODE = False
        auto_prompt = ''
        print_and_save_ai_message_to_history(ai_done_response, False)
        user_res = print_and_save_user_input_to_history()

    actions = 0

    return user_res

def convert_to_open_ai(input_to_model) -> list:
    open_ai_input_to_model = []
    for message in input_to_model:
        # normal messages
        if isinstance(message['content'], str):
            open_ai_input_to_model.append(message)
        # tools/functions
        else:
            for item in message['content']:
                if item["type"] == "tool_use":
                    new_message = {
                        "type": "function_call",
                        "call_id": item["id"],
                        "name": item['name'],
                        "arguments": json.dumps(item['input'])
                    }
                    open_ai_input_to_model.append(new_message)
                # tools/function result
                elif item["type"] == "tool_result":
                    new_message = {
                        "type": "function_call_output",
                        "call_id": item["tool_use_id"],
                        "output": item['content']
                    }
                    open_ai_input_to_model.append(new_message)

    return open_ai_input_to_model

def add_function_result(tool_use_id, tool_use, result):
    input_to_model.append(
        {
            "role": ASSISTANT,
            "content": [
                tool_use
            ]
        }
    )
    input_to_model.append(
        {
            "role": USER,
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result
                }
            ]
        }
    )

def print_function_call_info(name, args, tool_use_id):
    print_s(f"{model_color}{name} {json.dumps(args)[:64]}... {tool_use_id}{ANSII_RESET}")
    print_s()

def handle_function_call(name, args, tool_use_id, tool_use):
    global NO_QUESTIONS_IN_AUTO_MODE, memory

    print_function_call_info(name, args, tool_use_id)

    # handle each command
    if name == 'done':
        add_function_result(tool_use_id, tool_use, "prompt has been marked as completed. You can now ask the user questions")
        user_res = set_auto_mode(False, args['text'])
        input_to_model.append(
            {
                "content": user_res,
                "role": USER,
            }
        )
    elif name == "run_command":
        command = args.get('command')
        command = command if command != None else ''

        allow = True
        deny_reason = ""
        if (has_paths_outside_cwd(command)):
            print_s(f"{model_color}The assistant is trying to run a command outside the set directory '{command}'. Do you want to allow it (y/n)?: {ANSII_RESET}", end="")
            allow = input() == 'y'
            add_function_result(tool_use_id, tool_use, f"The user was prompted and has denied your request to run a command outside the sandboxed directory.")
            deny_reason = "that was was going to be run outside directory"
        elif NO_GIT_COMMANDS and "git" in command:
            add_function_result(tool_use_id, tool_use, f"The user has diabled git commands and your command '{command}' appears to be one. Please don't use git commands")
            allow = False
            deny_reason = "that looked like a git command"
        
        if allow:
            input_function_loop(command, tool_use_id, tool_use)
        else:
            print_s(f"{output_color}denied command {deny_reason}{ANSII_RESET}\n")
    elif name == "list_running_commands":
        result = "\n".join([command for _, command in running_commands])
        print_s(f"{output_color}{result}{ANSII_RESET}")
        print_s()
        add_function_result(tool_use_id, tool_use, result)
    elif name == "ls":
        path = args.get('path')
        path = path if path != None else ''

        cmd = f"ls -la {path}"
        p_result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        result = f'{p_result.stdout}\n{p_result.stderr}'
        print_s(f"{output_color}{result}{ANSII_RESET}")
        print_s()
        add_function_result(tool_use_id, tool_use, result)
    elif name == "cat":
        path = args.get('path')
        path = path if path != None else ''
        p = Path(path)

        result = 'file does not exist'
        if p.exists():
            file_c = ''
            with open(p, 'r') as file:
                file_c = file.read()
            result = add_line_numbers(file_c)

        print_s(f"{output_color}{result[:256]}\n...{ANSII_RESET}")
        print_s()
        update_last_ai_file_view(p)
        add_function_result(tool_use_id, tool_use, result)
    elif name == "write_file":
        path = args.get('path')
        contents = args.get('contents')
        path = path if path != None else ''
        contents = remove_line_numbers(contents) if contents != None else ''

        p = Path(path)
        result = None
        if file_edited_since_last_ai_edit(p):
            result = make_file_change_ai_message(p)
        else:
            # get current lines
            old_lines = []
            if p.exists():
                with open(path, 'r') as f:
                    old_lines = f.readlines()

            # write file
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(contents)

            # show diff
            new_lines = contents.split("\n")
            result = get_and_show_diff(old_lines, new_lines)
            print_s()

        update_last_ai_file_view(p)
        add_function_result(tool_use_id, tool_use, result)
    elif name == "edit_lines":
        path = args.get('path')
        start_line = args.get('start_line')
        end_line = args.get('end_line')
        contents = args.get('contents')
        contents = remove_line_numbers(contents) if contents != None else ''
        p = Path(path)
        result = ""
        if p.exists():
            if file_edited_since_last_ai_edit(p):
                result = make_file_change_ai_message(p)
            else:
                result = edit_lines(p, start_line, end_line, contents)
                print_s()
            update_last_ai_file_view(p)
        else:
            result = "file does not exist"
            print_s(f"{error_color}{result}{ANSII_RESET}")
        add_function_result(tool_use_id, tool_use, result)
    elif name == "delete":
        path = args.get('path')
        path = path if path != None else ''

        p = Path(path)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
        result = f"deleted {path}"
        print_s(f"{output_color}{result}{ANSII_RESET}")
        print_s()
        add_function_result(tool_use_id, tool_use, result)
    elif name == "add_memory":
        mem = args["memory"]
        add_and_write_memory(mem)
        print_s(f"{output_color}{mem}{ANSII_RESET}")
        print_s()
        add_function_result(tool_use_id, tool_use, mem)
    else:
        result = "That's not a command or doesn't make sense in this context"
        print_s(f"{output_color}{result}{ANSII_RESET}")
        print_s()
        add_function_result(tool_use_id, tool_use, result)

    return input_to_model

running_commands = {}
def input_function_loop(command, tool_use_id, tool_use):
    global actions, input_to_model, running_commands
    
    # start process
    process = None
    output = None
    process = TalkProcess(command, AUTO_DIRECTORY)
    output = process.get_output()
    print_s(f"{output_color}{output}{ANSII_RESET}\n")

    add_function_result(tool_use_id, tool_use, output)
    if not process.is_finished():
        running_commands[process] = command
    
    while process != None and not process.is_finished():

        # prompt user if max_actions has been hit
        should_continue = check_for_max_actions()
        if not should_continue:
            msg = "The user has requested you stop. Please ask them for further instructions"
            input_to_model.append(
                {
                    "content": msg,
                    "role": USER,
                }
            )
            break

        # break out if process is finished
        actions += 1
        if process.is_finished(): break

        # otherwise send output to model
        outputs, error = call_api()

        # handle ai response
        if not error:
            for output in outputs:
                type = output['type']
                if type == "tool_use":

                    name = output['name']
                    tool_use_id = output['id']
                    args = output['input']
                    if name == "command_input":
                        print_function_call_info(name, args, tool_use_id)
                        ai_input = args['input']

                        # send ai input
                        process.send_input(ai_input)
                        print_s(f"{model_color}{ai_input}{ANSII_RESET}\n")

                        # add process output to response for ai
                        result = process.get_output()
                        print_s(f"{output_color}{result}{ANSII_RESET}\n")
                        add_function_result(tool_use_id, output, result)

                    elif name == "kill_command":
                        print_function_call_info(name, args, tool_use_id)
                        command_name = running_commands.pop(process, 0)
                        if not process.is_finished():
                            process.kill()
                        add_function_result(tool_use_id, output, f"Process was killed: {command_name}")
                    else:
                        handle_function_call(name, args, tool_use_id, output)

                else:
                    command_name = running_commands.pop(process, 0)
                    if not process.is_finished():
                        process.kill()

                    message = output['text']
                    print_and_save_ai_message_to_history(message, False)

                    msg = f"Right now you have a command running '{command_name}' and it's waiting for your input. Since you sent a message we'll assume you're done and kill the command."
                    input_to_model.append(
                        {
                            "content": msg,
                            "role": USER,
                        }
                    )

            

        else:
            input_to_model.append(
                {
                    "content": outputs,
                    "role": USER,
                }
            )

    if process != None and not process.is_finished(): process.kill()

input_to_model = []
def prompt_ai_to_update_notes_and_shrink_history():
    global input_to_model


    if len(input_to_model) > HISTORY_LENGTH + CONVERSATION_SUMMARY_RATE:

        # ask model to add to it's notes
        print_s(f"{output_color}Summarizing a few older messages in conversation to save on tokens...{ANSII_RESET}")
        input_to_model.append(
            {
                "content": f"SYSTEM: We're about to drop the last {CONVERSATION_SUMMARY_RATE} messages in this conversation. Please output any important information from older messages that might be lost.",
                "role": USER,
            }
        )
        outputs, error = call_api(include_functions=False)

        # delete that request from the conversation
        input_to_model = input_to_model[:-1]

        # add model response as first message along with memories
        if not error and len(outputs) != 0:
            summary = outputs[0]['text']
        
            # make sure we don't delete tool calls to function output we still have
            new_length = HISTORY_LENGTH
            i = len(input_to_model) - 1
            tool_results = set()
            while i >= 0:
                content = input_to_model[i]["content"]
                if isinstance(content, list):
                    for call in content:
                        if call["type"] == "tool_result":
                            tool_results.add(call["tool_use_id"])
                        if call["type"] == "tool_use":
                            tool_results.remove(call['id'])
                    
                if len(input_to_model) - i >= HISTORY_LENGTH and len(tool_results) == 0:
                    new_length = len(input_to_model) - i
                    break;
                i-=1

            input_to_model = input_to_model[-new_length:]
            add_and_write_memory(summary)

        print_s()

def call_api(include_functions=True):
    global request_done, input_to_model

    conn = None
    body = None
    if API == OPEN_AI:

        if include_functions:
            body = json.dumps({
                "model": MODEL,
                "input": convert_to_open_ai(input_to_model),
                "tools": tools,
                "tool_choice": "auto" if API == OPEN_AI else {"type":"auto"}
            })
        else:
            body = json.dumps({
                "model": MODEL,
                "input": convert_to_open_ai(input_to_model)
            })

        conn = http.client.HTTPSConnection("api.openai.com")
        conn.request(
            "POST", 
            "/v1/responses", 
            body=body, 
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + OPEN_AI_API_KEY
            }
        )
    else:
        if include_functions:
            body = json.dumps({
                "model": MODEL,
                "max_tokens": 64000,
                "messages": input_to_model,
                "tools": tools,
                "tool_choice": "auto" if API == OPEN_AI else {"type":"auto"}
            })
        else:
            body = json.dumps({
                "model": MODEL,
                "max_tokens": 1024,
                "messages": input_to_model
            })
        conn = http.client.HTTPSConnection("api.anthropic.com")
        conn.request(
            "POST", 
            "/v1/messages", 
            body=body, 
            headers={
                'Content-Type': 'application/json',
                'X-Api-Key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01'
            }
        )
        
    output = None
    ex = ThreadPoolExecutor()
    future = ex.submit(conn.getresponse)
    
    cancelled = loading_indicator(future)
    if not cancelled:
        response = future.result()
        error = False
        if response.status == 200:
            data = response.read()
            response_body = json.loads(data)
            if API == OPEN_AI:
                output = []
                for output_s in response_body['output']:
                    if output_s['type'] == 'message':
                        output.append(
                            {
                                "type": "text",
                                "role": output_s['role'],
                                "text": output_s['content'][0]['text']
                            }
                        )
                    elif output_s['type'] == 'function_call':
                        output.append(
                            {
                                "type": "tool_use",
                                "id": output_s['call_id'],
                                "name": output_s['name'],
                                "input": json.loads(output_s['arguments'])
                            }
                        )
            else:
                output = response_body['content']
                
        else:
            output = f"Error: {response.status} - {response.read().decode()}{ANSII_RESET}"
            error = True
    else:
        last_type = input_to_model[-1]["role"]
        content = input_to_model[-1]["content"]
        if last_type == USER and isinstance(content, str):
            input_to_model = input_to_model[:-1]
        output = "cancelled"
        error = True


    conn.close()
    ex.shutdown(wait=False)
    return output, error

stop = threading.Event()
def auto_mode_loop(max_attempts=100):
    global actions, input_to_model, conversation_summary

    # ai loop
    user_input = print_and_save_user_input_to_history()
    input_to_model.append(
        {
            "content": user_input,
            "role": USER,
        }
    )
    while actions < max_attempts:

        # prompt ai and handle response
        outputs, error = call_api()
        actions += 1
        if not error:

            # sort so that run command function calls are the last to run
            outputs.sort(key=lambda x: x.get("name") == "run_test_command" or x.get("name") == "run_command")
            
            # handle ai commands and messages
            for output in outputs:
                type = output['type']
                if type == "text":
                    if NO_QUESTIONS_IN_AUTO_MODE:
                        print_s(f"{error_color}rejected message since prompt has not been completed{ANSII_RESET}")
                        print_and_save_ai_message_to_history(output['text'], False)
                        input_to_model.append(
                            {
                                "content": "The user has asked you complete this prompt without asking questions. Just complete the prompt with your best guess on the users' intentions and call the 'done' function when finished.",
                                "role": USER,
                            }
                        )
                    else:
                        # print ai message
                        message = output['text']
                        print_and_save_ai_message_to_history(message, False)

                        # update conversaion summary if conversation is getting long
                        prompt_ai_to_update_notes_and_shrink_history()

                        # prompt user
                        user_res = print_and_save_user_input_to_history()
                        input_to_model.append(
                            {
                                "content": user_res,
                                "role": USER,
                            }
                        )
                        actions = 0
                elif type == "tool_use":
                    name = output['name']
                    args = output['input']
                    tool_use_id = output['id']
                    handle_function_call(name, args, tool_use_id, output)
        else:
            message = outputs
            print_and_save_ai_message_to_history(message, error)

            # prompt user
            user_res = print_and_save_user_input_to_history()
            input_to_model.append(
                {
                    "content": user_res,
                    "role": USER,
                }
            )


        # ask for prompt to continue after max attempts
        if NO_QUESTIONS_IN_AUTO_MODE:
            should_continue = check_for_max_actions()
            if not should_continue:
                user_res = set_auto_mode(False, "CANCEL JOB")
                input_to_model.append(
                    {
                        "content": user_res,
                        "role": USER,
                    }
                )



# START
if OPEN_AI_API_KEY is None and ANTHROPIC_API_KEY is None:
    print(f"{error_color}You need to provide an api key to continue. Run with '--help' to see how to provide an api key{ANSII_RESET}")
    exit(1)

if OPEN_AI_API_KEY is None:
    API = ANTHROPIC
elif ANTHROPIC_API_KEY is None:
    API = OPEN_AI

# set up model functions based on api
define_model_functions()

# set first empty message in input which can be replace by memories
input_to_model.append(
    {
        "content": '',
        "role": USER,
    }
)

# initialize memory
p = Path(MEMORY_FILE_PATH)
if p.exists():
    print_s(f"{output_color}Using {MEMORY_FILE_PATH} for memory{ANSII_RESET}")
    using_memory = True
    load_memory()



while(True):
    
    # loop
    auto_mode_loop()


    
    
