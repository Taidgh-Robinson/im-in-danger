"""Orchestrate bounded agent iterations."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from scissorhands.agents import AgentAdapter
from scissorhands.core.execution import run_command
from scissorhands.core.iteration import IterationRecord
from scissorhands.core.receipts import write_iteration_receipt
from scissorhands.core.reporting import (
    report_iteration,
    report_status,
    report_verification,
)
from scissorhands.core.status import STATUS_FILE, read_status
from scissorhands.core.verification import VerificationResult, run_verification
from scissorhands.core.work_items import WorkItem
from scissorhands.prompting.compose import compose_prompt
from scissorhands.prompting.contract import default_contract

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
    contract: str = field(default_factory=default_contract)


@dataclass(frozen=True, slots=True)
class LoopResult:
    """Outcome and artifacts from a loop run."""

    completed: bool
    iterations: int
    run_dir: Path
    failed: bool = False


def has_completion_marker(text: str, marker: str = DEFAULT_COMPLETION_MARKER) -> bool:
    """Match a marker only when it occupies a complete output line."""
    clean = _ANSI_ESCAPE.sub("", text)
    return any(line.strip() == marker for line in clean.splitlines())


def _modified_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


Invoke = Callable[[list[str], str | None, Path, Path], int]
Verify = Callable[[Sequence[str], Path], VerificationResult]


@dataclass(frozen=True, slots=True)
class RunPaths:
    run_dir: Path
    status: Path
    progress: Path


@dataclass(frozen=True, slots=True)
class PreparedIteration:
    number: int
    prompt: str
    command: list[str]
    log: Path
    final_message: Path


def initialize_run(root: Path) -> RunPaths:
    state_dir = root / ".scissorhands"
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = state_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    progress = state_dir / "progress.md"
    if not progress.exists():
        progress.write_text(
            "# Scissorhands progress\n\nNo iterations completed yet.\n",
            encoding="utf-8",
        )
    return RunPaths(run_dir, state_dir / STATUS_FILE, progress)


def prepare_iteration(
    config: LoopConfig, run_dir: Path, number: int, feedback: str | None
) -> PreparedIteration:
    prompt = compose_prompt(
        config.work_item,
        number,
        config.completion_marker,
        max_iterations=config.max_iterations,
        verification_feedback=feedback,
        contract=config.contract,
    )
    final_message = run_dir / f"iteration-{number}.final.txt"
    command = config.adapter.command(
        executable=config.executable,
        root=config.root,
        final_message=final_message,
        model=config.model,
        auto_approve=config.auto_approve,
        prompt=prompt,
    )
    return PreparedIteration(
        number, prompt, command, run_dir / f"iteration-{number}.log", final_message
    )


def execute_iteration(
    config: LoopConfig,
    paths: RunPaths,
    prepared: PreparedIteration,
    *,
    invoke: Invoke,
    verify: Verify,
) -> IterationRecord:
    print(
        f"\n=== Scissorhands iteration {prepared.number}/{config.max_iterations} "
        f"({config.adapter.name}) ==="
    )
    status_before = _modified_ns(paths.status)
    progress_before = _modified_ns(paths.progress)
    stdin_prompt = prepared.prompt if config.adapter.uses_stdin else None
    return_code = invoke(prepared.command, stdin_prompt, prepared.log, config.root)
    status_updated = _modified_ns(paths.status) != status_before
    progress_updated = _modified_ns(paths.progress) != progress_before
    statuses = read_status(paths.status, config.work_item.checklist())
    claimed = False
    verification = None
    if return_code == 0:
        report_status(paths.status, statuses, updated=status_updated)
        output = config.adapter.completion_output(
            log=prepared.log, final_message=prepared.final_message
        )
        claimed = has_completion_marker(output, config.completion_marker)
        if config.work_item.verification:
            verification = verify(config.work_item.verification, config.root)
            report_verification(verification)
    return IterationRecord(
        iteration=prepared.number,
        agent=config.adapter.name,
        agent_exit_code=return_code,
        statuses=statuses,
        status_updated=status_updated,
        progress=_read_text(paths.progress),
        progress_updated=progress_updated,
        verification=verification,
        verification_required=bool(config.work_item.verification),
        marker_claimed=claimed,
        final_iteration=prepared.number == config.max_iterations,
    )


def run_loop(
    config: LoopConfig,
    *,
    invoke: Invoke = run_command,
    verify: Verify = run_verification,
) -> LoopResult:
    """Run fresh agent sessions until completion, failure, or the configured bound."""
    if config.max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    paths = initialize_run(config.root)
    feedback: str | None = None
    for number in range(1, config.max_iterations + 1):
        prepared = prepare_iteration(config, paths.run_dir, number, feedback)
        record = execute_iteration(
            config, paths, prepared, invoke=invoke, verify=verify
        )
        write_iteration_receipt(paths.run_dir / f"iteration-{number}.json", record)
        report_iteration(record, prepared.log)
        decision = record.decision
        if decision.accepted or decision.outcome == "agent_failed":
            return LoopResult(
                completed=decision.accepted,
                iterations=number,
                run_dir=paths.run_dir,
                failed=decision.outcome == "agent_failed",
            )
        feedback = record.verification_feedback
    return LoopResult(
        completed=False,
        iterations=config.max_iterations,
        run_dir=paths.run_dir,
    )
