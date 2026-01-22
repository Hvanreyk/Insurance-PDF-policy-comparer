"""Tests for Segment 3: Clause Classification Agent."""

from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

from ucc.agents.clause_classification import (
    _check_section_keywords,
    _check_text_patterns,
    _classify_block,
    _resolve_conflicts,
    get_all_classifications,
    get_blocks_by_clause_type,
    get_classification,
    run_clause_classification,
)
from ucc.agents.document_layout import doc_id_from_pdf, run_document_layout
from ucc.agents.definitions import run_definitions_agent
from ucc.io.pdf_blocks import Block
from ucc.storage.classification_store import ClauseType


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
# Unit Tests: Section Keyword Detection
# ---------------------------------------------------------------------------


def test_section_keywords_exclusion():
    signals = _check_section_keywords(["General Exclusions"])
    types = {s.clause_type for s in signals}
    assert ClauseType.EXCLUSION in types


def test_section_keywords_condition():
    signals = _check_section_keywords(["Policy Conditions"])
    types = {s.clause_type for s in signals}
    assert ClauseType.CONDITION in types


def test_section_keywords_definition():
    signals = _check_section_keywords(["Definitions"])
    types = {s.clause_type for s in signals}
    assert ClauseType.DEFINITION in types


def test_section_keywords_coverage():
    signals = _check_section_keywords(["What is covered"])
    types = {s.clause_type for s in signals}
    assert ClauseType.COVERAGE_GRANT in types


def test_section_keywords_empty():
    signals = _check_section_keywords([])
    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Unit Tests: Text Pattern Detection
# ---------------------------------------------------------------------------


def test_pattern_exclusion_we_will_not_cover():
    text = "We will not cover any loss arising from flood."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.EXCLUSION in types


def test_pattern_exclusion_not_covered():
    text = "Losses caused by war are not covered under this policy."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.EXCLUSION in types


def test_pattern_exclusion_policy_does_not_cover():
    text = "This policy does not cover intentional acts."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.EXCLUSION in types


def test_pattern_condition_you_must():
    text = "You must notify us within 30 days of any claim."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.CONDITION in types


def test_pattern_condition_it_is_a_condition():
    text = "It is a condition of this policy that you maintain the property."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.CONDITION in types


def test_pattern_warranty():
    text = "You warrant that all information provided is accurate."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.WARRANTY in types


def test_pattern_limit():
    text = "The limit of liability is $1,000,000 any one event."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.LIMIT in types


def test_pattern_sublimit():
    text = "A sub-limit of $50,000 applies to this section."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.SUBLIMIT in types


def test_pattern_extension():
    text = "This policy is extended to include temporary repairs."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.EXTENSION in types


def test_pattern_endorsement():
    text = "This endorsement is attached to and forms part of the policy."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.ENDORSEMENT in types


def test_pattern_coverage_grant():
    text = "We will pay for direct physical loss to your property."
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.COVERAGE_GRANT in types


def test_pattern_definition():
    text = '"Flood" means water entering the building through external openings.'
    signals = _check_text_patterns(text)
    types = {s.clause_type for s in signals}
    assert ClauseType.DEFINITION in types


# ---------------------------------------------------------------------------
# Unit Tests: Block Classification
# ---------------------------------------------------------------------------


def test_classify_admin_block():
    block = _make_block("b1", "Contact us at 1800 123 456.", is_admin=True)
    clf = _classify_block(block, set())
    assert clf.clause_type == ClauseType.ADMIN
    assert clf.confidence == 1.0
    assert clf.signals.get("hard_filter") is True


def test_classify_definition_in_definition_section():
    block = _make_block(
        "b1",
        '"Property" means the buildings and contents at the insured location.',
        section_path=["Definitions"],
    )
    clf = _classify_block(block, set())
    assert clf.clause_type == ClauseType.DEFINITION
    assert clf.confidence >= 0.9


