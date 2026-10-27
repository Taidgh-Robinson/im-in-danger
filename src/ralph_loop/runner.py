"""Core iteration loop."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ralph_loop.agents import AgentAdapter
from ralph_loop.verification import VerificationResult, run_verification
from ralph_loop.work_items import WorkItem

DEFAULT_COMPLETION_MARKER = "<promise>COMPLETE</promise>"
_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


@dataclass(frozen=True, slots=True)
class LoopConfig:
    """Configuration for one bounded loop run."""

    root: Path
    work_item: WorkItem
    adapter: AgentAdapter
    executable: str
    max_iterations: int
    model: str | None = None
    auto_approve: bool = False
    completion_marker: str = DEFAULT_COMPLETION_MARKER


@dataclass(frozen=True, slots=True)
class LoopResult:
    """Outcome and artifacts from a loop run."""

    completed: bool
    iterations: int
    run_dir: Path
    failed: bool = False


def compose_prompt(
    work_item: WorkItem,
    iteration: int,
    marker: str,
    *,
    max_iterations: int,
    verification_feedback: str | None = None,
) -> str:
    """Add the repeatable loop contract to the user's task."""
    final_note = ""
    if iteration == max_iterations:
        final_note = """
This is the final iteration. Do not start large new pieces of work. Finish or safely wrap up what
is in progress, leave the repository in a working state, and make `.ralph/progress.md` a clear
handoff for whoever picks this up next.
"""
    feedback = ""
    if verification_feedback:
        feedback = f"""
## Verification feedback

The harness ran the verification commands after the previous iteration and they failed. Fix these
failures before starting anything else:

{verification_feedback}
"""
    return f"""{work_item.as_prompt()}
{feedback}
## RALPH iteration contract

This is iteration {iteration} of {max_iterations}. Work on the task now: inspect the repository,
make the most useful next changes, and run relevant verification. Do not merely describe what could
be done.

Use `.ralph/progress.md` as durable memory between fresh agent sessions. Read it if it exists. At
the end of this iteration, update it with completed work, verification results, important
decisions, and the clearest next step.
{final_note}
Only when every definition of done item and every acceptance criterion is genuinely satisfied,
include this exact marker on a line by itself in your final response:

{marker}

Do not emit the marker when work remains or verification is failing. When the work item lists
verification commands, the harness runs them after every iteration and ignores the marker unless
they all pass.
"""


def has_completion_marker(text: str, marker: str = DEFAULT_COMPLETION_MARKER) -> bool:
    """Match a marker only when it occupies a complete output line."""
    clean = _ANSI_ESCAPE.sub("", text)
    return any(line.strip() == marker for line in clean.splitlines())


def _run_command(
    command: list[str], prompt: str | None, log_path: Path, cwd: Path
) -> int:
    """Run an agent while teeing its combined output to the terminal and a log."""
    with (
        log_path.open("w", encoding="utf-8") as log,
        subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as process,
    ):
        assert process.stdout is not None
        if prompt is not None:
            assert process.stdin is not None
            process.stdin.write(prompt)
            process.stdin.close()
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        return process.wait()


def _report_verification(verification: VerificationResult) -> None:
    """Print a one-line status for each verification command."""
    print("\n--- Verification ---")
    for result in verification.results:
        status = "PASS" if result.passed else f"FAIL (exit {result.return_code})"
        print(f"{status}: {result.command}")
    if not verification.passed:
        print(verification.feedback(), file=sys.stderr)


def run_loop(
    config: LoopConfig,
    *,
    invoke: Callable[[list[str], str | None, Path, Path], int] = _run_command,
    verify: Callable[[Sequence[str], Path], VerificationResult] = run_verification,
) -> LoopResult:
    """Run fresh agent sessions until completion, failure, or the configured bound."""
    if config.max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")

    state_dir = config.root / ".ralph"
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = state_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    progress = state_dir / "progress.md"
    if not progress.exists():
        progress.write_text(
            "# RALPH progress\n\nNo iterations completed yet.\n", encoding="utf-8"
        )

    feedback: str | None = None
    for iteration in range(1, config.max_iterations + 1):
        log = run_dir / f"iteration-{iteration}.log"
        final_message = run_dir / f"iteration-{iteration}.final.txt"
        prompt = compose_prompt(
            config.work_item,
            iteration,
            config.completion_marker,
            max_iterations=config.max_iterations,
            verification_feedback=feedback,
        )
        command = config.adapter.command(
            executable=config.executable,
            root=config.root,
            final_message=final_message,
            model=config.model,
            auto_approve=config.auto_approve,
            prompt=prompt,
        )

        print(
            f"\n=== RALPH iteration {iteration}/{config.max_iterations} ({config.adapter.name}) ==="
        )
        stdin_prompt = prompt if config.adapter.uses_stdin else None
        return_code = invoke(command, stdin_prompt, log, config.root)
        if return_code != 0:
            print(
                f"Agent command failed with exit code {return_code}. Log: {log}",
                file=sys.stderr,
            )
            return LoopResult(
                completed=False,
                iterations=iteration,
                run_dir=run_dir,
                failed=True,
            )

        output = config.adapter.completion_output(log=log, final_message=final_message)
        claimed = has_completion_marker(output, config.completion_marker)
        if config.work_item.verification:
            verification = verify(config.work_item.verification, config.root)
            _report_verification(verification)
            if not verification.passed:
                feedback = verification.feedback()
                if claimed:
                    print(
                        "Ignoring the completion marker because verification failed.",
                        file=sys.stderr,
                    )
                continue
            feedback = None
        if claimed:
            return LoopResult(completed=True, iterations=iteration, run_dir=run_dir)

    return LoopResult(
        completed=False,
        iterations=config.max_iterations,
        run_dir=run_dir,
    )
