




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
import tty
from typing import Optional


OPEN_AI = 'open_ai'
ANTHROPIC = 'anthropic'
models = """
- gpt-5.4
- gpt-5-mini
- gpt-5-nano
- claude-opus-4-6
- claude-sonnet-4-6
- claude-haiku-4-5
- (or enter specific model name)
Docs: https://developers.openai.com/api/docs/models/all, https://platform.claude.com/docs/en/about-claude/pricing
"""

# define arguments
parser = argparse.ArgumentParser(description="A terminal app for accessing chat gpt")
parser.add_argument('-ok', '--open_ai_api_key', help='Your open-api key created at https://platform.openai.com/api-keys')
parser.add_argument('-ak', '--anthropic_api_key', required=True, help='Your anthropic api key created at https://platform.claude.com/settings/keys')
parser.add_argument('-m', '--model', default='gpt-5-nano', help='The api model you\'ll access. View models here https://platform.openai.com/docs/models')
parser.add_argument('-a', '--api', default=OPEN_AI, help=f'Which api your model name is from. Currenlty only \'{OPEN_AI}\' and \'{ANTHROPIC}\' are supported.')

parser.add_argument('-d', '--dir', help='The directory in which the AI can execute commands and edit files. The currently directory by default.')



args = parser.parse_args()

API = args.api
MODEL = args.model
OPEN_AI_API_KEY = args.open_ai_api_key
ANTHROPIC_API_KEY = args.anthropic_api_key



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
SYSTEM = 'system'
AUTO_DIRECTORY = os.getcwd() if args.dir == None else args.dir
NO_QUESTIONS_IN_AUTO_MODE = False
MAX_ACTIONS = 24
HISTORY_LENGTH = 10
CONVERSATION_SUMMARY_RATE = 10



request_done = False
def loading_indicator():
    # Hide the cursor
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    # loop showing elapsed time
    start = time.time()
    length = 0
    while not request_done:
        elapsed = f"{(time.time() - start):.1f}"
        elapsed += 's'
        move_cursor_back(length)
        sys.stdout.write(temperature_color + elapsed + ANSII_RESET)
        sys.stdout.flush()
        length = len(elapsed)
        time.sleep(0.1)
        

    # clear line
    sys.stdout.write('\r\x1b[K')
    sys.stdout.flush()

    # show cursor
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()

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
    print_s("\n")
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


USER_TAG = 'YOU: (type help for special commands)'
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
    global memory
    with open(MEMORY_FILE_PATH, 'r') as file:
        content = file.read()
        try:
            memory = json.loads(content)
        except ValueError as e:
            print_s(f"{error_color}Error loading memories from {MEMORY_FILE_PATH}:\n{e}")

def write_memory():
    global memory

    if using_memory:
        # limit the size of memory to a few hundred memories
        memory = memory[:100]

        # write to file
        json_str = json.dumps(memory, indent=4)
        with open(MEMORY_FILE_PATH, 'w') as file:
            file.write(json_str)

        # add to notes sent with each request
        add_memory_to_notes()

def promp_ai_for_memory():
    global input_to_model

    print_s()
    print_s(f"{output_color}having ai store memory for conversation{ANSII_RESET}\n")
    input_to_model.append(
        {
            "content": f"SYSTEM: The user has requested you make a memory of the current conversation to be saved for your reference. Please describe the most important points of this conversation in a one line summary.",
            "role": SYSTEM if API == OPEN_AI else USER,
        }
    )
    outputs, error = call_api(input_to_model, include_functions=False)
    input_to_model = input_to_model[:-1]
    if not error:
        new_mem = outputs[0]['text']
        print_s(f"{assistant_color}New memory:\n {new_mem}{ANSII_RESET}")
        memory.append(new_mem)
    else:
        print_s(f"{error_color} Error: {outputs}{ANSII_RESET}")
    
    print_s()

