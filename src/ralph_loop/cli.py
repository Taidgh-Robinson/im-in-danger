"""Command-line interface for the RALPH loop runner."""

from __future__ import annotations

import argparse
import shlex
import shutil
from pathlib import Path

from ralph_loop.agents import ADAPTERS, get_adapter
from ralph_loop.contract import default_contract, load_contract
from ralph_loop.runner import LoopConfig, compose_prompt, run_loop
from ralph_loop.work_items import load_work_item


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ralph",
        description="Run a bounded, fresh-session RALPH loop with Codex or OpenCode.",
    )
    parser.add_argument("--agent", choices=sorted(ADAPTERS), default="codex")
    parser.add_argument(
        "--work-item",
        type=Path,
        default=Path("WORK_ITEM.toml"),
        help="Path to a structured TOML work item (default: WORK_ITEM.toml)",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        help="Path to a custom iteration contract template (default: the built-in one)",
    )
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--model", help="Backend-specific model name")
    parser.add_argument("--executable", help="Override the selected agent executable")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Allow the backend to auto-approve tool permissions (review safety notes first)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print command and prompt, then exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path.cwd().resolve()
    work_item_path = (
        args.work_item if args.work_item.is_absolute() else root / args.work_item
    )

    if args.max_iterations < 1:
        raise SystemExit("--max-iterations must be at least 1")
    if not work_item_path.is_file():
        raise SystemExit(f"Work item does not exist: {work_item_path}")

    executable = args.executable or args.agent
    resolved = shutil.which(executable)
    if resolved is None:
        raise SystemExit(f"Agent executable not found: {executable}")

    adapter = get_adapter(args.agent)
    try:
        work_item = load_work_item(work_item_path)
        contract = load_contract(args.contract) if args.contract else default_contract()
    except ValueError as error:
        raise SystemExit(str(error)) from error

    if args.dry_run:
        prompt = compose_prompt(
            work_item,
            1,
            "<promise>COMPLETE</promise>",
            max_iterations=args.max_iterations,
            contract=contract,
        )
        preview_final = root / ".ralph" / "runs" / "DRY-RUN" / "iteration-1.final.txt"
        command = adapter.command(
            executable=resolved,
            root=root,
            final_message=preview_final,
            model=args.model,
            auto_approve=args.auto_approve,
            prompt=prompt,
        )
        print("Command:")
        display_command = command if adapter.uses_stdin else [*command[:-1], "<PROMPT>"]
        print(shlex.join(display_command))
        print("\nPrompt:\n")
        print(prompt)
        return 0

    result = run_loop(
        LoopConfig(
            root=root,
            work_item=work_item,
            contract=contract,
            adapter=adapter,
            executable=resolved,
            max_iterations=args.max_iterations,
            model=args.model,
            auto_approve=args.auto_approve,
        )
    )
    if result.completed:
        print(
            f"\nRALPH completed after {result.iterations} iteration(s). Logs: {result.run_dir}"
        )
        return 0
    if result.failed:
        return 1
    print(f"\nIteration limit reached without completion. Logs: {result.run_dir}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
