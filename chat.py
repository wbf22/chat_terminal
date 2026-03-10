




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


# define arguments
parser = argparse.ArgumentParser(description="A terminal app for accessing chat gpt")
parser.add_argument('-k', '--api_key', required=True, help='Your open-api key created at https://platform.openai.com/api-keys')
parser.add_argument('-t', '--tokens', type=int, default=4096, help="Max tokens chat will respond with")
parser.add_argument('-m', '--model', help='The api model you\'ll access. View models here https://platform.openai.com/docs/models', default='gpt-4.1-nano')
parser.add_argument('-T', '--temperature', type=float, default=0.4,  help='Higher values like 0.8 will make the output more random, while lower values like 0.2 will make it more focused and deterministic. Range 0-2')

parser.add_argument('-d', '--dir', help='The working directory where the model can run commands in auto mode')

# add in app command notes
subparsers = parser.add_subparsers(dest='command', title='Commands')
vim_parser = subparsers.add_parser(
    'vim', 
    help='''
        To edit a message sent to chat gpt, you can type 'vim' + 'enter' and the conversation will opened in vim.
        This can be handy if you want to copy and paste or create newlines in your response without sending
        the message to chat gpt. To submit the message simply save and quit vim by entering 'esc' then ':' 
        the 'wq' and hit 'enter'. 

        Previous messages will also be visible in vim, though editing these messages won't alter the conversation
        history. Only new content after the last '# USER' tag will be retrieved after you're finished. 
    '''
)
quit_parser = subparsers.add_parser(
    'quit',
    help='''
        To finish the conversation you can type 'quit' or 'q' and hit enter. You'll then be given the option
        to get your conversation output to a file.
    '''
)


args = parser.parse_args()

MODEL = args.model
TOKENS = args.tokens
API_KEY = args.api_key
TEMPERATURE = args.temperature



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
ASSISTANT = 'assistant'
USER = 'user'
SYSTEM = 'system'
AUTO_DIRECTORY = os.getcwd() if args.dir == None else args.dir
NO_QUESTIONS_IN_AUTO_MODE = False
MAX_ACTIONS = 100



request_done = False
def loading_indicator():
    # Hide the cursor
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    # loop showing elapsed time
    start = time.time()
    length = 0
    while not request_done:
        elapsed = str(time.time() - start)[:5]
        elapsed += 's'
        move_cursor_back(length)
        sys.stdout.write(temperature_color + elapsed + ANSII_RESET)
        sys.stdout.flush()
        length = len(elapsed)

    # clear line
    sys.stdout.write('\r\x1b[K')
    sys.stdout.flush()

    # show cursor
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()

def print_and_save_ai_message_to_history(ai_message, error):
    global history

    # print out response
    print(
        assistant_color + 'ASSISTANT' + ANSII_RESET, 
        '(', 
        model_color + MODEL, 
        temperature_color + str(TEMPERATURE) + ANSII_RESET,
        ')'
    )
    sys.stdout.write("\r\n")
    if (error):
        sys.stdout.write(error_color + ai_message + ANSII_RESET)
    else:
        sys.stdout.write(ai_message)
    sys.stdout.write("\r\n\r\n")


    # add to history
    history.append({
        'role': ASSISTANT,
        'content': ai_message
    })

def print_and_save_user_input_to_history():

    # get prompt
    user_input = ''
    while user_input == '':
        sys.stdout.write(user_color + 'YOU: (type help for special commands)' + ANSII_RESET)
        sys.stdout.write("\r\n\r\n")
        user_input = user_prompt()

    sys.stdout.write("\r\n\r\n")

    # add user_input to history
    history.append({
        'role': USER,
        'content': user_input
    })

    return user_input

def write_history(history):
    with open(FILE_PATH, 'w') as file:
        for message in history:
            if message['role'] == ASSISTANT:
                file.write('# ASSISTANT ')
                file.write('(') 
                file.write(MODEL + " ") 
                file.write(str(TEMPERATURE))
                file.write(')')
                file.write('\n\n')
                file.write(message['content'])
                file.write('\n\n\n')
            else:
                file.write('# USER') 
                file.write('\n\n')
                file.write(message['content'])
                file.write('\n\n\n')

