# Working in this repository

This repository contains Scissorhands, a small Python harness for experimenting with agent loops.

## Commands

- Install/sync: `uv sync`
- Run tests: `uv run python -m unittest discover -s tests -v`
- Show the CLI: `uv run scissorhands --help`

## Conventions

- Keep the core dependency-free unless a dependency clearly earns its place.
- Use absolute imports instead of relative imports.
- Keep agent-specific CLI behavior inside `src/scissorhands/agents.py`.
- Add or update tests for behavioral changes.
- Do not weaken sandboxing or enable automatic approvals by default.

