# chat_terminal
A Python terminal app for experimenting with LLM-driven workflows from the command line. Use it to chat with models, let an assistant inspect and edit files in a sandboxed directory, run shell commands (with your permission), and persist short-term memory and notes across sessions.

This repo is a local sandbox for iterative AI-assisted development, exploration, and automation. It’s intentionally simple: a single terminal UI (`chat.py`) exposes model communication, a small function/tool API, and an auto-mode loop that lets an assistant iterate until it completes a task.

Features
- Chat with models from the terminal (OpenAI or Anthropic supported).
- Switch models and APIs at runtime.
- Assistant code reading and editing
- Allow the assistant to run commands and test code it's working on in a sandboxed directory.
  - Auto mode: give the assistant a goal and it will iterate inside the sandbox until it calls `done` or hits a max attempts limit.
- Summarize a repo (Useful for getting an overview of a repo)
- Memory system: users or assistants can store memories for important information


Quick start
1. Install Python 3
2. Run the app with your API keys:

```bash
python3 chat.py -ok <OPENAI_KEY> -ak <ANTHROPIC_KEY>
```

Only one API key is required. If you pass only the OpenAI key the app will use OpenAI; if you pass only the Anthropic key it will use Anthropic. You can also set the model with `-m` and choose which API a model belongs to with `-a`.
