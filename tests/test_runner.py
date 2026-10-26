from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ralph_loop.agents import OpenCodeAdapter
from ralph_loop.runner import LoopConfig, has_completion_marker, run_loop


class CompletionMarkerTests(TestCase):
    def test_marker_must_occupy_a_line(self) -> None:
        self.assertTrue(has_completion_marker("Done\n<promise>COMPLETE</promise>\n"))
        self.assertFalse(has_completion_marker("Use <promise>COMPLETE</promise> when done"))

    def test_ansi_formatting_is_ignored(self) -> None:
        self.assertTrue(has_completion_marker("\x1b[32m<promise>COMPLETE</promise>\x1b[0m"))


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
                output = "still working\n" if calls == 1 else "<promise>COMPLETE</promise>\n"
                log.write_text(output, encoding="utf-8")
                return 0

            result = run_loop(
                LoopConfig(
                    root=root,
                    task="# Build the thing",
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
                    task="task",
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=3,
                ),
                invoke=fail,
            )

            self.assertTrue(result.failed)
            self.assertEqual(result.iterations, 1)

