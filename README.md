# chat_terminal
A Python terminal app for interfacing with chatgpt and claude. 

Features
- chat with models in the terminal
- switch models
- allow model to run commands and iterate on code in a sandboxed directory
  +  auto mode (tell the AI to keep working and not bother you until it's done)
- summarize a directory (useful for understanding an unfamiliar codebase)

Usage:
```
python3 chat.py -ok <open ai key> -ak <anthropic key>
```

for help
```
python3 chat.py -h
# or 'help' during runtime
```

You might like having an alias like this:
```
alias chat='python3 ~/Documents/chat_terminal/chat.py -ok <open ai key> -ak <anthropic key>'
```

## Contributing
Feel free to make a pr and we can you review any changes you'd like to make. 

You can also make a issue for any bugs you find.

