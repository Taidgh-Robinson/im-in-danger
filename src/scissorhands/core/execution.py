"""Invoke agents and stream their output to a log."""

import subprocess
from pathlib import Path


def run_command(
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
