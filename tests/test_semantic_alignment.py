"""Tests for Segment 5: Semantic Alignment Agent."""

from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

from ucc.agents.semantic_alignment import (
    CandidatePair,
    ScoredCandidate,
    bipartite_match,
    compute_alignment_score,
    compute_dna_similarity,
    compute_section_similarity,
    compute_semantic_similarity,
    filter_candidates,
    get_alignment,
    get_alignments,
    run_semantic_alignment,
)
from ucc.agents.document_layout import doc_id_from_pdf, run_document_layout
from ucc.agents.definitions import run_definitions_agent
from ucc.agents.clause_classification import run_clause_classification
from ucc.agents.clause_dna import run_clause_dna_agent
from ucc.storage.alignment_store import AlignmentType
from ucc.storage.classification_store import ClauseType
from ucc.storage.dna_store import ClauseDNA, Polarity, Strictness


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_policy_a() -> bytes:
    return Path("tests/fixtures/policy_A.pdf").read_bytes()


@pytest.fixture(scope="module")
def sample_policy_b() -> bytes:
    return Path("tests/fixtures/policy_B.pdf").read_bytes()


def _make_dna(
    doc_id: str = "doc1",
    block_id: str = "b1",
    clause_type: ClauseType = ClauseType.EXCLUSION,
    polarity: Polarity = Polarity.REMOVE,
    strictness: Strictness = Strictness.ABSOLUTE,
    scope_connectors: list[str] | None = None,
    carve_outs: list[str] | None = None,
    entities: list[str] | None = None,
    definition_dependencies: list[str] | None = None,
    temporal_constraints: list[str] | None = None,
    burden_shift: bool = False,
) -> ClauseDNA:
    return ClauseDNA(
        doc_id=doc_id,
        block_id=block_id,
        clause_type=clause_type,
        polarity=polarity,
        strictness=strictness,
        scope_connectors=scope_connectors or [],
        carve_outs=carve_outs or [],
        entities=entities or [],
        numbers={},
        definition_dependencies=definition_dependencies or [],
        temporal_constraints=temporal_constraints or [],
        burden_shift=burden_shift,
        raw_signals={},
        confidence=0.8,
    )


# ---------------------------------------------------------------------------
# Unit Tests: Section Similarity
# ---------------------------------------------------------------------------


def test_section_similarity_identical():
    sim = compute_section_similarity(
        ["Cover", "Exclusions"],
        ["Cover", "Exclusions"],
    )
    assert sim >= 0.9


def test_section_similarity_partial():
    sim = compute_section_similarity(
        ["Cover", "General Exclusions"],
        ["Cover", "Specific Exclusions"],
    )
    assert 0.3 < sim < 0.9


def test_section_similarity_different():
    sim = compute_section_similarity(
        ["Cover", "Exclusions"],
        ["Definitions", "Glossary"],
    )
    assert sim < 0.5


def test_section_similarity_empty():
    sim = compute_section_similarity([], [])
    assert sim == 1.0
    
    sim = compute_section_similarity(["Cover"], [])
    assert sim == 0.3


def test_section_similarity_depth_weighting():
    # Deeper shared paths should score higher
    shallow = compute_section_similarity(
        ["Cover"],
        ["Cover"],
    )
    deep = compute_section_similarity(
        ["Cover", "Exclusions", "General"],
        ["Cover", "Exclusions", "General"],
    )
    assert deep >= shallow


# ---------------------------------------------------------------------------
# Unit Tests: DNA Similarity
# ---------------------------------------------------------------------------


def test_dna_similarity_identical():
    dna_a = _make_dna(
        polarity=Polarity.REMOVE,
        strictness=Strictness.ABSOLUTE,
        scope_connectors=["arising from"],
        entities=["peril:flood"],
    )
    dna_b = _make_dna(
        polarity=Polarity.REMOVE,
        strictness=Strictness.ABSOLUTE,
        scope_connectors=["arising from"],
        entities=["peril:flood"],
    )
    
    sim, components = compute_dna_similarity(dna_a, dna_b)
    assert sim >= 0.9
    assert components["polarity"] == 1.0
    assert components["strictness"] == 1.0


def test_dna_similarity_different_polarity():
    dna_a = _make_dna(polarity=Polarity.REMOVE)
    dna_b = _make_dna(polarity=Polarity.GRANT)
    
    sim, components = compute_dna_similarity(dna_a, dna_b)
    assert components["polarity"] == 0.0
    assert sim < 0.9  # Should be lower due to polarity mismatch