auto_prompt = ""
def user_prompt():
    global auto_prompt
    
    user_input = input()

    if user_input.strip() == 'vim':

        # clear last two lines
        sys.stdout.write('\x1b[1A')
        sys.stdout.write('\x1b[K')
        sys.stdout.write('\x1b[1A')
        sys.stdout.write('\x1b[K')
        sys.stdout.flush()
        
        # load history into file
        write_history(history)
        with open(FILE_PATH, 'a') as file:
            file.write('# USER') 
            file.write('\n\n\n')

        # open vim for user
        subprocess.run(['vim', '+', FILE_PATH])
        with open(FILE_PATH, 'r') as file:
            content = file.read()

        # parse out last user input and store in user_input
        last_message_start = content.rfind("# USER")
        user_input = content[last_message_start+6:]
        print(user_input)

    elif user_input.strip() == 'quit' or user_input == 'q':
        exit(0)
    elif user_input.strip() == "save":
        print()
        print(user_color + "Save conversation to 'chat.md'? (y/n) ", end='')
        user_input = input()
        print()
        if (user_input == 'y'):
            write_history(history)
        exit(0)
    elif user_input.strip() == "auto":

        NO_QUESTIONS_IN_AUTO_MODE = True
        print(f'{model_color}In auto mode! Your ai helper will iterate in this directory until it believes it has achieved the goal you provide it. Once started, the model will continue it achieves it\'s goal or hits the max attempts limit{ANSII_RESET}')
        print()
        MAX_ACTIONS = input(f"{user_color}Max api usage (number of requests)\n{ANSII_RESET}")
        MAX_ACTIONS = int(MAX_ACTIONS)

        print(f"{user_color}Task for ai:{ANSII_RESET}")
        user_input = user_prompt()

        auto_prompt = f"""
You're working in a loop to complete the following user prompt:
{user_input}

You can call the provided functions to run commands, explore your sandboxed directory, and create
and edit files. Once done use the 'done' function to indicate you've finished

Sometimes you can send a regular message to ask them for clarification on the prompt, 
though try to avoid bothering the user until it's important.
        """
        user_input = auto_prompt

    elif user_input.strip() == "help":
        print(model_color)
        print("Help:")
        print("- auto (give the ai a task or list of tasks and tell it to complete them before it responds again. The ai will be constrained to the current directory or the directory specified with --dir)")
        print("- vim (open vim for editing your response. Remember to quit with 'ESC + :wq'!)")
        print("- quit or q (quit chat)")
        print("- save (save your conversation to a file)")
        print(ANSII_RESET)

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