auto_prompt = ""
actions = 0
def user_prompt():
    global auto_prompt, NO_QUESTIONS_IN_AUTO_MODE, AUTO_DIRECTORY, input_to_model, memory
    
    user_input = input()

    if user_input.strip() == 'vim':

        # clear last two lines
        print_s('\x1b[1A', end="")
        print_s('\x1b[K', end="")
        print_s('\x1b[1A', end="")
        print_s('\x1b[K', end="")
        sys.stdout.flush()
        
        # load history into file
        write_history(history)

        # open vim for user
        subprocess.run(['vim', '+', FILE_PATH])
        with open(FILE_PATH, 'r') as file:
            content = file.read()
        os.remove(FILE_PATH)

        # parse out last user input and store in user_input
        last_message_start = content.rfind(USER_TAG)
        user_input = content[last_message_start+37:]
        print_s(user_input)
    elif user_input.strip() == 'quit' or user_input == 'q':
        promp_ai_for_memory()
        write_memory()
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
        print_s(f"{model_color}Directories{ANSII_RESET}")
        c = 'b'
        directories = []
        while c != "":
            c = input("Enter a directory path to summarize. Hit enter again to finish (by default the current directory is used)\n")
            if c != "":
                directories.append(c)
            print_s("\033[A\033[2K" * 2, end="", flush=True)
            print_s(c)
        print_s()
        if len(directories) == 0:
            directories = [os.getcwd()]

        print_s(f"{model_color}Exclude{ANSII_RESET}")
        c = 'b'
        exclude = []
        while c != "":
            c = input("Enter a directory path to EXCLUDE. Hit enter again to finish (by default .git in the current directory is excluded)\n")
            if c != "":
                exclude.append(c)
            print_s("\033[A\033[2K" * 2, end="", flush=True)
            print_s(c)
        print_s()
        if len(exclude) == 0:
            exclude = [".git"]
        
        summarize_repo(directories, exclude)
        user_input = ''
    elif user_input.strip() == "model":
        print_s()
        print_s(f"{assistant_color}CHANGE MODEL{ANSII_RESET}\n")
        print_s(f"{model_color}api:\n[0] {OPEN_AI} (chatgpt)\n[1] {ANTHROPIC} (cluade)\n{ANSII_RESET}")
        api = input()
        if api == "1":
            API = ANTHROPIC
        else:
            API = OPEN_AI

        print_s()
        print_s(f"{assistant_color}model name:\n{models}{ANSII_RESET}")
        MODEL = input()

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
        if choice == "0":
            promp_ai_for_memory()
        elif choice == "1":
            print_s(f"{assistant_color}enter custom memory:\n{ANSII_RESET}")
            new_mem = input()
            print_s(f"{assistant_color}New memory:\n {new_mem}{ANSII_RESET}")
            memory.append(new_mem)
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
            write_memory()
        
        print_s()
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
        print_s(ANSII_RESET)

        user_input = ''


    return user_input

def is_in_dir(base_dir, path):
    base = Path(base_dir).resolve()
    target = Path(path).resolve()
    return base in target.parents or target == base

def convert_to_directory_path(path):

    if not is_in_dir(AUTO_DIRECTORY, path):
        if path.startswith("/"):
            path = path[1:]
        path = os.path.join(AUTO_DIRECTORY, path)

    return path

def convert_paths_in_command(command):
    # Matches unix/windows absolute paths and relative paths with extensions
    path_pattern = r'(?:\/[\w.\-\/]+|[A-Za-z]:\\[\w.\-\\]+|\.{0,2}\/[\w.\-\/]+|\w[\w.\-]*\/[\w.\-\/]*)'

    def replace_path(match):
        path = match.group(0)
        new_path = convert_to_directory_path(path)
        return new_path

    modified = re.sub(path_pattern, replace_path, command)
    return modified

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