def test_dna_similarity_different_strictness():
    dna_a = _make_dna(strictness=Strictness.ABSOLUTE)
    dna_b = _make_dna(strictness=Strictness.CONDITIONAL)
    
    sim, components = compute_dna_similarity(dna_a, dna_b)
    assert components["strictness"] == 0.0


def test_dna_similarity_partial_strictness():
    # Conditional and discretionary should get partial credit
    dna_a = _make_dna(strictness=Strictness.CONDITIONAL)
    dna_b = _make_dna(strictness=Strictness.DISCRETIONARY)
    
    sim, components = compute_dna_similarity(dna_a, dna_b)
    assert components["strictness"] == 0.5


def test_dna_similarity_scope_connectors():
    dna_a = _make_dna(scope_connectors=["arising from", "in connection with"])
    dna_b = _make_dna(scope_connectors=["arising from"])
    
    sim, components = compute_dna_similarity(dna_a, dna_b)
    # Jaccard of {arising, in} and {arising} = 1/2
    assert 0.4 < components["scope_connectors"] < 0.7


def test_dna_similarity_entities():
    dna_a = _make_dna(entities=["peril:flood", "peril:fire", "peril:storm"])
    dna_b = _make_dna(entities=["peril:flood", "peril:fire"])
    
    sim, components = compute_dna_similarity(dna_a, dna_b)
    # Jaccard similarity
    assert components["entities"] > 0.5


# ---------------------------------------------------------------------------
# Unit Tests: Semantic Similarity
# ---------------------------------------------------------------------------


def test_semantic_similarity_identical():
    texts_a = ["We will not cover any loss arising from flood damage."]
    texts_b = ["We will not cover any loss arising from flood damage."]
    
    sim_matrix = compute_semantic_similarity(texts_a, texts_b)
    assert sim_matrix[0, 0] >= 0.99


def test_semantic_similarity_similar():
    texts_a = ["We will not cover flood damage to property."]
    texts_b = ["Flood damage to your property is excluded."]
    
    sim_matrix = compute_semantic_similarity(texts_a, texts_b)
    assert sim_matrix[0, 0] > 0.3  # Should have some similarity


def test_semantic_similarity_different():
    texts_a = ["We will pay for fire damage."]
    texts_b = ["Your duty to notify us of claims."]
    
    sim_matrix = compute_semantic_similarity(texts_a, texts_b)
    assert sim_matrix[0, 0] < 0.5  # Should be quite different


def test_semantic_similarity_empty():
    sim_matrix = compute_semantic_similarity([], ["text"])
    assert sim_matrix.shape == (0, 1)


# ---------------------------------------------------------------------------
# Unit Tests: Alignment Score
# ---------------------------------------------------------------------------


def test_alignment_score_high():
    dna_a = _make_dna(burden_shift=False)
    dna_b = _make_dna(burden_shift=False)
    
    score, confidence, penalties = compute_alignment_score(
        section_similarity=0.9,
        dna_similarity=0.9,
        semantic_similarity=0.8,
        dna_a=dna_a,
        dna_b=dna_b,
    )
    
    # 0.45*0.9 + 0.30*0.8 + 0.25*0.9 = 0.405 + 0.24 + 0.225 = 0.87
    assert 0.8 < score < 0.95
    assert len(penalties) == 0


def test_alignment_score_carve_out_penalty():
    dna_a = _make_dna(carve_outs=["except: sudden events"])
    dna_b = _make_dna(carve_outs=["unless: pre-approved"])
    
    score, confidence, penalties = compute_alignment_score(
        section_similarity=0.9,
        dna_similarity=0.8,
        semantic_similarity=0.8,
        dna_a=dna_a,
        dna_b=dna_b,
    )
    
    assert "carve_out_diff" in penalties[0]


def test_alignment_score_burden_shift_penalty():
    dna_a = _make_dna(burden_shift=True)
    dna_b = _make_dna(burden_shift=False)
    
    score, confidence, penalties = compute_alignment_score(
        section_similarity=0.9,
        dna_similarity=0.8,
        semantic_similarity=0.8,
        dna_a=dna_a,
        dna_b=dna_b,
    )
    
    assert any("burden_shift" in p for p in penalties)


