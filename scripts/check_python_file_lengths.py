"""Enforce the repository's Python file size limit from a Git checkout."""

import os
import subprocess
from pathlib import Path

MAX_LINES = 450
PYTHON_ROOTS = ("src", "tests", "scripts")
ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    inventory = subprocess.check_output(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            *PYTHON_ROOTS,
        ],
        cwd=ROOT,
    )
    checked = 0
    violations = []
    for name in sorted(set(inventory.split(b"\0"))):
        path = ROOT / os.fsdecode(name)
        if path.suffix != ".py" or not path.is_file():
            continue
        checked += 1
        lines = len(path.read_bytes().splitlines())
        if lines > MAX_LINES:
            violations.append((path.relative_to(ROOT), lines))

    for path, lines in violations:
        print(f"{path.as_posix()}: {lines} lines (maximum {MAX_LINES})")
    if violations:
        print(f"{len(violations)} Python files exceed the {MAX_LINES}-line limit.")
        return 1
    print(f"Checked {checked} Python files. Maximum {MAX_LINES} lines per file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