tools = [
    {
        "type": "function",
        "name": "done",
        "description": "Used to indicate you've complete the users prompt and are awaiting further instructions",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "What you want to say to the user now that you're done"
                }
            },
            "required": ["path"]
        }
    },
    {
        "type": "function",
        "name": "run_command",
        "description": "Run a command in the directory",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command string with args"
                }
            },
            "required": ["path"]
        }
    },
    {
        "type": "function",
        "name": "kill_command",
        "description": "Kill a command/process that is running"
    },
    {
        "type": "function",
        "name": "command_input",
        "description": "Send input to a currently running command/process",
        "parameters": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "input to be sent to currently running command"
                }
            },
            "required": ["path"]
        }
    },
    {
        "type": "function",
        "name": "ls",
        "description": "List the files in a directory",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the directory, e.g. /home/user/documents"
                }
            },
            "required": ["path"]
        }
    },
    {
        "type": "function",
        "name": "cat",
        "description": "Get the current contents of a file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file, e.g. /home/user/documents/myfile.txt"
                }
            },
            "required": ["path"]
        }
    },
    {
        "type": "function",
        "name": "write_file",
        "description": "Set the contents of a file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file, e.g. /home/user/documents/myfile.txt"
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
        "type": "function",
        "name": "delete",
        "description": "Delete a file or folder (with it's contents)",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the directory, e.g. /home/user/documents"
                }
            },
            "required": ["path"]
        }
    },
    {
        "type": "function",
        "name": "get_user_instructions",
        "description": "Sometimes the user will give you a prompt and will ask you to finish it before sending a normal message. During that time you can call this to get their original instructions"
    },
]
def handle_function_call(name, args, call_id, input_to_model):
    global NO_QUESTIONS_IN_AUTO_MODE

    # handle each command
    if name == 'done':
        input_to_model.append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": "prompt has been marked as completed. You can now ask the user questions"
            }
        )
        NO_QUESTIONS_IN_AUTO_MODE = False
        print_and_save_ai_message_to_history(args['text'], False)
        user_res = print_and_save_user_input_to_history()
        input_to_model.append(
            {
                "content": user_res,
                "role": USER,
            }
        )

    elif name == "run_command":
        command = args['command']
        input_to_model = input_function_loop(command, call_id, input_to_model)
    elif name == "ls":
        path = convert_to_directory_path(args['path'])
        cmd = f"ls -la {path}"
        p_result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        result = f'{p_result.stdout}\n{p_result.stderr}'
        sys.stdout.write(f"{output_color}{result}{ANSII_RESET}")
        sys.stdout.write("\r\n\r\n")
        input_to_model.append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result
            }
        )
    elif name == "cat":
        path = convert_to_directory_path(args['path'])
        p_result = subprocess.run(f"cat {path}", shell=True, capture_output=True, text=True)
        result = f'{p_result.stdout}\n{p_result.stderr}'
        sys.stdout.write(f"{output_color}{result}{ANSII_RESET}")
        sys.stdout.write("\r\n\r\n")
        input_to_model.append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result
            }
        )
    elif name == "write_file":
        path = convert_to_directory_path(args['path'])
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["contents"])

        result = f"""
write to file {args["path"]}
```
{args["contents"]}
```
        """
        sys.stdout.write(f"{output_color}{result}{ANSII_RESET}")
        sys.stdout.write("\r\n\r\n")
        input_to_model.append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result
            }
        )
    elif name == "delete":
        path = convert_to_directory_path(args['path'])
        p = Path(path)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
        result = f"deleted {path}"
        sys.stdout.write(f"{output_color}{result}{ANSII_RESET}")
        sys.stdout.write("\r\n\r\n")
        input_to_model.append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result
            }
        )
    elif name == "get_user_instructions":
        input_to_model.append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": auto_prompt
            }
        )
    else:
        result = "That's not a command or doesn't make sense in this context"
        sys.stdout.write(f"{output_color}{result}{ANSII_RESET}")
        sys.stdout.write("\r\n\r\n")
        input_to_model.append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result
            }
        )

    return input_to_model

def input_function_loop(command, call_id, input_to_model):
    
    # start process
    process = None
    output = None
    if is_command_in_directory(command):
        process = TalkProcess(command, AUTO_DIRECTORY)
        output = process.get_output()
        sys.stdout.write(f"{output_color}{output}{ANSII_RESET}\n")
    else:
        output = f"invalid command, working outside designated directory '{AUTO_DIRECTORY}'. Stick to relative paths"
 
    input_to_model.append(
        {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output
        }
    )
    
    kill = False
    made_calls = False
    i = 0
    while process != None and not process.is_finished() and i < MAX_ACTIONS:

        # break out if process is finished
        i+=1
        if process.is_finished(): break

        # otherwise send output to model
        outputs, error = ai_auto_mode_prompt(input_to_model)
        input_to_model.clear()

        # handle ai response
        if not error:
            for output in outputs:
                type = output['type']
                if type == "function_call":

                    name = output['name']
                    call_id = output['call_id']
                    sys.stdout.write(f"{model_color}{name} {output['arguments']} {call_id}{ANSII_RESET}\n")
                    if name == "command_input":
                        args = {}
                        if 'arguments' in output:
                            args = json.loads(output['arguments'])
                        ai_input = args['input']

                        # send ai input
                        process.send_input(ai_input)
                        sys.stdout.write(f"{model_color}{ai_input}{ANSII_RESET}\n")

                        # add process output to response for ai
                        output = process.get_output()
                        sys.stdout.write(f"{output_color}{output}{ANSII_RESET}\n")
                        input_to_model.append(
                            {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": output
                            }
                        )

                    elif name == "kill_command":
                        kill = True
                        input_to_model.append(
                            {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": "Process was killed"
                            }
                        )
                    else:
                        input_to_model.append(
                            {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": "Right now you have a command running. If you want run another function, use 'command_input' or 'kill_command' functions to finish first."
                            }
                        )
                        print(f"{error_color}rejected attempt to run command while other command is running{ANSII_RESET}")

                else:
                    msg = "Right now you have a command running and it's waiting for your input. Use 'command_input' or 'kill_command' functions before sending the user a message."
                    input_to_model.append(
                        {
                            "content": msg,
                            "role": SYSTEM,
                        }
                    )
                    print(f"{error_color}rejected message since ai is running a command currently{ANSII_RESET}")
            
            if kill:
                process.kill()

        else:
            input_to_model.append(
                {
                    "content": outputs,
                    "role": SYSTEM,
                }
            )

    if not process.is_finished(): process.kill()
    return input_to_model