# ---------------------------------------------------------------------------
# Unit Tests: Candidate Filtering
# ---------------------------------------------------------------------------


def test_filter_candidates_same_type():
    blocks_a = [{"id": "a1", "text": "Flood exclusion text here."}]
    blocks_b = [{"id": "b1", "text": "Flood is excluded from cover."}]
    classifications_a = {"a1": "EXCLUSION"}
    classifications_b = {"b1": "EXCLUSION"}
    
    candidates = filter_candidates(blocks_a, blocks_b, classifications_a, classifications_b)
    assert len(candidates) == 1


def test_filter_candidates_different_type():
    blocks_a = [{"id": "a1", "text": "Flood exclusion text here."}]
    blocks_b = [{"id": "b1", "text": "You must notify us within 30 days."}]
    classifications_a = {"a1": "EXCLUSION"}
    classifications_b = {"b1": "CONDITION"}
    
    candidates = filter_candidates(blocks_a, blocks_b, classifications_a, classifications_b)
    assert len(candidates) == 0  # Different types should not match


def test_filter_candidates_admin_excluded():
    blocks_a = [{"id": "a1", "text": "Contact us at 1800 123 456."}]
    blocks_b = [{"id": "b1", "text": "Call us anytime for assistance."}]
    classifications_a = {"a1": "ADMIN"}
    classifications_b = {"b1": "ADMIN"}
    
    candidates = filter_candidates(blocks_a, blocks_b, classifications_a, classifications_b)
    assert len(candidates) == 0  # ADMIN blocks should be excluded


def test_filter_candidates_length_ratio():
    # Very short vs very long should be filtered out
    blocks_a = [{"id": "a1", "text": "Short."}]
    blocks_b = [{"id": "b1", "text": "This is a much longer text " * 20}]
    classifications_a = {"a1": "EXCLUSION"}
    classifications_b = {"b1": "EXCLUSION"}
    
    candidates = filter_candidates(blocks_a, blocks_b, classifications_a, classifications_b)
    assert len(candidates) == 0  # Length ratio outside [0.5, 2.0]


# ---------------------------------------------------------------------------
# Unit Tests: Bipartite Matching
# ---------------------------------------------------------------------------


def test_bipartite_match_basic():
    dna = _make_dna()
    pair = CandidatePair(
        block_id_a="a1",
        block_id_b="b1",
        clause_type="EXCLUSION",
        text_a="text",
        text_b="text",
        expanded_text_a="text",
        expanded_text_b="text",
        dna_a=dna,
        dna_b=dna,
        section_path_a=[],
        section_path_b=[],
    )
    
    scored = ScoredCandidate(
        pair=pair,
        section_similarity=0.9,
        dna_similarity=0.9,
        semantic_similarity=0.8,
        alignment_score=0.85,
        confidence=0.8,
        penalties=[],
    )
    
    matched = bipartite_match([scored])
    assert len(matched) == 1


def test_bipartite_match_below_threshold():
    dna = _make_dna()
    pair = CandidatePair(
        block_id_a="a1",
        block_id_b="b1",
        clause_type="EXCLUSION",
        text_a="text",
        text_b="text",
        expanded_text_a="text",
        expanded_text_b="text",
        dna_a=dna,
        dna_b=dna,
        section_path_a=[],
        section_path_b=[],
    )
    
    scored = ScoredCandidate(
        pair=pair,
        section_similarity=0.3,
        dna_similarity=0.3,
        semantic_similarity=0.3,
        alignment_score=0.3,  # Below threshold
        confidence=0.3,
        penalties=[],
    )
    
    matched = bipartite_match([scored], threshold=0.6)
    assert len(matched) == 0


