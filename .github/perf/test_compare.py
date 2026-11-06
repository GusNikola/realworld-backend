import json
from pathlib import Path

import pytest

from compare import Limits, evaluate, load_metrics, main

METRIC = "http_req_duration{phase:load}"
FAILED = "http_req_failed{phase:load}"
REQS = "http_reqs{phase:load}"


def write_summary(
    tmp_path: Path, name: str, p95: float, error_rate: float = 0.0, rate: float = 30.0
) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "metrics": {
                    METRIC: {"avg": p95 / 2, "p(95)": p95},
                    FAILED: {"value": error_rate},
                    REQS: {"count": int(rate * 60), "rate": rate},
                }
            }
        )
    )
    return path


def test_load_metrics_reads_load_phase(tmp_path: Path) -> None:
    path = write_summary(tmp_path, "s.json", p95=42.5, error_rate=0.002, rate=29.9)

    metrics = load_metrics(path)

    assert metrics == {"p95_ms": 42.5, "error_rate": 0.002, "rps": 29.9}


def test_equal_runs_pass() -> None:
    run = {"p95_ms": 40.0, "error_rate": 0.0, "rps": 30.0}

    assert evaluate(run, run, Limits()) == []


def test_slower_candidate_fails() -> None:
    baseline = {"p95_ms": 40.0, "error_rate": 0.0, "rps": 30.0}
    candidate = {"p95_ms": 70.0, "error_rate": 0.0, "rps": 30.0}

    failures = evaluate(baseline, candidate, Limits())

    assert len(failures) == 1
    assert "p95" in failures[0]


def test_small_absolute_difference_is_noise() -> None:
    # 8 ms -> 15 ms is +87%, but under the 10 ms noise floor on top of the ratio.
    baseline = {"p95_ms": 8.0, "error_rate": 0.0, "rps": 30.0}
    candidate = {"p95_ms": 15.0, "error_rate": 0.0, "rps": 30.0}

    assert evaluate(baseline, candidate, Limits()) == []


def test_error_rate_over_limit_fails() -> None:
    run = {"p95_ms": 40.0, "error_rate": 0.0, "rps": 30.0}
    candidate = {"p95_ms": 40.0, "error_rate": 0.05, "rps": 30.0}

    failures = evaluate(run, candidate, Limits())

    assert len(failures) == 1
    assert "error rate" in failures[0]


def test_absolute_p95_limit_applies_without_baseline() -> None:
    candidate = {"p95_ms": 900.0, "error_rate": 0.0, "rps": 30.0}

    failures = evaluate(None, candidate, Limits())

    assert len(failures) == 1
    assert "500" in failures[0]


def test_main_without_baseline_file_uses_absolute_checks(tmp_path: Path) -> None:
    candidate = write_summary(tmp_path, "candidate.json", p95=40.0)

    assert main([str(tmp_path / "missing.json"), str(candidate)]) == 0


def test_main_returns_1_on_regression(tmp_path: Path) -> None:
    baseline = write_summary(tmp_path, "baseline.json", p95=40.0)
    candidate = write_summary(tmp_path, "candidate.json", p95=80.0)

    assert main([str(baseline), str(candidate)]) == 1


def test_main_rejects_summary_without_load_phase(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"metrics": {}}))

    with pytest.raises(KeyError):
        main([str(broken), str(broken)])
