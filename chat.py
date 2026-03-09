




import json
import os
from pathlib import Path
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

parser.add_argument('-a', '--auto', action='store_true', help='Puts model in auto mode where it iterates on code in a folder running the code and iterating until achieving the prompt request.')
parser.add_argument('-c', '--cmd', help='The command for running a test when the ai is modifying code. The ai will call this to test what they\'re working on.')
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
error_color = color_code(255, 0, 0)

FILE_PATH = 'chat.md'
ASSISTANT = 'assistant'
USER = 'user'
SYSTEM = 'system'
RUN_COMMAND = args.cmd
AUTO_DIRECTORY = args.dir



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
    sys.stdout.write(user_color + 'USER PROMPT: (what you want the ai helper to do)' + ANSII_RESET)
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

def user_prompt():
    
    user_input = input()

    if user_input.startswith('vim'):

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

    elif user_input.startswith('quit') or user_input == 'q':
        exit(0)
    elif user_input.startswith("save"):
        print()
        print(user_color + "Save conversation to 'chat.md'? (y/n) ", end='')
        user_input = input()
        print()
        if (user_input == 'y'):
            write_history(history)
        exit(0)
    elif user_input.startswith("auto") and not in_auto_mode:
        auto_mode()

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


tools = [
    {
        "type": "function",
        "name": "run_test_command",
        "description": "The user has provided you with a prompt to do some work in a directory. This command is what they provided you to test. We'll send you back the output of the test command"
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
]
def handle_function_call(name, args, call_id):

    # handle each command
    result = None
    if name == "run_test_command":
        p_result = subprocess.run(RUN_COMMAND, shell=True, capture_output=True, text=True)
        result = f'{p_result.stdout}\n{p_result.stderr}'
    elif name == "ls":
        path = convert_to_directory_path(args['path'])
        cmd = f"ls -la {path}"
        p_result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        result = f'{p_result.stdout}\n{p_result.stderr}'
    elif name == "cat":
        path = convert_to_directory_path(args['path'])
        p_result = subprocess.run(f"cat {path}", shell=True, capture_output=True, text=True)
        result = f'{p_result.stdout}\n{p_result.stderr}'
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
    elif name == "delete":
        path = convert_to_directory_path(args['path'])
        p = Path(path)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
        result = f"deleted {path}"

    return result

def ai_auto_mode_prompt(model_input):
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
        output = response_body['output'][-1]
    else:
        output = f"Error: {response.status} - {response.read().decode()}{ANSII_RESET}"
        error = True
    conn.close()

    return output, error


in_auto_mode = args.auto
stop = threading.Event()
def auto_mode_loop(max_attempts=100):

    # get input and save to history
    user_input = print_and_save_user_input_to_history()

    # ai loop
    sys.stdout.write(f"{model_color}Ai started in auto mode\r\n")
    i = 0

    prompt = f"""
You're working in a loop to complete the following user prompt:
{user_input}

You can call the provided functions to run the user provided test command, or
read and set files, as well as exploring directories. Once done just send a regular
message to let them know how it went. You can also send a regular message to ask
them for clarification on the prompt, though try to avoid bothering the user until
it's important.
    """
    
    input_to_model = [
        {
            "content": prompt,
            "role": SYSTEM,
        }
    ]
    while not stop.is_set() and i < max_attempts:

        # prompt ai and handle response
        output, error = ai_auto_mode_prompt(input_to_model)
        if not error:
            type = output['type']
            if type == "message":
                message = output['content'][0]['text']
                print_and_save_ai_message_to_history(message, False)
                user_res = print_and_save_user_input_to_history()
                input_to_model = [
                    {
                        "content": user_res,
                        "role": USER,
                    }
                ]
            elif type == "function_call":
                name = output['name']
                args = {}
                if 'arguments' in output:
                    args = json.loads(output['arguments'])
                call_id = output['call_id']
                sys.stdout.write(f"{model_color}{name} {output['arguments']} {call_id}{ANSII_RESET}")
                sys.stdout.write("\r\n\r\n")
                result = handle_function_call(name, args, call_id)
                sys.stdout.write(f"{output_color}{result}{ANSII_RESET}")
                sys.stdout.write("\r\n\r\n")
                input_to_model = [
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": result
                    }
                ]
        else:
            message = output
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


def auto_mode():
    global RUN_COMMAND
    global in_auto_mode
    
    in_auto_mode = True
    print(model_color + 'In auto mode! Your ai helper will iterate in this directory until it believes it has achieved the goal you provide it. Once started, the model will continue unless type something or it achieves it\'s goal' + ANSII_RESET)
    print()

    if len(RUN_COMMAND) == 0:
        sys.stdout.write(user_color + "RUN COMMAND: (eg. 'sh run_my_app.sh')" + ANSII_RESET)
        sys.stdout.write("\r\n\r\n")
        RUN_COMMAND = input()
    

    # loop
    auto_mode_loop()

    in_auto_mode = False    
    RUN_COMMAND = ''



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
    if in_auto_mode:
        auto_mode()

    # get input and save to history
    user_input = print_and_save_user_input_to_history()

    # call api
    body = json.dumps({
        "conversation": CONVERSATION_ID,
        "model": MODEL,
        "input": user_input
    })
    time_elapsed_displayer = threading.Thread(target=loading_indicator)
    time_elapsed_displayer.start()
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
    request_done = True
    time_elapsed_displayer.join()
    request_done = False

    message = None
    error = False
    if response.status == 200:
        data = response.read()
        message = json.loads(data)['output']['content']['text']
    else:
        message = f"Error: {response.status} - {response.reason}{ANSII_RESET}"
        error = True
    conn.close()

    # print out response and save to history
    print_and_save_ai_message_to_history(message, error)
    

    
    