def test_bipartite_match_greedy_best_first():
    dna = _make_dna()
    
    # Two candidates for same block_a
    pair1 = CandidatePair(
        block_id_a="a1",
        block_id_b="b1",
        clause_type="EXCLUSION",
        text_a="text",
        text_b="text",
        expanded_text_a="text",
        expanded_text_b="text",
        dna_a=dna,
        dna_b=dna,
        section_path_a=[],
        section_path_b=[],
    )
    pair2 = CandidatePair(
        block_id_a="a1",
        block_id_b="b2",
        clause_type="EXCLUSION",
        text_a="text",
        text_b="text",
        expanded_text_a="text",
        expanded_text_b="text",
        dna_a=dna,
        dna_b=dna,
        section_path_a=[],
        section_path_b=[],
    )
    
    scored1 = ScoredCandidate(
        pair=pair1,
        section_similarity=0.9,
        dna_similarity=0.9,
        semantic_similarity=0.8,
        alignment_score=0.85,
        confidence=0.8,
        penalties=[],
    )
    scored2 = ScoredCandidate(
        pair=pair2,
        section_similarity=0.7,
        dna_similarity=0.7,
        semantic_similarity=0.6,
        alignment_score=0.70,  # Lower score
        confidence=0.7,
        penalties=[],
    )
    
    matched = bipartite_match([scored1, scored2])
    
    # Should only match the better one
    assert len(matched) == 1
    assert matched[0].pair.block_id_b == "b1"


# ---------------------------------------------------------------------------
# Unit Tests: Clause Type Matching
# ---------------------------------------------------------------------------


def test_exclusion_should_not_match_condition():
    """Ensure exclusions and conditions are never aligned."""
    blocks_a = [{"id": "a1", "text": "We will not cover flood damage."}]
    blocks_b = [{"id": "b1", "text": "You must notify us within 30 days."}]
    
    classifications_a = {"a1": ClauseType.EXCLUSION.value}
    classifications_b = {"b1": ClauseType.CONDITION.value}
    
    candidates = filter_candidates(blocks_a, blocks_b, classifications_a, classifications_b)
    assert len(candidates) == 0


def test_identical_exclusions_should_align():
    """Identical exclusions should produce high alignment score."""
    dna_a = _make_dna(
        clause_type=ClauseType.EXCLUSION,
        polarity=Polarity.REMOVE,
        strictness=Strictness.ABSOLUTE,
        scope_connectors=["arising from"],
        entities=["peril:flood"],
    )
    dna_b = _make_dna(
        clause_type=ClauseType.EXCLUSION,
        polarity=Polarity.REMOVE,
        strictness=Strictness.ABSOLUTE,
        scope_connectors=["arising from"],
        entities=["peril:flood"],
    )
    
    dna_sim, _ = compute_dna_similarity(dna_a, dna_b)
    assert dna_sim >= 0.9


# ---------------------------------------------------------------------------
# Unit Tests: DNA vs Lexical Preference
# ---------------------------------------------------------------------------


def test_prefer_dna_over_lexical():
    """DNA-consistent clauses should be preferred over lexically similar but legally different ones."""
    
    # Two exclusions with different DNA
    dna_a = _make_dna(
        polarity=Polarity.REMOVE,
        strictness=Strictness.ABSOLUTE,
        entities=["peril:flood"],
    )
    
    # Similar DNA
    dna_b_similar = _make_dna(
        polarity=Polarity.REMOVE,
        strictness=Strictness.ABSOLUTE,
        entities=["peril:flood"],
    )
    
    # Different DNA (different entities)
    dna_b_different = _make_dna(
        polarity=Polarity.REMOVE,
        strictness=Strictness.ABSOLUTE,
        entities=["peril:cyber", "peril:terrorism"],
    )
    
    sim_similar, _ = compute_dna_similarity(dna_a, dna_b_similar)
    sim_different, _ = compute_dna_similarity(dna_a, dna_b_different)
    
    # DNA-consistent should have higher similarity
    assert sim_similar > sim_different


# ---------------------------------------------------------------------------
# Unit Tests: Stability / Determinism
# ---------------------------------------------------------------------------


def test_alignment_deterministic():
    """Same inputs should produce same outputs."""
    dna_a = _make_dna(entities=["peril:flood"])
    dna_b = _make_dna(entities=["peril:flood"])
    
    sim1, comp1 = compute_dna_similarity(dna_a, dna_b)
    sim2, comp2 = compute_dna_similarity(dna_a, dna_b)
    
    assert sim1 == sim2
    assert comp1 == comp2


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


