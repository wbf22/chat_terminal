




import json
import subprocess
import json
import sys
import argparse
import http.client
import threading
import time


# define arguments
parser = argparse.ArgumentParser(description="A terminal app for accessing chat gpt")
parser.add_argument('-k', '--api_key', required=True, help='Your open-api key created at https://platform.openai.com/api-keys')
parser.add_argument('-t', '--tokens', type=int, default=4096, help="Max tokens chat will respond with")
parser.add_argument('-m', '--model', help='The api model you\'ll access. View models here https://platform.openai.com/docs/models', default='gpt-4.1-nano')
parser.add_argument('-T', '--temperature', type=float, default=0.4,  help='Higher values like 0.8 will make the output more random, while lower values like 0.2 will make it more focused and deterministic. Range 0-2')

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
error_color = color_code(255, 0, 0)

FILE_PATH = 'chat.md'
ASSISTANT = 'assistant'
USER = 'user'


# history = [
#     {
#         "role": "assistant",
#         "content": "Hello! How can I assist you today?"
#     },
#     {
#         "role": "user",
#         "content": "Hey chat"
#     }
# ]

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

history = []
while(True):

    print(user_color + 'USER' + ANSII_RESET)
    print()

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
        print()
        print(user_color + "Save conversation to 'chat.md'? (y/n) ", end='')
        user_input = input()
        if (user_input == 'y'):
            write_history(history)
        exit(0)


    print()
    print()

    # add user_input to history
    history.append({
        'role': USER,
        'content': user_input
    })

    # call api
    body = json.dumps({
        "model": MODEL,
        "messages": history
    })
    time_elapsed_displayer = threading.Thread(target=loading_indicator)
    time_elapsed_displayer.start()
    conn = http.client.HTTPSConnection("api.openai.com")
    conn.request(
        "POST", 
        "/v1/chat/completions", 
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

    completion = None
    error = False
    if response.status == 200:
        data = response.read()
        completion = json.loads(data)
    else:
        message = f"Error: {response.status} - {response.reason}{ANSII_RESET}"
        completion = {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": message
                    },
                }
            ]
        }
        error = True
    conn.close()

    # print out response
    message = completion['choices'][0]['message']
    print(
        assistant_color + 'ASSISTANT' + ANSII_RESET, 
        '(', 
        model_color + MODEL, 
        temperature_color + str(TEMPERATURE) + ANSII_RESET,
        ')'
    )
    print()
    if (error):
        print({error_color} + message['content'] + {ANSII_RESET})
    else:
        print(message['content'])
    print()
    print()


    # add to history
    history.append(message)
    

    
    