def test_classify_exclusion():
    block = _make_block(
        "b1",
        "We will not cover any loss caused by terrorism.",
        section_path=["Exclusions"],
    )
    clf = _classify_block(block, set())
    assert clf.clause_type == ClauseType.EXCLUSION
    assert clf.confidence >= 0.8


def test_classify_condition():
    block = _make_block(
        "b1",
        "You must take all reasonable precautions to prevent loss.",
        section_path=["Conditions"],
    )
    clf = _classify_block(block, set())
    assert clf.clause_type == ClauseType.CONDITION
    assert clf.confidence >= 0.7


def test_classify_uncertain_fallback():
    block = _make_block(
        "b1",
        "See the attached schedule for details.",
        section_path=["Schedule"],
    )
    clf = _classify_block(block, set())
    # Should either match endorsement or fall back to uncertain
    assert clf.clause_type in [ClauseType.ENDORSEMENT, ClauseType.UNCERTAIN]


# ---------------------------------------------------------------------------
# Unit Tests: Conflict Resolution
# ---------------------------------------------------------------------------


def test_resolve_conflicts_precedence():
    from ucc.agents.clause_classification import _SignalMatch
    
    # Exclusion has higher precedence than Coverage Grant
    signals = [
        _SignalMatch(ClauseType.EXCLUSION, 0.8, "pattern", "excluded"),
        _SignalMatch(ClauseType.COVERAGE_GRANT, 0.85, "pattern", "we will pay"),
    ]
    clause_type, confidence, _ = _resolve_conflicts(signals)
    assert clause_type == ClauseType.EXCLUSION  # Higher precedence wins


def test_resolve_conflicts_confidence_reduction():
    from ucc.agents.clause_classification import _SignalMatch
    
    signals = [
        _SignalMatch(ClauseType.CONDITION, 0.9, "pattern", "you must"),
        _SignalMatch(ClauseType.EXCLUSION, 0.85, "pattern", "excluded"),
    ]
    clause_type, confidence, signals_out = _resolve_conflicts(signals)
    # Confidence should be reduced due to conflict
    assert clause_type == ClauseType.EXCLUSION
    assert confidence < 0.9  # Reduced from original


def test_resolve_conflicts_no_signals():
    clause_type, confidence, signals = _resolve_conflicts([])
    assert clause_type == ClauseType.UNCERTAIN
    assert confidence <= 0.4


# ---------------------------------------------------------------------------
# Unit Tests: Classification Distinctness
# ---------------------------------------------------------------------------


def test_exclusion_vs_condition_distinct():
    """Ensure exclusions and conditions are classified distinctly."""
    exclusion_block = _make_block(
        "b1",
        "We will not cover loss or damage caused by wear and tear.",
    )
    condition_block = _make_block(
        "b2",
        "You must notify us within 14 days of discovering any loss.",
    )
    
    excl_clf = _classify_block(exclusion_block, set())
    cond_clf = _classify_block(condition_block, set())
    
    assert excl_clf.clause_type == ClauseType.EXCLUSION
    assert cond_clf.clause_type == ClauseType.CONDITION
    assert excl_clf.clause_type != cond_clf.clause_type


def test_admin_never_leaks():
    """Admin blocks should always be classified as ADMIN regardless of text."""
    admin_block = _make_block(
        "b1",
        "We will pay for all covered losses.",  # Coverage grant text
        is_admin=True,
    )
    clf = _classify_block(admin_block, set())
    assert clf.clause_type == ClauseType.ADMIN


def test_classification_deterministic():
    """Running classification twice should produce identical results."""
    block = _make_block(
        "b1",
        "We will not cover any loss arising from flood or storm surge.",
        section_path=["Exclusions"],
    )
    
    clf1 = _classify_block(block, set())
    clf2 = _classify_block(block, set())
    
    assert clf1.clause_type == clf2.clause_type
    assert clf1.confidence == clf2.confidence


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