def summarize_repo(directories: list[str], exclude: list[str]):
    global input_to_model, memory

    MAX_FILE_SIZE_BYTES = 500 * 1000

    all_files = []
    for directory in directories:
        directory_path = Path(directory).resolve()
        files = [p for p in directory_path.rglob("*") if p.is_file()]
        for f in files:
            is_excluded = False
            for exclude_dir_path in exclude:
                exlude_dir = Path(exclude_dir_path).resolve()
                if exlude_dir in f.parents or f == exlude_dir:
                    is_excluded = True
                    break
            
            if not is_excluded:
                all_files.append(f)

    print_s("Starting...")
    prompt = """
The user has requested you help them summarize and understand the repo they're working in. 
We'll provide you files, one by one and ask you to summarize them. We'll record your summaries
in a note sheet which we'll return to you when we've finished. You can then provide the user with a 
summary of the repo and start helping them with their questions.
    """
    input_to_model.append(
        {
            "content": prompt,
            "role": SYSTEM if API == OPEN_AI else USER,
        }
    )
    call_api(input_to_model, include_functions=False)

    notes = []
    i = 0
    for file in all_files:
        i+=1
        size = file.stat().st_size
        contents = None
        if size > MAX_FILE_SIZE_BYTES:
            print_s(f"{i}/{len(all_files)} {model_color}exceeded max file size: {file} > {MAX_FILE_SIZE_BYTES/1000.0}KB - {ANSII_RESET}")
            contents = "EXCEEDED MAX FILE SIZE"
        else:
            print_s(f"{i}/{len(all_files)} {model_color}reading: {file} - {ANSII_RESET}")
            try:
                contents = file.read_text()
            except FileNotFoundError:
                print(f"File not found: {file}")
            except PermissionError:
                print(f"Permission denied: {file}")
            except Exception as e:
                print(f"Unexpected error: {e}")


        prompt = f"```{file}\n{contents}\n```\nReturn a one line summary of this file"
        input_to_model.append(
            {
                "content": prompt,
                "role": SYSTEM if API == OPEN_AI else USER,
            }
        )
        outputs, error = call_api(input_to_model, include_functions=False)
        ai_summary = None
        tries = 0
        while error and tries < 2:
            ai_summary = outputs
            time.sleep(30)
            tries += 1

        output = outputs[0]
        ai_summary = output['text'].replace("\n", " ")
        print_s(f" - {ai_summary}")
        notes.append(f"{file} - {ai_summary}")
        input_to_model.append(
            {
                "content": ai_summary,
                "role": ASSISTANT,
            }
        )

        time.sleep(4)
        

    print_s()
    note_file = "\n".join(notes)
    prompt = f"{note_file} \n\n Now summarize the repo for the user"
    input_to_model.append(
        {
            "content": prompt,
            "role": SYSTEM if API == OPEN_AI else USER,
        }
    )
    print_s("Summarizing...")
    outputs, error = call_api(input_to_model, include_functions=False)
    message = None
    if error:
        message = outputs
    else:
        message = outputs[0]['text']
    print_and_save_ai_message_to_history(message, error)

    # save as memory
    memory.append(message)
    write_memory()
    

def check_for_max_actions():
    global actions
    if actions > MAX_ACTIONS:
        print_s(f"{output_color}The assistant has made {actions} requests on this task. Would you like them to continue? (y/n){ANSII_RESET}")
        if input() == 'n':
            return False
        else:
            actions = 0    
    
    return True

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
            "name": "run_command",
            "description": "Run a command in the directory",
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
            "name": "kill_command",
            "description": "Kill a command/process that is running",
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
                        "description": "Path to the directory, e.g. /myfolder"
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
            "name": "set_notes",
            "description": "If you would like to write something down to remember, you can do so with this function. This will replace the contents of your notes. You don't need to ask the user for permission to update this. Your notes will be returned with each request as the first message in the conversation.",
            params_name: {
                "type": "object",
                "properties": {
                    "note": {
                        "type": "string",
                        "description": "The notes you'd like to keep for this conversation"
                    }
                },
                "required": ["note"]
            }
        },
        {
            "name": "get_notes",
            "description": "Returns notes you may have previously written with the 'set_notes' function. Your notes will be returned with each request as the first message in the conversation.",
            params_name: { "type": "object", "properties": {}}
        },
    ]

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

def add_function_result(tool_use_id, tool_use, result):
    if API == OPEN_AI:
        input_to_model.append(
            {
                "type": "function_call",
                "call_id": tool_use_id,
                "name": tool_use['name'],
                "arguments": json.dumps(tool_use['input'])
            }
        )
        input_to_model.append(
            {
                "type": "function_call_output",
                "call_id": tool_use_id,
                "output": result
            }
        )
    else:
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

