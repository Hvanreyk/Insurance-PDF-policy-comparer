import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

from ucc.facets.extract import diff_facets, extract_facets
from ucc.io.pdf_blocks import Block
from ucc.preprocess.furniture import dehyphenate, remove_furniture
from ucc.preprocess.toc import apply_sections
from ucc.retrieval.align import align_blocks
from ucc.typing.clauses import ClauseType, classify_clause


def _make_block(
    block_id: str,
    text: str,
    page: int = 1,
    bbox=(100.0, 200.0, 400.0, 300.0),
    page_size=(600.0, 800.0),
):
    return Block(
        id=block_id,
        page_number=page,
        text=text,
        bbox=bbox,
        page_width=page_size[0],
        page_height=page_size[1],
    )


def test_dehyphenate_and_furniture_filters():
    assert dehyphenate("cov-\nerage") == "coverage"

    blocks = [
        _make_block("p1", "Policy Schedule"),
        _make_block("p2", "Policy Schedule", page=2),
        _make_block("p3", "Page 3", bbox=(50.0, 30.0, 150.0, 60.0)),
        _make_block("p4", "Important cov-\nerage information"),
    ]

    filtered = remove_furniture(blocks)
    texts = [block.text for block in filtered]

    # repeated furniture and page numbers removed
    assert "Policy Schedule" not in texts
    assert all("Page" not in text for text in texts)
    # dehyphenated text preserved
    assert any("coverage" in text for text in texts)


def test_toc_whitelist_assigns_operational_sections():
    blocks = [
        _make_block("h1", "1 Cover"),
        _make_block("h2", "1.1 Flood Extension"),
        _make_block("b1", "We will indemnify you for flood."),
        _make_block("h3", "Privacy statement"),
        _make_block("b2", "We collect personal information."),
    ]
    apply_sections(blocks)

    cover_block = next(block for block in blocks if block.id == "b1")
    admin_block = next(block for block in blocks if block.id == "b2")

    assert cover_block.section_path == ["1 Cover", "1.1 Flood Extension"]
    assert cover_block.is_admin is False
    assert admin_block.is_admin is True


def test_clause_typing_priority_definition_overrides_grant():
    text = "\"Flood\" means water escaping. We will cover resulting damage."
    clause_type = classify_clause(text, {"DEFINITION", "GRANT"})
    assert clause_type is ClauseType.DEFINITION


def test_alignment_filters_by_clause_type():
    block_a = {"id": "a1", "text": "\"Flood\" means water.", "clause_type": "DEFINITION", "concepts": []}
    block_b = {"id": "b1", "text": "We will indemnify you.", "clause_type": "GRANT", "concepts": []}
    alignments = align_blocks([block_a], [block_b])
    assert alignments == []

    block_b2 = {"id": "b2", "text": "\"Flood\" means overflow.", "clause_type": "DEFINITION", "concepts": []}
    alignments = align_blocks([block_a], [block_b2])
    assert any(alignment.block_id_b == "b2" for alignment in alignments)


def test_facet_diff_highlights_broader_and_narrower():
    text_a = "We will cover storm surge and flood. Limit of liability is $1,000,000."
    text_b = "We will cover flood only. Limit of liability is $500,000."

    facets_a = extract_facets(text_a, ["Flood"])
    facets_b = extract_facets(text_b, ["Flood"])
    diff = diff_facets(facets_a, facets_b)

    assert any("broader" in entry.lower() for entry in diff["broader"])
    assert diff["changed_facets"].get("limit")
