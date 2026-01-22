"""Tests for Segment 2: Definitions Agent."""

from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

from ucc.agents.definitions import (
    _build_definition_graph,
    _canonicalize_term,
    _deduplicate_definitions,
    _expand_block_text,
    _extract_definitions_from_blocks,
    _find_mentions,
    _is_definition_zone,
    _RawDefinition,
    _truncate_definition,
    get_definitions,
    get_expanded_block_text,
    get_term_mentions,
    run_definitions_agent,
)
from ucc.agents.document_layout import doc_id_from_pdf, run_document_layout
from ucc.io.pdf_blocks import Block
from ucc.storage.definitions_store import Definition, DefinitionType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_policy_a() -> bytes:
    return Path("tests/fixtures/policy_A.pdf").read_bytes()


def _make_block(
    block_id: str,
    text: str,
    page: int = 1,
    section_path: list[str] | None = None,
    is_admin: bool = False,
    bbox: tuple = (100.0, 200.0, 400.0, 300.0),
    page_size: tuple = (600.0, 800.0),
) -> Block:
    block = Block(
        id=block_id,
        page_number=page,
        text=text,
        bbox=bbox,
        page_width=page_size[0],
        page_height=page_size[1],
    )
    block.section_path = section_path or []
    block.is_admin = is_admin
    return block


# ---------------------------------------------------------------------------
# Unit Tests: Canonicalization
# ---------------------------------------------------------------------------


def test_canonicalize_term_basic():
    assert _canonicalize_term("Flood") == "FLOOD"
    assert _canonicalize_term('"Flood"') == "FLOOD"
    assert _canonicalize_term("  Flood Damage  ") == "FLOOD DAMAGE"


def test_canonicalize_term_with_punctuation():
    assert _canonicalize_term("'Covered Loss'") == "COVERED LOSS"
    assert _canonicalize_term('"Named Insured"') == "NAMED INSURED"


def test_canonicalize_term_collapses_whitespace():
    assert _canonicalize_term("Property   Damage") == "PROPERTY DAMAGE"


# ---------------------------------------------------------------------------
# Unit Tests: Definition Zone Detection
# ---------------------------------------------------------------------------


def test_is_definition_zone_positive():
    assert _is_definition_zone(["Definitions"])
    assert _is_definition_zone(["Section 1", "Definitions"])
    assert _is_definition_zone(["Glossary"])
    assert _is_definition_zone(["What words mean"])
    assert _is_definition_zone(["Meaning of words"])


def test_is_definition_zone_negative():
    assert not _is_definition_zone(["Cover"])
    assert not _is_definition_zone(["Exclusions"])
    assert not _is_definition_zone([])


# ---------------------------------------------------------------------------
# Unit Tests: Truncation
# ---------------------------------------------------------------------------


def test_truncate_definition_short():
    short = "Water entering the building"
    assert _truncate_definition(short, max_length=220) == short


def test_truncate_definition_long():
    long_text = "A" * 300
    truncated = _truncate_definition(long_text, max_length=100)
    assert len(truncated) <= 103  # 100 + "..."
    assert truncated.endswith("...")


def test_truncate_definition_preserves_word_boundary():
    text = "Water entering the building through external openings caused by flood"
    truncated = _truncate_definition(text, max_length=40)
    assert "..." in truncated
    # Should not cut mid-word
    assert not truncated[:-3].endswith(" ")  # Account for ellipsis


# ---------------------------------------------------------------------------
# Unit Tests: Definition Extraction
# ---------------------------------------------------------------------------


def test_extract_definitions_quoted_glossary():
    blocks = [
        _make_block(
            "b1",
            '"Flood" means water entering the building through external openings.',
            section_path=["Definitions"],
        ),
    ]
    raw_defs = _extract_definitions_from_blocks(blocks)
    assert len(raw_defs) == 1
    assert raw_defs[0].term_surface == "Flood"
    assert "water entering" in raw_defs[0].definition_text
    assert raw_defs[0].definition_type == DefinitionType.GLOSSARY
    assert raw_defs[0].confidence >= 0.9


