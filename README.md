# chat_terminal
A Python terminal app for experimenting with LLM-driven workflows from the command line. Use it to chat with models, let an assistant inspect and edit files in a sandboxed directory, run shell commands (with your permission), and persist short-term memory and notes across sessions.

This repo is a local sandbox for iterative AI-assisted development, exploration, and automation. It’s intentionally simple: a single terminal UI (`chat.py`) exposes model communication, a small function/tool API, and an auto-mode loop that lets an assistant iterate until it completes a task.

Features
- Chat with models from the terminal (OpenAI or Anthropic supported).
- Switch models and APIs at runtime.
- Allow the assistant to run commands and edit files in a sandboxed directory.
  - Auto mode: give the assistant a goal and it will iterate inside the sandbox until it calls `done` or hits a max attempts limit.
- Summarize a directory / repository (the assistant will read files and produce per-file notes and a repo summary).
- Memory system: the assistant can save short notes (memories) which are persisted to `chat.json` and included with subsequent prompts.
- Built-in small utilities exposed as "tools/functions" to the model (ls, cat, write_file, edit_lines, delete, run_command, add_memory, and a couple helpers for running and interacting with processes).

Quick start
1. Install Python 3.8+.
2. Run the app with your API keys:

```bash
python3 chat.py -ok <OPENAI_KEY> -ak <ANTHROPIC_KEY>
```

Only one API key is required. If you pass only the OpenAI key the app will use OpenAI; if you pass only the Anthropic key it will use Anthropic. You can also set the model with `-m` and choose which API a model belongs to with `-a`.

Common CLI options
- -ok, --open_ai_api_key: OpenAI API key
- -ak, --anthropic_api_key: Anthropic API key
- -m, --model: model name to use (default: gpt-5-nano in this repo)
- -a, --api: which API the model name comes from (open_ai or anthropic)
- -d, --dir: directory in which the assistant is sandboxed (defaults to current working directory)
- -nc, --no_commands: disable assistant-run commands (removes run_command from available tools)

Runtime commands (type during a session)
- auto — start auto mode (assistant will iterate toward a task in the sandbox)
- vim — open vim to compose a longer user message
- quit / q — quit
- save — write conversation to `chat.md`
- dir — change & set the assistant sandbox directory
- summarize — summarize one or more directories (uses summarize_repo)
- model — change the active model
- notes — show what the assistant has saved as notes for this conversation
- memory — make or manage persistent memories in `chat.json`
- context — show the request context sent to the model
- usage — links to API usage dashboards
- help — show in-app help

How sandboxing & security work
- By default the assistant is sandboxed to the current working directory. You can change that using the `--dir` flag or the `dir` runtime command.
- The assistant can request to run shell commands. The `run_command` function may be disabled with `--no_commands` for extra safety.
- If the assistant tries to run a command that references paths outside the sandbox, the user is prompted to allow or deny the action.
- Avoid running destructive commands or giving model the ability to run commands without supervision — the assistant can delete files if permitted.

Notes & memory
- Conversation history saved to `chat.md` when you use `save` or when the assistant exits while the memory system is active.
- Persistent memories are stored in `chat.json`. The assistant periodically summarizes conversation context into memories to reduce tokens and preserve important details.

Summarize/repo helper
- The `summarize_repo` flow lets the assistant read files in one or more directories and produce per-file one-line summaries. It collects those into a note sheet and then produces a repo summary which is saved into memory.

Files of interest
- chat.py — main terminal app and core logic (model comms, tools, auto mode, memory, summarize_repo)
- chat.json — persistent memory file (created/updated by the app)
- chat.md — saved conversation history (created when using `save`)
- auto_mode_test/ — small test content used to exercise the summarizer and memory routines (includes `life_advice.txt` and `companion_plants.md`)
- ascii_art.txt — sample ASCII art used while experimenting with the repo
- oregon_trail.py — a small single-file terminal game added to repo as a demo/experiment
- .vscode/launch.json — example debug/launch configuration (currently contains CLI args including places for API keys)

Developer notes & recommendations
- Do not commit API keys. The current `.vscode/launch.json` contains an args array where keys may be put for convenience; avoid committing those keys and consider using environment variables or a local secrets file ignored by git.
- Recommended `.gitignore` additions: __pycache__/, *.pyc, .vscode/ (if it contains secrets), and any local credential files.
- The app supports OpenAI and Anthropic. Models listed in `chat.py` are examples; change with `-m` or via the `model` command.
- For safer operation in shared environments, start the app with `--no_commands` to prevent remote command execution.

Contributing
- PRs welcome. If you submit changes, please avoid committing secrets (API keys) and consider small, focused PRs for clarity.

License
- See LICENSE (public domain in this repo).

Questions or next steps
- I can: update `.gitignore` with suggested entries, remove `__pycache__` from the repo, add a brief example workflow to the README, or create `notes.md` capturing summaries of the `auto_mode_test` files. Tell me which you'd like me to do next.