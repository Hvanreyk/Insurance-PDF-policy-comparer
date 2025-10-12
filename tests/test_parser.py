from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

from pdf_parser import parse_document_to_clauses


@pytest.fixture(scope="module")
def sample_policy_a() -> bytes:
    return Path("tests/fixtures/policy_A.pdf").read_bytes()


def test_parse_document_to_clauses(sample_policy_a: bytes) -> None:
    clauses = parse_document_to_clauses(sample_policy_a)
    assert len(clauses) >= 4
    titles = [clause.title for clause in clauses]
    assert "1. Insuring Agreement" in titles
    assert any(clause.type == "exclusion" for clause in clauses)
    assert all(clause.hash for clause in clauses)
