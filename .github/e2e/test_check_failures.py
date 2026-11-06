import json
from pathlib import Path

from check_failures import failure_keys, load_known, main


def report(*failures: tuple[str, str | None, str]) -> dict:
    return {
        "run": {
            "failures": [
                {"source": {"name": source}, "error": {"test": test, "message": message}}
                for source, test, message in failures
            ]
        }
    }


def write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


def test_failure_keys_use_request_and_assertion() -> None:
    data = report(("Articles by Tag", "The second tag is training", "expected false"))

    assert failure_keys(data) == ["Articles by Tag :: The second tag is training"]


def test_failure_without_assertion_uses_error_message() -> None:
    data = report(("Register", None, "connect ECONNREFUSED"))

    assert failure_keys(data) == ["Register :: connect ECONNREFUSED"]


def test_load_known_skips_comments_and_blank_lines(tmp_path: Path) -> None:
    path = write(tmp_path, "known.txt", "# comment\n\nA :: b\n")

    assert load_known(path) == {"A :: b"}


def test_only_known_failures_pass(tmp_path: Path) -> None:
    data = report(("Articles by Tag", "The second tag is training", "x"))
    report_path = write(tmp_path, "report.json", json.dumps(data))
    known = write(tmp_path, "known.txt", "Articles by Tag :: The second tag is training\n")

    assert main([str(report_path), str(known)]) == 0


def test_unexpected_failure_fails(tmp_path: Path) -> None:
    data = report(
        ("Articles by Tag", "The second tag is training", "x"),
        ("Login", "Response code is 200", "expected 500 to equal 200"),
    )
    report_path = write(tmp_path, "report.json", json.dumps(data))
    known = write(tmp_path, "known.txt", "Articles by Tag :: The second tag is training\n")

    assert main([str(report_path), str(known)]) == 1


def test_known_failure_that_now_passes_does_not_fail(tmp_path: Path) -> None:
    report_path = write(tmp_path, "report.json", json.dumps(report()))
    known = write(tmp_path, "known.txt", "Articles by Tag :: The second tag is training\n")

    assert main([str(report_path), str(known)]) == 0
