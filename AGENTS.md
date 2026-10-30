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
- Keep loop execution and work-item state in `src/scissorhands/core/`.
- Keep contract templates and rendering in `src/scissorhands/prompting/`.
- Keep roadmap and design drafts in `docs/planning/`.
- Add or update tests for behavioral changes.
- Do not weaken sandboxing or enable automatic approvals by default.

