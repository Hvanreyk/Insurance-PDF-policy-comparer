from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _fixture_bytes(name: str) -> bytes:
    return (Path("tests/fixtures") / name).read_bytes()


def test_compare_clauses_endpoint_success() -> None:
    response = client.post(
        "/api/compare-clauses",
        files={
            "file_a": ("policy_A.pdf", _fixture_bytes("policy_A.pdf"), "application/pdf"),
            "file_b": ("policy_B.pdf", _fixture_bytes("policy_B.pdf"), "application/pdf"),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "matches" in data and data["matches"]
    assert "summary" in data


def test_compare_clauses_endpoint_empty_file() -> None:
    response = client.post(
        "/api/compare-clauses",
        files={
            "file_a": ("policy_A.pdf", _fixture_bytes("policy_A.pdf"), "application/pdf"),
            "file_b": ("empty.pdf", b"", "application/pdf"),
        },
    )
    assert response.status_code == 400