def handle_function_call(name, args, tool_use_id, tool_use):
    global NO_QUESTIONS_IN_AUTO_MODE, notes

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

        command = convert_paths_in_command(command)
        input_function_loop(command, tool_use_id, tool_use, input_to_model)
    elif name == "ls":
        path = args.get('path')
        path = path if path != None else ''

        path = convert_to_directory_path(path)
        cmd = f"ls -la {path}"
        p_result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        result = f'{p_result.stdout}\n{p_result.stderr}'
        print_s(f"{output_color}{result}{ANSII_RESET}")
        print_s()
        add_function_result(tool_use_id, tool_use, result)
    elif name == "cat":
        path = args.get('path')
        path = path if path != None else ''

        path = convert_to_directory_path(path)
        p_result = subprocess.run(f"cat {path}", shell=True, capture_output=True, text=True)
        result = f'{p_result.stdout}\n{p_result.stderr}'
        print_s(f"{output_color}{result[:256]}\n...{ANSII_RESET}")
        print_s()
        add_function_result(tool_use_id, tool_use, result)
    elif name == "write_file":
        path = args.get('path')
        contents = args.get('contents')
        path = path if path != None else ''
        contents = contents if contents != None else ''

        path = convert_to_directory_path(path)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents)

        result = f"""
write to file {path}
```
{contents}
```
        """
        print_s(f"{output_color}{result}{ANSII_RESET}")
        print_s()
        if contents == '':
            result += "\nYou didn't specify any file 'contents' so an empty file was created"
        add_function_result(tool_use_id, tool_use, result)
    elif name == "delete":
        path = args.get('path')
        path = path if path != None else ''

        path = convert_to_directory_path(path)
        p = Path(path)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
        result = f"deleted {path}"
        print_s(f"{output_color}{result}{ANSII_RESET}")
        print_s()
        add_function_result(tool_use_id, tool_use, result)
    elif name == "set_notes":
        notes = args["note"]
        print_s(f"{output_color}{notes}{ANSII_RESET}")
        print_s()
        add_function_result(tool_use_id, tool_use, notes)
    elif name == "get_notes":
        add_function_result(tool_use_id, tool_use, notes)
    else:
        result = "That's not a command or doesn't make sense in this context"
        print_s(f"{output_color}{result}{ANSII_RESET}")
        print_s()
        add_function_result(tool_use_id, tool_use, result)

    return input_to_model

def input_function_loop(command, tool_use_id, tool_use, input_to_model):
    global actions
    
    # start process
    process = None
    output = None
    if is_command_in_directory(command):
        process = TalkProcess(command, AUTO_DIRECTORY)
        output = process.get_output()
        print_s(f"{output_color}{output}{ANSII_RESET}\n")
    else:
        output = f"invalid command, working outside designated directory '{AUTO_DIRECTORY}'. Stick to relative paths"
 
    add_function_result(tool_use_id, tool_use, output)
    
    kill = False
    made_calls = False
    while process != None and not process.is_finished():

        # prompt user if max_actions has been hit
        should_continue = check_for_max_actions()
        if not should_continue:
            break

        # break out if process is finished
        actions += 1
        if process.is_finished(): break

        # otherwise send output to model
        outputs, error = call_api(input_to_model)

        # handle ai response
        if not error:
            for output in outputs:
                type = output['type']
                if type == "function_call":

                    name = output['name']
                    tool_use_id = output['tool_use_id']
                    print_s(f"{model_color}{name} {output['arguments']} {tool_use_id}{ANSII_RESET}\n")
                    if name == "command_input":
                        args = {}
                        if 'arguments' in output:
                            args = json.loads(output['arguments'])
                        ai_input = args['input']

                        # send ai input
                        process.send_input(ai_input)
                        print_s(f"{model_color}{ai_input}{ANSII_RESET}\n")

                        # add process output to response for ai
                        result = process.get_output()
                        print_s(f"{output_color}{result}{ANSII_RESET}\n")
                        add_function_result(tool_use_id, output, result)

                    elif name == "kill_command":
                        kill = True
                        add_function_result(tool_use_id, output, "Process was killed")
                    else:
                        add_function_result(tool_use_id, output, "Right now you have a command running. If you want run another function, use 'command_input' or 'kill_command' functions to finish first.")
                        print_s(f"{error_color}rejected attempt to run command while other command is running{ANSII_RESET}")

                else:
                    msg = "Right now you have a command running and it's waiting for your input. Use 'command_input' or 'kill_command' functions before sending the user a message."
                    input_to_model.append(
                        {
                            "content": msg,
                            "role": SYSTEM if API == OPEN_AI else USER,
                        }
                    )
                    print_s(f"{error_color}rejected message since ai is running a command currently{ANSII_RESET}")
            
            if kill:
                process.kill()

        else:
            input_to_model.append(
                {
                    "content": outputs,
                    "role": SYSTEM if API == OPEN_AI else USER,
                }
            )

    if process != None and not process.is_finished(): process.kill()