def test_extract_definitions_unquoted_glossary():
    blocks = [
        _make_block(
            "b1",
            "Property Damage means physical damage to tangible property.",
            section_path=["Definitions"],
        ),
    ]
    raw_defs = _extract_definitions_from_blocks(blocks)
    assert len(raw_defs) == 1
    assert raw_defs[0].term_surface == "Property Damage"


def test_extract_definitions_colon_pattern():
    blocks = [
        _make_block(
            "b1",
            "Covered Loss: any direct physical loss or damage to insured property.",
            section_path=["Definitions"],
        ),
    ]
    raw_defs = _extract_definitions_from_blocks(blocks)
    assert len(raw_defs) == 1
    assert raw_defs[0].term_surface == "Covered Loss"


def test_extract_definitions_inline():
    blocks = [
        _make_block(
            "b1",
            'We will cover "Flood" means water overflow from natural sources.',
            section_path=["Cover"],
        ),
    ]
    raw_defs = _extract_definitions_from_blocks(blocks)
    assert len(raw_defs) == 1
    assert raw_defs[0].definition_type == DefinitionType.INLINE
    assert raw_defs[0].confidence < 0.9  # Lower confidence for inline


def test_extract_definitions_skips_admin_blocks():
    blocks = [
        _make_block(
            "b1",
            '"Privacy" means your personal information.',
            section_path=["Privacy Statement"],
            is_admin=True,
        ),
    ]
    raw_defs = _extract_definitions_from_blocks(blocks)
    assert len(raw_defs) == 0


# ---------------------------------------------------------------------------
# Unit Tests: Deduplication
# ---------------------------------------------------------------------------


def test_deduplicate_definitions_keeps_highest_confidence():
    raw = [
        _RawDefinition(
            term_surface="Flood",
            definition_text="Water overflow",
            source_block_id="b1",
            source_page=1,
            confidence=0.6,
            definition_type=DefinitionType.INLINE,
        ),
        _RawDefinition(
            term_surface="Flood",
            definition_text="Water entering building",
            source_block_id="b2",
            source_page=2,
            confidence=0.95,
            definition_type=DefinitionType.GLOSSARY,
        ),
    ]
    deduped = _deduplicate_definitions(raw, "doc123")
    assert len(deduped) == 1
    assert deduped[0].confidence == 0.95
    assert "entering building" in deduped[0].definition_text


# ---------------------------------------------------------------------------
# Unit Tests: Mentions
# ---------------------------------------------------------------------------


def test_find_mentions_basic():
    definitions = [
        Definition(
            definition_id="def1",
            doc_id="doc1",
            term_canonical="FLOOD",
            term_surface="Flood",
            definition_text="Water overflow",
            source_block_id="b1",
            source_page=1,
            confidence=0.95,
            definition_type=DefinitionType.GLOSSARY,
        ),
    ]
    blocks = [
        _make_block("b2", "We will cover Flood damage to your property.", page=2),
        _make_block("b3", "Flood is excluded when caused by negligence.", page=3),
    ]
    mentions = _find_mentions(blocks, definitions, "doc1")
    
    assert len(mentions) == 2
    terms = [m.term_canonical for m in mentions]
    assert all(t == "FLOOD" for t in terms)


def test_find_mentions_case_insensitive():
    definitions = [
        Definition(
            definition_id="def1",
            doc_id="doc1",
            term_canonical="NAMED INSURED",
            term_surface="Named Insured",
            definition_text="The person named in the schedule",
            source_block_id="b1",
            source_page=1,
            confidence=0.95,
            definition_type=DefinitionType.GLOSSARY,
        ),
    ]
    blocks = [
        _make_block("b2", "The NAMED INSURED must notify us immediately.", page=2),
        _make_block("b3", "If the named insured fails to comply.", page=3),
    ]
    mentions = _find_mentions(blocks, definitions, "doc1")
    assert len(mentions) == 2


