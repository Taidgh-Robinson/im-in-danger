from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ralph_loop.agents import OpenCodeAdapter
from ralph_loop.runner import (
    LoopConfig,
    compose_prompt,
    has_completion_marker,
    run_loop,
)
from ralph_loop.verification import CommandResult, VerificationResult
from ralph_loop.work_items import WorkItem

WORK_ITEM = WorkItem(
    title="Build the thing",
    description="Build the requested thing.",
    definition_of_done=("Tests pass.",),
    acceptance_criteria=("The thing works.",),
)
VERIFIED_WORK_ITEM = replace(WORK_ITEM, verification=("make test",))
MARKER = "<promise>COMPLETE</promise>"


class CompletionMarkerTests(TestCase):
    def test_marker_must_occupy_a_line(self) -> None:
        self.assertTrue(has_completion_marker("Done\n<promise>COMPLETE</promise>\n"))
        self.assertFalse(
            has_completion_marker("Use <promise>COMPLETE</promise> when done")
        )

    def test_ansi_formatting_is_ignored(self) -> None:
        self.assertTrue(
            has_completion_marker("\x1b[32m<promise>COMPLETE</promise>\x1b[0m")
        )


class LoopTests(TestCase):
    def test_loop_repeats_until_completion(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            calls = 0

            def fake_invoke(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                nonlocal calls
                calls += 1
                self.assertEqual(cwd, root)
                self.assertIsNone(prompt)
                self.assertIn(f"iteration {calls}", command[-1])
                output = (
                    "still working\n" if calls == 1 else "<promise>COMPLETE</promise>\n"
                )
                log.write_text(output, encoding="utf-8")
                return 0

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=3,
                ),
                invoke=fake_invoke,
            )

            self.assertTrue(result.completed)
            self.assertEqual(result.iterations, 2)
            self.assertEqual(calls, 2)
            self.assertTrue((root / ".ralph" / "progress.md").exists())

    def test_loop_stops_on_agent_failure(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def fail(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                log.write_text("failed", encoding="utf-8")
                return 7

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=3,
                ),
                invoke=fail,
            )

            self.assertTrue(result.failed)
            self.assertEqual(result.iterations, 1)

    def test_verification_is_skipped_without_commands(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def complete(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                log.write_text("<promise>COMPLETE</promise>\n", encoding="utf-8")
                return 0

            def unexpected_verify(
                commands: Sequence[str], cwd: Path
            ) -> VerificationResult:
                self.fail("verification should not run without commands")

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=3,
                ),
                invoke=complete,
                verify=unexpected_verify,
            )

            self.assertTrue(result.completed)
            self.assertEqual(result.iterations, 1)

    def test_marker_is_ignored_until_verification_passes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prompts: list[str] = []
            verify_calls = 0

            def complete(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                prompts.append(command[-1])
                log.write_text("<promise>COMPLETE</promise>\n", encoding="utf-8")
                return 0

            def verify(commands: Sequence[str], cwd: Path) -> VerificationResult:
                nonlocal verify_calls
                verify_calls += 1
                self.assertEqual(list(commands), ["make test"])
                self.assertEqual(cwd, root)
                code = 1 if verify_calls == 1 else 0
                return VerificationResult(
                    (CommandResult("make test", code, "FAILED test_thing\n"),)
                )

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=VERIFIED_WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=3,
                ),
                invoke=complete,
                verify=verify,
            )

            self.assertTrue(result.completed)
            self.assertEqual(result.iterations, 2)
            self.assertNotIn("## Verification feedback", prompts[0])
            self.assertIn("## Verification feedback", prompts[1])
            self.assertIn("FAILED test_thing", prompts[1])

    def test_failing_verification_exhausts_the_iteration_limit(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def complete(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                log.write_text("<promise>COMPLETE</promise>\n", encoding="utf-8")
                return 0

            def always_fail(commands: Sequence[str], cwd: Path) -> VerificationResult:
                return VerificationResult((CommandResult("make test", 1, ""),))

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=VERIFIED_WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=2,
                ),
                invoke=complete,
                verify=always_fail,
            )

            self.assertFalse(result.completed)
            self.assertFalse(result.failed)
            self.assertEqual(result.iterations, 2)


class ComposePromptTests(TestCase):
    def test_completion_requires_definition_of_done_and_acceptance(self) -> None:
        prompt = compose_prompt(WORK_ITEM, 1, MARKER, max_iterations=3)

        self.assertIn(
            "every definition of done item and every acceptance criterion", prompt
        )

    def test_prompt_states_the_iteration_budget(self) -> None:
        prompt = compose_prompt(WORK_ITEM, 2, MARKER, max_iterations=5)

        self.assertIn("This is iteration 2 of 5.", prompt)
        self.assertNotIn("This is the final iteration.", prompt)

    def test_final_iteration_asks_for_a_clean_handoff(self) -> None:
        prompt = compose_prompt(WORK_ITEM, 5, MARKER, max_iterations=5)

        self.assertIn("This is iteration 5 of 5.", prompt)
        self.assertIn("This is the final iteration.", prompt)
        self.assertIn("Do not start large new pieces of work.", prompt)
