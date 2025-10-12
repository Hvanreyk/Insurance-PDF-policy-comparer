from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

from ucc.pipeline import ComparisonOptions, UCCComparer


def load_bytes(name: str) -> bytes:
    return Path("tests/fixtures") / name


def read_fixture(name: str) -> bytes:
    return (Path("tests/fixtures") / name).read_bytes()


def test_compare_pipeline_returns_materiality_scores() -> None:
    comparer = UCCComparer(options=ComparisonOptions())
    result = comparer.compare(read_fixture("policy_A.pdf"), read_fixture("policy_B.pdf"))

    statuses = {match.status for match in result.matches}
    assert {"added", "removed", "modified"}.issubset(statuses)

    asbestos = next(match for match in result.matches if match.status == "added")
    assert asbestos.materiality_score >= 0.95

    sprinkler = next(match for match in result.matches if match.strictness_delta != 0)
    assert sprinkler.strictness_delta < 0