def ai_auto_mode_prompt(model_input):
    global request_done
    time_elapsed_displayer = threading.Thread(target=loading_indicator)
    time_elapsed_displayer.start()

    body = json.dumps({
        "conversation": CONVERSATION_ID,
        "model": MODEL,
        "input": model_input,
        "tools": tools,
        "tool_choice": "auto"
    })

    conn = http.client.HTTPSConnection("api.openai.com")
    conn.request(
        "POST", 
        "/v1/responses", 
        body=body, 
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + API_KEY
        }
    )
    response = conn.getresponse()
    output = None
    error = False
    if response.status == 200:
        data = response.read()
        response_body = json.loads(data)
        output = response_body['output']
    else:
        output = f"Error: {response.status} - {response.read().decode()}{ANSII_RESET}"
        error = True
    conn.close()

    request_done = True
    time_elapsed_displayer.join()
    request_done = False

    return output, error


stop = threading.Event()
def auto_mode_loop(max_attempts=100):

    # ai loop
    user_input = print_and_save_user_input_to_history()
    input_to_model = [
        {
            "content": user_input,
            "role": USER,
        }
    ]
    i = 0
    while not stop.is_set() and i < max_attempts:

        # prompt ai and handle response
        outputs, error = ai_auto_mode_prompt(input_to_model)
        input_to_model = []
        if not error:

            # sort so that run command function calls are the last to run
            outputs.sort(key=lambda x: x.get("name") == "run_test_command" or x.get("name") == "run_command")
            
            # handle ai commands and messages
            for output in outputs:
                type = output['type']
                if type == "message":
                    if NO_QUESTIONS_IN_AUTO_MODE:
                        print(f"{error_color}rejected message since prompt has not been completed{ANSII_RESET}")
                        input_to_model.append(
                            {
                                "content": "The user has asked you complete this prompt without asking questions. Just complete the prompt with your best guess on the users' intentions and call the 'done' function when finished.",
                                "role": SYSTEM,
                            }
                        )
                    else:
                        message = output['content'][0]['text']
                        print_and_save_ai_message_to_history(message, False)
                        user_res = print_and_save_user_input_to_history()
                        input_to_model.append(
                            {
                                "content": user_res,
                                "role": USER,
                            }
                        )
                elif type == "function_call":
                    name = output['name']
                    args = {}
                    if 'arguments' in output:
                        args = json.loads(output['arguments'])
                    call_id = output['call_id']
                    sys.stdout.write(f"{model_color}{name} {output['arguments']} {call_id}{ANSII_RESET}")
                    sys.stdout.write("\r\n\r\n")
                    input_to_model = handle_function_call(name, args, call_id, input_to_model)
        else:
            message = outputs
            print_and_save_ai_message_to_history(message, error)

        i += 1


    # join user input thread
    # t1.join()


    if i == max_attempts:
        print(user_color + f'Ai helper paused after hitting max attempts of {max_attempts}, continue current auto mode setup with new prompt? (y/n)' + ANSII_RESET)
        print()
        user_input = user_prompt()
        print()
        print()

        if user_input.lower() == "y":
            auto_mode_loop()


# MAIN CODE
history = []

# start a conversation
conn = http.client.HTTPSConnection("api.openai.com")
conn.request(
    "POST", 
    "/v1/conversations",
    headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + API_KEY
    }
)
response = conn.getresponse()
data = response.read()
CONVERSATION_ID = json.loads(data)['id']
conn.close()

while(True):
    

    # loop
    auto_mode_loop()


    
    