def test_find_mentions_excludes_definition_source_block():
    definitions = [
        Definition(
            definition_id="def1",
            doc_id="doc1",
            term_canonical="FLOOD",
            term_surface="Flood",
            definition_text="Water overflow",
            source_block_id="b1",
            source_page=1,
            confidence=0.95,
            definition_type=DefinitionType.GLOSSARY,
        ),
    ]
    blocks = [
        _make_block("b1", '"Flood" means water overflow.', section_path=["Definitions"]),
        _make_block("b2", "We cover Flood damage.", page=2),
    ]
    mentions = _find_mentions(blocks, definitions, "doc1")
    
    # Should only find mention in b2, not in the definition source b1
    assert len(mentions) == 1
    assert mentions[0].block_id == "b2"


def test_find_mentions_excludes_admin_blocks():
    definitions = [
        Definition(
            definition_id="def1",
            doc_id="doc1",
            term_canonical="FLOOD",
            term_surface="Flood",
            definition_text="Water overflow",
            source_block_id="b1",
            source_page=1,
            confidence=0.95,
            definition_type=DefinitionType.GLOSSARY,
        ),
    ]
    blocks = [
        _make_block("b2", "Flood is mentioned in privacy section.", is_admin=True),
        _make_block("b3", "We cover Flood damage.", page=2),
    ]
    mentions = _find_mentions(blocks, definitions, "doc1")
    
    assert len(mentions) == 1
    assert mentions[0].block_id == "b3"


# ---------------------------------------------------------------------------
# Unit Tests: Block Expansion
# ---------------------------------------------------------------------------


def test_expand_block_text_basic():
    definitions = [
        Definition(
            definition_id="def1",
            doc_id="doc1",
            term_canonical="FLOOD",
            term_surface="Flood",
            definition_text="water entering the building through external openings",
            source_block_id="b1",
            source_page=1,
            confidence=0.95,
            definition_type=DefinitionType.GLOSSARY,
        ),
    ]
    from ucc.storage.definitions_store import TermMention
    
    block = _make_block("b2", "We will cover Flood damage to your property.")
    mentions = [
        TermMention(
            mention_id="m1",
            doc_id="doc1",
            block_id="b2",
            term_canonical="FLOOD",
            span_start=14,
            span_end=19,
            context_snippet="cover Flood damage",
        ),
    ]
    
    graph = _build_definition_graph(definitions)
    expanded, meta = _expand_block_text(block, definitions, mentions, graph)
    
    assert "Flood [defined as:" in expanded
    assert "water entering" in expanded
    assert meta["terms_expanded"] == ["FLOOD"]
    assert meta["depth"] == 1


def test_expand_block_text_deterministic():
    definitions = [
        Definition(
            definition_id="def1",
            doc_id="doc1",
            term_canonical="FLOOD",
            term_surface="Flood",
            definition_text="water overflow",
            source_block_id="b1",
            source_page=1,
            confidence=0.95,
            definition_type=DefinitionType.GLOSSARY,
        ),
    ]
    from ucc.storage.definitions_store import TermMention
    
    block = _make_block("b2", "Flood damage and more Flood issues.")
    mentions = [
        TermMention(
            mention_id="m1",
            doc_id="doc1",
            block_id="b2",
            term_canonical="FLOOD",
            span_start=0,
            span_end=5,
            context_snippet="Flood damage",
        ),
        TermMention(
            mention_id="m2",
            doc_id="doc1",
            block_id="b2",
            term_canonical="FLOOD",
            span_start=22,
            span_end=27,
            context_snippet="more Flood issues",
        ),
    ]
    
    graph = _build_definition_graph(definitions)
    
    # Run twice to verify determinism
    expanded1, meta1 = _expand_block_text(block, definitions, mentions, graph)
    expanded2, meta2 = _expand_block_text(block, definitions, mentions, graph)
    
    assert expanded1 == expanded2
    assert meta1 == meta2


