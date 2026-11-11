"""Reject mypy regressions while reducing the initial diagnostic baseline."""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "config" / "mypy-baseline.json"


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--output", "json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    if result.returncode not in {0, 1}:
        print(result.stdout, file=sys.stderr, end="")
        return result.returncode

    errors = Counter()
    locations = {}
    for line in result.stdout.splitlines():
        diagnostic = json.loads(line)
        if diagnostic["severity"] != "error":
            continue
        path, code = diagnostic["file"], diagnostic["code"]
        key = (path, code)
        errors[key] += 1
        locations.setdefault(key, []).append(diagnostic)
    if result.returncode == 1 and not errors:
        return 1

    baseline = Counter(
        {
            (path, code): count
            for path, codes in json.loads(BASELINE.read_text()).items()
            for code, count in codes.items()
        }
    )
    regressions = errors - baseline
    for path, code in sorted(regressions):
        print(f"{path}: {errors[path, code]} [{code}], baseline {baseline[path, code]}")
        for diagnostic in locations[path, code]:
            print(f"  line {diagnostic['line']}: {diagnostic['message']}")
    if regressions:
        return 1
    print(
        f"Mypy passed with {errors.total()} existing diagnostics within the baseline."
    )
    if errors != baseline:
        print("Reduce the checked-in baseline to reflect the resolved diagnostics.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
