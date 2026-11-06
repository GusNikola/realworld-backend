"""Fail the e2e job only on Postman failures that are not known and accepted.

Usage: check_failures.py NEWMAN_REPORT.json KNOWN_FAILURES.txt

Known failures are app bugs that the pipeline must not fix by changing app code;
listing them keeps the suite blocking for every other regression.
"""

import json
import sys
from pathlib import Path


def failure_keys(report: dict) -> list[str]:
    keys = []
    for failure in report["run"]["failures"]:
        error = failure["error"]
        detail = error.get("test") or error.get("message")
        keys.append(f"{failure['source']['name']} :: {detail}")
    return keys


def load_known(path: Path) -> set[str]:
    lines = (line.strip() for line in Path(path).read_text().splitlines())
    return {line for line in lines if line and not line.startswith("#")}


def main(argv: list[str]) -> int:
    report_path, known_path = argv
    failures = failure_keys(json.loads(Path(report_path).read_text()))
    known = load_known(Path(known_path))

    unexpected = [key for key in failures if key not in known]
    for key in failures:
        print(f"{'known' if key in known else 'FAIL'}: {key}")
    for key in sorted(known - set(failures)):
        print(f"known failure now passes, remove it from the list: {key}")

    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