def test_expand_block_text_truncates_long_definitions():
    long_def = "A" * 500
    definitions = [
        Definition(
            definition_id="def1",
            doc_id="doc1",
            term_canonical="FLOOD",
            term_surface="Flood",
            definition_text=long_def,
            source_block_id="b1",
            source_page=1,
            confidence=0.95,
            definition_type=DefinitionType.GLOSSARY,
        ),
    ]
    from ucc.storage.definitions_store import TermMention
    
    block = _make_block("b2", "We cover Flood.")
    mentions = [
        TermMention(
            mention_id="m1",
            doc_id="doc1",
            block_id="b2",
            term_canonical="FLOOD",
            span_start=9,
            span_end=14,
            context_snippet="cover Flood",
        ),
    ]
    
    graph = _build_definition_graph(definitions)
    expanded, meta = _expand_block_text(block, definitions, mentions, graph)
    
    assert meta["truncated"] is True
    assert "..." in expanded


def test_expand_block_text_no_mentions():
    definitions = [
        Definition(
            definition_id="def1",
            doc_id="doc1",
            term_canonical="FLOOD",
            term_surface="Flood",
            definition_text="water overflow",
            source_block_id="b1",
            source_page=1,
            confidence=0.95,
            definition_type=DefinitionType.GLOSSARY,
        ),
    ]
    
    block = _make_block("b2", "We cover storm damage.")
    
    graph = _build_definition_graph(definitions)
    expanded, meta = _expand_block_text(block, definitions, [], graph)
    
    assert expanded == block.text
    assert meta["terms_expanded"] == []
    assert meta["depth"] == 0


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


def test_run_definitions_agent_with_sample_pdf(tmp_path, monkeypatch, sample_policy_a):
    """Integration test: run full agent on sample PDF."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    # Run Segment 1 first
    run_document_layout(sample_policy_a, doc_id=doc_id)
    
    # Run Segment 2
    result = run_definitions_agent(doc_id)
    
    # Should have extracted at least some definitions
    assert result.doc_id == doc_id
    # The sample PDF should have at least one definition
    # (this depends on the actual PDF content)
    assert isinstance(result.definitions, list)
    assert isinstance(result.mentions, list)
    assert isinstance(result.expansions, list)
    
    # Expansions should exist for all blocks
    assert len(result.expansions) > 0


def test_definitions_persistence_round_trip(tmp_path, monkeypatch, sample_policy_a):
    """Test that definitions are correctly persisted and retrieved."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    # Run both segments
    run_document_layout(sample_policy_a, doc_id=doc_id)
    result = run_definitions_agent(doc_id)
    
    # Retrieve from persistence
    persisted_defs = get_definitions(doc_id)
    
    assert len(persisted_defs) == len(result.definitions)
    
    if result.definitions:
        assert persisted_defs[0].term_canonical == result.definitions[0].term_canonical


def test_definitions_idempotent(tmp_path, monkeypatch, sample_policy_a):
    """Running agent twice should not duplicate data."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    # Run Segment 1
    run_document_layout(sample_policy_a, doc_id=doc_id)
    
    # Run Segment 2 twice
    result1 = run_definitions_agent(doc_id)
    result2 = run_definitions_agent(doc_id)
    
    # Results should be identical
    assert len(result1.definitions) == len(result2.definitions)
    assert len(result1.mentions) == len(result2.mentions)
    assert len(result1.expansions) == len(result2.expansions)


def test_get_expanded_block_text_api(tmp_path, monkeypatch, sample_policy_a):
    """Test the get_expanded_block_text retrieval API."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    run_document_layout(sample_policy_a, doc_id=doc_id)
    result = run_definitions_agent(doc_id)
    
    if result.expansions:
        block_id = result.expansions[0].block_id
        expanded = get_expanded_block_text(doc_id, block_id)
        assert expanded is not None
        assert isinstance(expanded, str)


def test_get_term_mentions_api(tmp_path, monkeypatch, sample_policy_a):
    """Test the get_term_mentions retrieval API."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    run_document_layout(sample_policy_a, doc_id=doc_id)
    result = run_definitions_agent(doc_id)
    
    all_mentions = get_term_mentions(doc_id)
    assert len(all_mentions) == len(result.mentions)
    
    # Test filtered by block_id
    if result.mentions:
        block_id = result.mentions[0].block_id
        block_mentions = get_term_mentions(doc_id, block_id)
        assert all(m.block_id == block_id for m in block_mentions)
