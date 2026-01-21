from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

from ucc.agents.document_layout import doc_id_from_pdf, get_layout_blocks, run_document_layout
from ucc.io.pdf_blocks import Block
from ucc.preprocess.furniture import remove_furniture


@pytest.fixture(scope="module")
def sample_policy_a() -> bytes:
    return Path("tests/fixtures/policy_A.pdf").read_bytes()


def test_document_layout_produces_blocks(tmp_path, monkeypatch, sample_policy_a: bytes) -> None:
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))

    doc_id = doc_id_from_pdf(sample_policy_a)
    result = run_document_layout(sample_policy_a, doc_id=doc_id, source_uri="policy_A.pdf")

    assert result.blocks
    block = result.blocks[0]
    assert block.id
    assert block.page_number >= 1
    assert block.bbox
    assert block.page_width > 0
    assert block.page_height > 0


def test_document_layout_section_paths_non_empty(tmp_path, monkeypatch, sample_policy_a: bytes) -> None:
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))

    doc_id = doc_id_from_pdf(sample_policy_a)
    result = run_document_layout(sample_policy_a, doc_id=doc_id)

    assert any(block.section_path for block in result.blocks)


def test_document_layout_persistence_round_trip(tmp_path, monkeypatch, sample_policy_a: bytes) -> None:
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))

    doc_id = doc_id_from_pdf(sample_policy_a)
    result = run_document_layout(sample_policy_a, doc_id=doc_id)
    persisted = get_layout_blocks(doc_id)

    assert len(persisted) == len(result.blocks)
    assert persisted[0].text == result.blocks[0].text
    assert persisted[0].section_path == result.blocks[0].section_path


def test_furniture_removal_drops_repeated_headers() -> None:
    blocks = [
        Block(
            id="p1",
            page_number=1,
            text="Policy Schedule",
            bbox=(100.0, 200.0, 400.0, 220.0),
            page_width=600.0,
            page_height=800.0,
        ),
        Block(
            id="p2",
            page_number=2,
            text="Policy Schedule",
            bbox=(100.0, 200.0, 400.0, 220.0),
            page_width=600.0,
            page_height=800.0,
        ),
        Block(
            id="b1",
            page_number=1,
            text="We will indemnify you for covered loss.",
            bbox=(120.0, 300.0, 500.0, 340.0),
            page_width=600.0,
            page_height=800.0,
        ),
    ]

    filtered = remove_furniture(blocks)
    texts = {block.text for block in filtered}
    assert "Policy Schedule" not in texts
    assert any("indemnify" in text for text in texts)
