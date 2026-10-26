# RALPH loop playground

A deliberately small Python harness for running bounded, fresh-context agent loops with either
[Codex](https://developers.openai.com/codex/) or [OpenCode](https://opencode.ai/).

Here, a **RALPH loop** means: give a coding agent the same goal repeatedly, let each fresh run
inspect the work left by previous runs, and stop when the agent emits an explicit completion
promise. The repository—not chat history—is the shared memory.

## Quick start

```bash
uv sync
uv run python -m unittest discover -s tests -v

# Edit PROMPT.md first, then choose an agent:
uv run ralph --agent codex --prompt PROMPT.md --max-iterations 5
uv run ralph --agent opencode --prompt PROMPT.md --max-iterations 5
```

Each iteration starts a new agent session. Runtime state is written beneath `.ralph/`:

- `.ralph/progress.md` is the agents' durable handoff note.
- `.ralph/runs/<run-id>/iteration-N.log` contains the combined command output.
- Codex also writes its final response to `iteration-N.final.txt`.

The loop stops when the agent puts `<promise>COMPLETE</promise>` on a line by itself, when an
agent command fails, or when the iteration limit is reached. Reaching the limit returns exit code
2; an agent failure returns 1.

## Safety model

The defaults are intentionally conservative:

- Codex runs with `--sandbox workspace-write`.
- OpenCode uses its configured permission policy.
- Neither backend receives an automatic-approval flag unless you pass `--auto-approve`.
- Every run must have a positive `--max-iterations` value.

`--auto-approve` maps to `codex exec --approve-for-me` and `opencode run --auto`. OpenCode labels
its flag dangerous, so use it only inside a repository you trust and review your agent/tool
configuration first.

Use `--dry-run` to inspect the selected command and composed prompt without invoking an agent:

```bash
uv run ralph --agent opencode --prompt PROMPT.md --dry-run
```

Models are backend-specific and optional:

```bash
uv run ralph --agent codex --model YOUR_CODEX_MODEL --prompt PROMPT.md
uv run ralph --agent opencode --model provider/model --prompt PROMPT.md
```

## Writing a useful task

Put the goal, constraints, verification command, and objective acceptance criteria in `PROMPT.md`.
Keep the task outcome-focused. The harness adds iteration instructions and the completion contract
automatically. Do not put the completion marker in your own prompt.

Start with two or three iterations and inspect `.ralph/progress.md`, the run logs, and the Git diff.
Small limits make it much easier to learn how prompt wording affects convergence.