input_to_model = []
notes = ''
def add_memory_to_notes():
    global notes
    notes = f"Your notes:\n{notes}\n\nLong term memories:\n{"\n".join(memory)}"


def prompt_ai_to_update_notes_and_shrink_history():
    global notes, input_to_model


    if len(input_to_model) > HISTORY_LENGTH + CONVERSATION_SUMMARY_RATE:

        # ask model to add to it's notes
        print_s(f"{output_color}Summarizing a few older messages in conversation to save on tokens...{ANSII_RESET}")
        input_to_model.append(
            {
                "content": f"SYSTEM: We're about to drop the last {CONVERSATION_SUMMARY_RATE} messages in this conversation. Please output an update to your notes including any important information from older messages that might be lost. Your notes:\n{notes}",
                "role": SYSTEM if API == OPEN_AI else USER,
            }
        )
        outputs, error = call_api(input_to_model, include_functions=False)

        # delete that request from the conversation
        input_to_model = input_to_model[:-1]

        # add model response as first message and replace notes
        if not error and len(outputs) != 0:
            notes = outputs[0]['text']
            add_memory_to_notes()
        
            input_to_model = input_to_model[-HISTORY_LENGTH:]
            input_to_model[0] = {
                "content": notes,
                "role": SYSTEM if API == OPEN_AI else USER,
            }

        print_s()

    
def call_api(model_input, include_functions=True):
    global request_done
    time_elapsed_displayer = threading.Thread(target=loading_indicator)
    time_elapsed_displayer.start()

    conn = None
    body = None
    if API == OPEN_AI:

        if include_functions:
            body = json.dumps({
                "model": MODEL,
                "input": model_input,
                "tools": tools,
                "tool_choice": "auto" if API == OPEN_AI else {"type":"auto"}
            })
        else:
            body = json.dumps({
                "model": MODEL,
                "input": model_input
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
                "messages": model_input,
                "tools": tools,
                "tool_choice": "auto" if API == OPEN_AI else {"type":"auto"}
            })
        else:
            body = json.dumps({
                "model": MODEL,
                "max_tokens": 1024,
                "messages": model_input
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
        
    response = conn.getresponse()
    output = None
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
        # print_s(body)
        # print_s(output)
        error = True
    conn.close()

    request_done = True
    time_elapsed_displayer.join()
    request_done = False


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
        outputs, error = call_api(input_to_model)
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
                                "role": SYSTEM if API == OPEN_AI else USER,
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
                elif type == "tool_use":
                    name = output['name']
                    args = output['input']
                    tool_use_id = output['id']
                    print_s(f"{model_color}{name} {json.dumps(args)[:64]}... {tool_use_id}{ANSII_RESET}")
                    print_s()
                    handle_function_call(name, args, tool_use_id, output)
        else:
            message = outputs
            print_and_save_ai_message_to_history(message, error)

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

# set up model functions based on api
define_model_functions()


# initialize memory
p = Path(MEMORY_FILE_PATH)
if p.exists():
    print_s(f"{output_color}Using {MEMORY_FILE_PATH} for memory{ANSII_RESET}")
    using_memory = True
    load_memory()
    add_memory_to_notes()


# set first note message in input
input_to_model.append(
    {
        "content": notes,
        "role": SYSTEM if API == OPEN_AI else USER,
    }
)

while(True):
    
    # loop
    auto_mode_loop()


    
    
