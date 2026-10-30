"""Terminal presentation of iteration observations and decisions."""

import sys
from pathlib import Path

from scissorhands.core.iteration import IterationRecord
from scissorhands.core.status import CriterionStatus, format_status
from scissorhands.core.verification import VerificationResult


def report_status(
    path: Path, statuses: tuple[CriterionStatus, ...] | None, *, updated: bool
) -> None:
    print("\n--- Criteria status ---")
    if statuses is None:
        print(f"No readable status in {path}.")
        return
    if not updated:
        print("(not updated this iteration)")
    print(format_status(statuses))


def report_verification(verification: VerificationResult) -> None:
    print("\n--- Verification ---")
    for result in verification.results:
        status = "PASS" if result.passed else f"FAIL (exit {result.return_code})"
        print(f"{status}: {result.command}")
    if not verification.passed:
        print(verification.feedback(), file=sys.stderr)


def report_iteration(record: IterationRecord, log: Path) -> None:
    decision = record.decision
    if record.agent_exit_code != 0:
        print(
            f"Agent command failed with exit code {record.agent_exit_code}. Log: {log}",
            file=sys.stderr,
        )
    elif record.marker_claimed and decision.rejection_reason is not None:
        print(
            f"Ignoring the completion marker because {decision.rejection_reason}.",
            file=sys.stderr,
        )