def test_run_semantic_alignment_with_sample_pdfs(tmp_path, monkeypatch, sample_policy_a, sample_policy_b):
    """Integration test: run full alignment on sample PDFs."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id_a = doc_id_from_pdf(sample_policy_a)
    doc_id_b = doc_id_from_pdf(sample_policy_b)
    
    # Run Segments 1-4 for both documents
    run_document_layout(sample_policy_a, doc_id=doc_id_a)
    run_definitions_agent(doc_id_a)
    run_clause_classification(doc_id_a)
    run_clause_dna_agent(doc_id_a)
    
    run_document_layout(sample_policy_b, doc_id=doc_id_b)
    run_definitions_agent(doc_id_b)
    run_clause_classification(doc_id_b)
    run_clause_dna_agent(doc_id_b)
    
    # Run Segment 5
    result = run_semantic_alignment(doc_id_a, doc_id_b)
    
    assert result.doc_id_a == doc_id_a
    assert result.doc_id_b == doc_id_b
    assert isinstance(result.alignments, list)
    assert isinstance(result.stats, dict)
    assert "total" in result.stats


def test_alignment_persistence_round_trip(tmp_path, monkeypatch, sample_policy_a, sample_policy_b):
    """Test that alignments are correctly persisted and retrieved."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id_a = doc_id_from_pdf(sample_policy_a)
    doc_id_b = doc_id_from_pdf(sample_policy_b)
    
    # Run all segments for both docs
    for doc_id, pdf_bytes in [(doc_id_a, sample_policy_a), (doc_id_b, sample_policy_b)]:
        run_document_layout(pdf_bytes, doc_id=doc_id)
        run_definitions_agent(doc_id)
        run_clause_classification(doc_id)
        run_clause_dna_agent(doc_id)
    
    result = run_semantic_alignment(doc_id_a, doc_id_b)
    
    # Retrieve from persistence
    persisted = get_alignments(doc_id_a, doc_id_b)
    
    assert len(persisted) == len(result.alignments)


def test_alignment_idempotent(tmp_path, monkeypatch, sample_policy_a, sample_policy_b):
    """Running alignment twice should not duplicate data."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id_a = doc_id_from_pdf(sample_policy_a)
    doc_id_b = doc_id_from_pdf(sample_policy_b)
    
    # Run all segments
    for doc_id, pdf_bytes in [(doc_id_a, sample_policy_a), (doc_id_b, sample_policy_b)]:
        run_document_layout(pdf_bytes, doc_id=doc_id)
        run_definitions_agent(doc_id)
        run_clause_classification(doc_id)
        run_clause_dna_agent(doc_id)
    
    # Run alignment twice
    result1 = run_semantic_alignment(doc_id_a, doc_id_b)
    result2 = run_semantic_alignment(doc_id_a, doc_id_b)
    
    assert len(result1.alignments) == len(result2.alignments)
    assert result1.stats == result2.stats


def test_alignment_has_score_components(tmp_path, monkeypatch, sample_policy_a, sample_policy_b):
    """Verify that alignments include score components for explainability."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id_a = doc_id_from_pdf(sample_policy_a)
    doc_id_b = doc_id_from_pdf(sample_policy_b)
    
    for doc_id, pdf_bytes in [(doc_id_a, sample_policy_a), (doc_id_b, sample_policy_b)]:
        run_document_layout(pdf_bytes, doc_id=doc_id)
        run_definitions_agent(doc_id)
        run_clause_classification(doc_id)
        run_clause_dna_agent(doc_id)
    
    result = run_semantic_alignment(doc_id_a, doc_id_b)
    
    # Check matched alignments have score components
    matched = [a for a in result.alignments if a.alignment_type != AlignmentType.UNMATCHED]
    
    for alignment in matched:
        assert isinstance(alignment.score_components, dict)
        assert "section_similarity" in alignment.score_components
        assert "dna_similarity" in alignment.score_components
        assert "semantic_similarity" in alignment.score_components


def test_get_alignment_api(tmp_path, monkeypatch, sample_policy_a, sample_policy_b):
    """Test the get_alignment API for retrieving by block_id."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id_a = doc_id_from_pdf(sample_policy_a)
    doc_id_b = doc_id_from_pdf(sample_policy_b)
    
    for doc_id, pdf_bytes in [(doc_id_a, sample_policy_a), (doc_id_b, sample_policy_b)]:
        run_document_layout(pdf_bytes, doc_id=doc_id)
        run_definitions_agent(doc_id)
        run_clause_classification(doc_id)
        run_clause_dna_agent(doc_id)
    
    result = run_semantic_alignment(doc_id_a, doc_id_b)
    
    if result.alignments:
        block_id = result.alignments[0].block_id_a
        retrieved = get_alignment(block_id)
        assert len(retrieved) >= 1
        assert all(a.block_id_a == block_id for a in retrieved)
