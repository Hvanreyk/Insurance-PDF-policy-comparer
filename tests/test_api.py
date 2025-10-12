from pathlib import Path
import sys
import types

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

google_stub = types.ModuleType("google")
google_cloud_stub = types.ModuleType("google.cloud")
storage_stub = types.ModuleType("google.cloud.storage")
storage_stub.Client = lambda *args, **kwargs: None
google_cloud_stub.storage = storage_stub

google_oauth_stub = types.ModuleType("google.oauth2")
service_account_stub = types.ModuleType("google.oauth2.service_account")
service_account_stub.Credentials = types.SimpleNamespace(
    from_service_account_info=lambda info: None
)
google_oauth_stub.service_account = service_account_stub

sys.modules.setdefault("google", google_stub)
sys.modules.setdefault("google.cloud", google_cloud_stub)
sys.modules.setdefault("google.cloud.storage", storage_stub)
sys.modules.setdefault("google.oauth2", google_oauth_stub)
sys.modules.setdefault("google.oauth2.service_account", service_account_stub)

requests_stub = types.ModuleType("requests")
requests_stub.post = lambda *args, **kwargs: types.SimpleNamespace(
    json=lambda: {},
    raise_for_status=lambda: None,
)
sys.modules.setdefault("requests", requests_stub)

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