def test_run_clause_classification_with_sample_pdf(tmp_path, monkeypatch, sample_policy_a):
    """Integration test: run full classification on sample PDF."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    # Run Segment 1
    run_document_layout(sample_policy_a, doc_id=doc_id)
    
    # Run Segment 2
    run_definitions_agent(doc_id)
    
    # Run Segment 3
    result = run_clause_classification(doc_id)
    
    assert result.doc_id == doc_id
    assert len(result.classifications) > 0
    assert isinstance(result.stats, dict)
    
    # Check that at least some types were assigned
    total_classified = sum(result.stats.values())
    assert total_classified == len(result.classifications)


def test_classification_persistence_round_trip(tmp_path, monkeypatch, sample_policy_a):
    """Test that classifications are correctly persisted and retrieved."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    run_document_layout(sample_policy_a, doc_id=doc_id)
    run_definitions_agent(doc_id)
    result = run_clause_classification(doc_id)
    
    # Retrieve from persistence
    persisted = get_all_classifications(doc_id)
    
    assert len(persisted) == len(result.classifications)
    
    if result.classifications:
        first = result.classifications[0]
        retrieved = get_classification(doc_id, first.block_id)
        assert retrieved is not None
        assert retrieved.clause_type == first.clause_type
        assert retrieved.confidence == first.confidence


def test_get_blocks_by_clause_type_api(tmp_path, monkeypatch, sample_policy_a):
    """Test the get_blocks_by_clause_type retrieval API."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    run_document_layout(sample_policy_a, doc_id=doc_id)
    run_definitions_agent(doc_id)
    result = run_clause_classification(doc_id)
    
    # Find a clause type that has at least one block
    for clause_type in ClauseType:
        if result.stats.get(clause_type.value, 0) > 0:
            blocks = get_blocks_by_clause_type(doc_id, clause_type)
            assert len(blocks) == result.stats[clause_type.value]
            assert all(b.clause_type == clause_type for b in blocks)
            break


def test_classification_idempotent(tmp_path, monkeypatch, sample_policy_a):
    """Running classification twice should not duplicate data."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    run_document_layout(sample_policy_a, doc_id=doc_id)
    run_definitions_agent(doc_id)
    
    # Run classification twice
    result1 = run_clause_classification(doc_id)
    result2 = run_clause_classification(doc_id)
    
    # Results should be identical
    assert len(result1.classifications) == len(result2.classifications)
    assert result1.stats == result2.stats
    
    # Check individual blocks
    for clf1, clf2 in zip(result1.classifications, result2.classifications):
        assert clf1.block_id == clf2.block_id
        assert clf1.clause_type == clf2.clause_type


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------


def test_empty_text_block():
    block = _make_block("b1", "")
    clf = _classify_block(block, set())
    assert clf.clause_type == ClauseType.UNCERTAIN


def test_ambiguous_text():
    """Text that could match multiple types."""
    block = _make_block(
        "b1",
        "We will pay for flood damage, but we will not cover earthquake.",
    )
    clf = _classify_block(block, set())
    # Should resolve to exclusion due to precedence
    assert clf.clause_type in [ClauseType.EXCLUSION, ClauseType.COVERAGE_GRANT]
    # Confidence should be lower due to ambiguity
    assert clf.confidence < 0.95


def test_section_path_boosts_confidence():
    """Section path should boost pattern confidence."""
    # Same text, different sections
    block_in_excl_section = _make_block(
        "b1",
        "This does not include wear and tear.",
        section_path=["Exclusions"],
    )
    block_no_section = _make_block(
        "b2",
        "This does not include wear and tear.",
        section_path=[],
    )
    
    clf1 = _classify_block(block_in_excl_section, set())
    clf2 = _classify_block(block_no_section, set())
    
    # Section-based classification should have higher confidence
    if clf1.clause_type == clf2.clause_type:
        # If same type, section version should be more confident
        assert clf1.confidence >= clf2.confidence
