"""Compare two k6 summary exports (baseline and candidate) and fail on a regression.

Usage: compare.py BASELINE.json CANDIDATE.json

A missing baseline file (first run, or a base ref that cannot be built) leaves only
the absolute checks. A markdown report is printed for the GitHub job summary; the
exit code is 1 when any check fails.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

PHASE = "{phase:load}"


@dataclass(frozen=True)
class Limits:
    # Candidate p95 may be at most max_ratio times the baseline p95 plus noise_ms.
    max_ratio: float = 1.25
    noise_ms: float = 10.0
    max_error_rate: float = 0.01
    max_p95_ms: float = 500.0


def load_metrics(path: Path) -> dict[str, float]:
    metrics = json.loads(Path(path).read_text())["metrics"]
    return {
        "p95_ms": float(metrics[f"http_req_duration{PHASE}"]["p(95)"]),
        "error_rate": float(metrics[f"http_req_failed{PHASE}"]["value"]),
        "rps": float(metrics[f"http_reqs{PHASE}"]["rate"]),
    }


def evaluate(
    baseline: dict[str, float] | None, candidate: dict[str, float], limits: Limits
) -> list[str]:
    failures = []
    p95 = candidate["p95_ms"]

    if candidate["error_rate"] > limits.max_error_rate:
        failures.append(
            f"error rate {candidate['error_rate']:.2%} is over "
            f"{limits.max_error_rate:.2%}"
        )

    if p95 > limits.max_p95_ms:
        failures.append(f"p95 {p95:.1f} ms is over the {limits.max_p95_ms:.0f} ms limit")
    elif baseline is not None:
        allowed = baseline["p95_ms"] * limits.max_ratio + limits.noise_ms
        if p95 > allowed:
            failures.append(
                f"p95 {p95:.1f} ms regressed from {baseline['p95_ms']:.1f} ms "
                f"(allowed {allowed:.1f} ms)"
            )

    return failures


def report(
    baseline: dict[str, float] | None, candidate: dict[str, float], failures: list[str]
) -> str:
    def cell(run: dict[str, float] | None, key: str, fmt: str) -> str:
        return "n/a" if run is None else format(run[key], fmt)

    lines = [
        "### Performance (k6)",
        "",
        "| Metric | Baseline | Candidate |",
        "|---|---|---|",
        f"| p95 latency (ms) | {cell(baseline, 'p95_ms', '.1f')} "
        f"| {cell(candidate, 'p95_ms', '.1f')} |",
        f"| Error rate | {cell(baseline, 'error_rate', '.2%')} "
        f"| {cell(candidate, 'error_rate', '.2%')} |",
        f"| Throughput (req/s) | {cell(baseline, 'rps', '.1f')} "
        f"| {cell(candidate, 'rps', '.1f')} |",
        "",
    ]
    if baseline is None:
        lines.append("No baseline available; only absolute limits were checked.")
    lines.extend(f"- FAIL: {failure}" for failure in failures)
    if not failures:
        lines.append("Result: no regression.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    baseline_path, candidate_path = (Path(arg) for arg in argv)
    baseline = load_metrics(baseline_path) if baseline_path.exists() else None
    candidate = load_metrics(candidate_path)

    failures = evaluate(baseline, candidate, Limits())
    print(report(baseline, candidate, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
