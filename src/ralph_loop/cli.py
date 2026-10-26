"""Command-line interface for the RALPH loop runner."""

from __future__ import annotations

import argparse
import shlex
import shutil
from pathlib import Path

from .agents import ADAPTERS, get_adapter
from .runner import LoopConfig, compose_prompt, run_loop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ralph",
        description="Run a bounded, fresh-session RALPH loop with Codex or OpenCode.",
    )
    parser.add_argument("--agent", choices=sorted(ADAPTERS), default="codex")
    parser.add_argument("--prompt", type=Path, default=Path("PROMPT.md"))
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--model", help="Backend-specific model name")
    parser.add_argument("--executable", help="Override the selected agent executable")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Allow the backend to auto-approve tool permissions (review safety notes first)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print command and prompt, then exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path.cwd().resolve()
    prompt_path = args.prompt if args.prompt.is_absolute() else root / args.prompt

    if args.max_iterations < 1:
        raise SystemExit("--max-iterations must be at least 1")
    if not prompt_path.is_file():
        raise SystemExit(f"Prompt file does not exist: {prompt_path}")

    executable = args.executable or args.agent
    resolved = shutil.which(executable)
    if resolved is None:
        raise SystemExit(f"Agent executable not found: {executable}")

    adapter = get_adapter(args.agent)
    task = prompt_path.read_text(encoding="utf-8")

    if args.dry_run:
        preview_final = root / ".ralph" / "runs" / "DRY-RUN" / "iteration-1.final.txt"
        command = adapter.command(
            executable=resolved,
            root=root,
            final_message=preview_final,
            model=args.model,
            auto_approve=args.auto_approve,
            prompt=compose_prompt(task, 1, "<promise>COMPLETE</promise>"),
        )
        print("Command:")
        display_command = command if adapter.uses_stdin else [*command[:-1], "<PROMPT>"]
        print(shlex.join(display_command))
        print("\nPrompt:\n")
        print(compose_prompt(task, 1, "<promise>COMPLETE</promise>"))
        return 0

    result = run_loop(
        LoopConfig(
            root=root,
            task=task,
            adapter=adapter,
            executable=resolved,
            max_iterations=args.max_iterations,
            model=args.model,
            auto_approve=args.auto_approve,
        )
    )
    if result.completed:
        print(f"\nRALPH completed after {result.iterations} iteration(s). Logs: {result.run_dir}")
        return 0
    if result.failed:
        return 1
    print(f"\nIteration limit reached without completion. Logs: {result.run_dir}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

