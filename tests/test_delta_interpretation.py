"""Tests for Segment 6: Delta Interpretation Agent."""

from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

from ucc.agents.delta_interpretation import (
    detect_burden_shift_change,
    detect_carve_out_change,
    detect_definition_dependency_change,
    detect_numeric_change,
    detect_scope_change,
    detect_strictness_change,
    detect_temporal_change,
    get_deltas,
    get_deltas_for_clause,
    run_delta_interpretation,
)
from ucc.agents.document_layout import doc_id_from_pdf, run_document_layout
from ucc.agents.definitions import run_definitions_agent
from ucc.agents.clause_classification import run_clause_classification
from ucc.agents.clause_dna import run_clause_dna_agent
from ucc.agents.semantic_alignment import run_semantic_alignment
from ucc.storage.classification_store import ClauseType
from ucc.storage.delta_store import DeltaDirection, DeltaType
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
    numbers: dict | None = None,
    definition_dependencies: list[str] | None = None,
    temporal_constraints: list[str] | None = None,
    burden_shift: bool = False,
    confidence: float = 0.8,
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
        numbers=numbers or {},
        definition_dependencies=definition_dependencies or [],
        temporal_constraints=temporal_constraints or [],
        burden_shift=burden_shift,
        raw_signals={},
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Unit Tests: Scope Change Detection
# ---------------------------------------------------------------------------


def test_scope_change_broader_connectors():
    """Adding broadening connectors should be detected as broader."""
    dna_a = _make_dna(scope_connectors=["arising from"])
    dna_b = _make_dna(scope_connectors=["arising from", "in connection with"])
    
    direction, details, evidence = detect_scope_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.BROADER
    assert "added_connectors" in details
    assert "in connection with" in details["added_connectors"]


def test_scope_change_narrower_connectors():
    """Removing broadening connectors should be detected as narrower."""
    dna_a = _make_dna(scope_connectors=["arising from", "in connection with"])
    dna_b = _make_dna(scope_connectors=["arising from"])
    
    direction, details, evidence = detect_scope_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.NARROWER
    assert "removed_connectors" in details


def test_scope_change_broader_entities():
    """Adding entities should generally be broader."""
    dna_a = _make_dna(entities=["peril:flood"])
    dna_b = _make_dna(entities=["peril:flood", "peril:fire", "peril:storm"])
    
    direction, details, evidence = detect_scope_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.BROADER
    assert "added_entities" in details


def test_scope_change_narrower_entities():
    """Removing entities should generally be narrower."""
    dna_a = _make_dna(entities=["peril:flood", "peril:fire", "peril:storm"])
    dna_b = _make_dna(entities=["peril:flood"])
    
    direction, details, evidence = detect_scope_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.NARROWER
    assert "removed_entities" in details


def test_scope_change_no_change():
    """Identical scopes should return None."""
    dna_a = _make_dna(scope_connectors=["arising from"], entities=["peril:flood"])
    dna_b = _make_dna(scope_connectors=["arising from"], entities=["peril:flood"])
    
    direction, details, evidence = detect_scope_change(dna_a, dna_b)
    
    assert direction is None


# ---------------------------------------------------------------------------
# Unit Tests: Strictness Change Detection
# ---------------------------------------------------------------------------


def test_strictness_change_exclusion_weakened():
    """Exclusion: absolute → conditional should be broader coverage."""
    dna_a = _make_dna(
        polarity=Polarity.REMOVE,
        strictness=Strictness.ABSOLUTE,
    )
    dna_b = _make_dna(
        polarity=Polarity.REMOVE,
        strictness=Strictness.CONDITIONAL,
    )
    
    direction, details, evidence = detect_strictness_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.BROADER  # Exclusion weakened = more coverage


def test_strictness_change_exclusion_strengthened():
    """Exclusion: conditional → absolute should be narrower coverage."""
    dna_a = _make_dna(
        polarity=Polarity.REMOVE,
        strictness=Strictness.CONDITIONAL,
    )
    dna_b = _make_dna(
        polarity=Polarity.REMOVE,
        strictness=Strictness.ABSOLUTE,
    )
    
    direction, details, evidence = detect_strictness_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.NARROWER  # Exclusion strengthened = less coverage


def test_strictness_change_coverage_strengthened():
    """Coverage: conditional → absolute should be broader."""
    dna_a = _make_dna(
        polarity=Polarity.GRANT,
        strictness=Strictness.CONDITIONAL,
    )
    dna_b = _make_dna(
        polarity=Polarity.GRANT,
        strictness=Strictness.ABSOLUTE,
    )
    
    direction, details, evidence = detect_strictness_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.BROADER


def test_strictness_change_discretionary_ambiguous():
    """Involving discretionary should be ambiguous."""
    dna_a = _make_dna(strictness=Strictness.ABSOLUTE)
    dna_b = _make_dna(strictness=Strictness.DISCRETIONARY)
    
    direction, details, evidence = detect_strictness_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.AMBIGUOUS


def test_strictness_change_no_change():
    """Same strictness should return None."""
    dna_a = _make_dna(strictness=Strictness.ABSOLUTE)
    dna_b = _make_dna(strictness=Strictness.ABSOLUTE)
    
    direction, details, evidence = detect_strictness_change(dna_a, dna_b)
    
    assert direction is None


# ---------------------------------------------------------------------------
# Unit Tests: Carve-out Change Detection
# ---------------------------------------------------------------------------


def test_carve_out_added_exclusion():
    """Adding carve-out to exclusion = broader coverage (exception to exclusion)."""
    dna_a = _make_dna(
        polarity=Polarity.REMOVE,
        carve_outs=[],
    )
    dna_b = _make_dna(
        polarity=Polarity.REMOVE,
        carve_outs=["except: sudden and accidental events"],
    )
    
    direction, details, evidence = detect_carve_out_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.BROADER
    assert "added_carve_outs" in details


def test_carve_out_removed_exclusion():
    """Removing carve-out from exclusion = narrower coverage."""
    dna_a = _make_dna(
        polarity=Polarity.REMOVE,
        carve_outs=["except: sudden and accidental events"],
    )
    dna_b = _make_dna(
        polarity=Polarity.REMOVE,
        carve_outs=[],
    )
    
    direction, details, evidence = detect_carve_out_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.NARROWER
    assert "removed_carve_outs" in details


def test_carve_out_added_coverage():
    """Adding carve-out to coverage = narrower coverage."""
    dna_a = _make_dna(
        polarity=Polarity.GRANT,
        carve_outs=[],
    )
    dna_b = _make_dna(
        polarity=Polarity.GRANT,
        carve_outs=["unless: pre-existing conditions"],
    )
    
    direction, details, evidence = detect_carve_out_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.NARROWER


def test_carve_out_removed_coverage():
    """Removing carve-out from coverage = broader coverage."""
    dna_a = _make_dna(
        polarity=Polarity.GRANT,
        carve_outs=["unless: pre-existing conditions"],
    )
    dna_b = _make_dna(
        polarity=Polarity.GRANT,
        carve_outs=[],
    )
    
    direction, details, evidence = detect_carve_out_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.BROADER


def test_carve_out_mixed_ambiguous():
    """Both added and removed carve-outs = ambiguous."""
    dna_a = _make_dna(
        polarity=Polarity.REMOVE,
        carve_outs=["except: sudden events"],
    )
    dna_b = _make_dna(
        polarity=Polarity.REMOVE,
        carve_outs=["unless: pre-approved"],
    )
    
    direction, details, evidence = detect_carve_out_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.AMBIGUOUS


# ---------------------------------------------------------------------------
# Unit Tests: Burden Shift Change Detection
# ---------------------------------------------------------------------------


def test_burden_shift_added():
    """Adding burden shift = narrower (more obligations on insured)."""
    dna_a = _make_dna(burden_shift=False)
    dna_b = _make_dna(burden_shift=True)
    
    direction, details, evidence = detect_burden_shift_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.NARROWER
    assert details["from_burden_shift"] is False
    assert details["to_burden_shift"] is True


def test_burden_shift_removed():
    """Removing burden shift = broader (fewer obligations)."""
    dna_a = _make_dna(burden_shift=True)
    dna_b = _make_dna(burden_shift=False)
    
    direction, details, evidence = detect_burden_shift_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.BROADER


def test_burden_shift_no_change():
    """Same burden shift should return None."""
    dna_a = _make_dna(burden_shift=True)
    dna_b = _make_dna(burden_shift=True)
    
    direction, details, evidence = detect_burden_shift_change(dna_a, dna_b)
    
    assert direction is None


# ---------------------------------------------------------------------------
# Unit Tests: Numeric Change Detection
# ---------------------------------------------------------------------------


def test_numeric_change_limit_increased():
    """Higher limit = broader."""
    dna_a = _make_dna(numbers={"limits": [500000.0]})
    dna_b = _make_dna(numbers={"limits": [1000000.0]})
    
    direction, details, evidence = detect_numeric_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.BROADER
    assert "limits_increased" in details


def test_numeric_change_limit_decreased():
    """Lower limit = narrower."""
    dna_a = _make_dna(numbers={"limits": [1000000.0]})
    dna_b = _make_dna(numbers={"limits": [500000.0]})
    
    direction, details, evidence = detect_numeric_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.NARROWER
    assert "limits_decreased" in details


def test_numeric_change_deductible_increased():
    """Higher deductible = narrower."""
    dna_a = _make_dna(numbers={"deductibles": [5000.0]})
    dna_b = _make_dna(numbers={"deductibles": [10000.0]})
    
    direction, details, evidence = detect_numeric_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.NARROWER
    assert "deductibles_increased" in details


def test_numeric_change_deductible_decreased():
    """Lower deductible = broader."""
    dna_a = _make_dna(numbers={"deductibles": [10000.0]})
    dna_b = _make_dna(numbers={"deductibles": [5000.0]})
    
    direction, details, evidence = detect_numeric_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.BROADER
    assert "deductibles_decreased" in details


def test_numeric_change_waiting_period_increased():
    """Longer waiting period = narrower."""
    dna_a = _make_dna(numbers={"waiting_period_hours": [24]})
    dna_b = _make_dna(numbers={"waiting_period_hours": [72]})
    
    direction, details, evidence = detect_numeric_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.NARROWER


def test_numeric_change_no_change():
    """Same numbers should return None."""
    dna_a = _make_dna(numbers={"limits": [1000000.0]})
    dna_b = _make_dna(numbers={"limits": [1000000.0]})
    
    direction, details, evidence = detect_numeric_change(dna_a, dna_b)
    
    assert direction is None


# ---------------------------------------------------------------------------
# Unit Tests: Definition Dependency Change Detection
# ---------------------------------------------------------------------------


def test_definition_dependency_added():
    """New dependency = ambiguous (we don't know what it means)."""
    dna_a = _make_dna(definition_dependencies=["FLOOD"])
    dna_b = _make_dna(definition_dependencies=["FLOOD", "STORM"])
    
    direction, details, evidence = detect_definition_dependency_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.AMBIGUOUS
    assert "added_dependencies" in details
    assert "STORM" in details["added_dependencies"]


def test_definition_dependency_removed():
    """Removed dependency = ambiguous."""
    dna_a = _make_dna(definition_dependencies=["FLOOD", "STORM"])
    dna_b = _make_dna(definition_dependencies=["FLOOD"])
    
    direction, details, evidence = detect_definition_dependency_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.AMBIGUOUS
    assert "removed_dependencies" in details


def test_definition_dependency_no_change():
    """Same dependencies should return None."""
    dna_a = _make_dna(definition_dependencies=["FLOOD"])
    dna_b = _make_dna(definition_dependencies=["FLOOD"])
    
    direction, details, evidence = detect_definition_dependency_change(dna_a, dna_b)
    
    assert direction is None


# ---------------------------------------------------------------------------
# Unit Tests: Temporal Change Detection
# ---------------------------------------------------------------------------


def test_temporal_constraint_added():
    """Additional timing constraint = narrower."""
    dna_a = _make_dna(temporal_constraints=["during the period of insurance"])
    dna_b = _make_dna(temporal_constraints=[
        "during the period of insurance",
        "within 30 days",
    ])
    
    direction, details, evidence = detect_temporal_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.NARROWER
    assert "added_constraints" in details


def test_temporal_constraint_removed():
    """Constraint removed = broader."""
    dna_a = _make_dna(temporal_constraints=[
        "during the period of insurance",
        "within 30 days",
    ])
    dna_b = _make_dna(temporal_constraints=["during the period of insurance"])
    
    direction, details, evidence = detect_temporal_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.BROADER
    assert "removed_constraints" in details


def test_temporal_constraint_mixed():
    """Both added and removed = ambiguous."""
    dna_a = _make_dna(temporal_constraints=["within 30 days"])
    dna_b = _make_dna(temporal_constraints=["within 14 days"])
    
    direction, details, evidence = detect_temporal_change(dna_a, dna_b)
    
    assert direction == DeltaDirection.AMBIGUOUS


def test_temporal_constraint_no_change():
    """Same constraints should return None."""
    dna_a = _make_dna(temporal_constraints=["during the period of insurance"])
    dna_b = _make_dna(temporal_constraints=["during the period of insurance"])
    
    direction, details, evidence = detect_temporal_change(dna_a, dna_b)
    
    assert direction is None


# ---------------------------------------------------------------------------
# Unit Tests: Ambiguous Cases
# ---------------------------------------------------------------------------


def test_ambiguous_flagged_not_forced():
    """Ambiguous cases should be flagged as ambiguous, not forced to a direction."""
    # Mixed carve-out changes
    dna_a = _make_dna(carve_outs=["except: A", "except: B"])
    dna_b = _make_dna(carve_outs=["except: C", "except: D"])
    
    direction, _, _ = detect_carve_out_change(dna_a, dna_b)
    assert direction == DeltaDirection.AMBIGUOUS
    
    # Discretionary strictness
    dna_a = _make_dna(strictness=Strictness.CONDITIONAL)
    dna_b = _make_dna(strictness=Strictness.DISCRETIONARY)
    
    direction, _, _ = detect_strictness_change(dna_a, dna_b)
    assert direction == DeltaDirection.AMBIGUOUS


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


def test_run_delta_interpretation_with_sample_pdfs(tmp_path, monkeypatch, sample_policy_a, sample_policy_b):
    """Integration test: run full delta interpretation on sample PDFs."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id_a = doc_id_from_pdf(sample_policy_a)
    doc_id_b = doc_id_from_pdf(sample_policy_b)
    
    # Run Segments 1-5 for both documents
    run_document_layout(sample_policy_a, doc_id=doc_id_a)
    run_definitions_agent(doc_id_a)
    run_clause_classification(doc_id_a)
    run_clause_dna_agent(doc_id_a)
    
    run_document_layout(sample_policy_b, doc_id=doc_id_b)
    run_definitions_agent(doc_id_b)
    run_clause_classification(doc_id_b)
    run_clause_dna_agent(doc_id_b)
    
    run_semantic_alignment(doc_id_a, doc_id_b)
    
    # Run Segment 6
    result = run_delta_interpretation(doc_id_a, doc_id_b)
    
    assert result.doc_id_a == doc_id_a
    assert result.doc_id_b == doc_id_b
    assert isinstance(result.deltas, list)
    assert isinstance(result.stats, dict)


def test_delta_persistence_round_trip(tmp_path, monkeypatch, sample_policy_a, sample_policy_b):
    """Test that deltas are correctly persisted and retrieved."""
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
    
    run_semantic_alignment(doc_id_a, doc_id_b)
    result = run_delta_interpretation(doc_id_a, doc_id_b)
    
    # Retrieve from persistence
    persisted = get_deltas(doc_id_a, doc_id_b)
    
    assert len(persisted) == len(result.deltas)


def test_delta_idempotent(tmp_path, monkeypatch, sample_policy_a, sample_policy_b):
    """Running delta interpretation twice should not duplicate data."""
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
    
    run_semantic_alignment(doc_id_a, doc_id_b)
    
    # Run delta interpretation twice
    result1 = run_delta_interpretation(doc_id_a, doc_id_b)
    result2 = run_delta_interpretation(doc_id_a, doc_id_b)
    
    assert len(result1.deltas) == len(result2.deltas)


def test_delta_has_evidence(tmp_path, monkeypatch, sample_policy_a, sample_policy_b):
    """Verify that deltas include evidence for explainability."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id_a = doc_id_from_pdf(sample_policy_a)
    doc_id_b = doc_id_from_pdf(sample_policy_b)
    
    for doc_id, pdf_bytes in [(doc_id_a, sample_policy_a), (doc_id_b, sample_policy_b)]:
        run_document_layout(pdf_bytes, doc_id=doc_id)
        run_definitions_agent(doc_id)
        run_clause_classification(doc_id)
        run_clause_dna_agent(doc_id)
    
    run_semantic_alignment(doc_id_a, doc_id_b)
    result = run_delta_interpretation(doc_id_a, doc_id_b)
    
    for delta in result.deltas:
        assert isinstance(delta.evidence, dict)
        assert isinstance(delta.details, dict)


def test_get_deltas_for_clause_api(tmp_path, monkeypatch, sample_policy_a, sample_policy_b):
    """Test the get_deltas_for_clause API."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id_a = doc_id_from_pdf(sample_policy_a)
    doc_id_b = doc_id_from_pdf(sample_policy_b)
    
    for doc_id, pdf_bytes in [(doc_id_a, sample_policy_a), (doc_id_b, sample_policy_b)]:
        run_document_layout(pdf_bytes, doc_id=doc_id)
        run_definitions_agent(doc_id)
        run_clause_classification(doc_id)
        run_clause_dna_agent(doc_id)
    
    run_semantic_alignment(doc_id_a, doc_id_b)
    result = run_delta_interpretation(doc_id_a, doc_id_b)
    
    if result.deltas:
        block_id = result.deltas[0].block_id_a
        clause_deltas = get_deltas_for_clause(block_id)
        assert all(d.block_id_a == block_id for d in clause_deltas)


# ---------------------------------------------------------------------------
# Delta Type Coverage Tests
# ---------------------------------------------------------------------------


def test_all_delta_types_detected():
    """Ensure all delta types can be detected."""
    # Create DNA pairs that trigger each delta type
    
    # Scope change
    dna_a = _make_dna(scope_connectors=["arising from"])
    dna_b = _make_dna(scope_connectors=["arising from", "in connection with"])
    direction, _, _ = detect_scope_change(dna_a, dna_b)
    assert direction is not None
    
    # Strictness change
    dna_a = _make_dna(strictness=Strictness.ABSOLUTE)
    dna_b = _make_dna(strictness=Strictness.CONDITIONAL)
    direction, _, _ = detect_strictness_change(dna_a, dna_b)
    assert direction is not None
    
    # Carve-out change
    dna_a = _make_dna(carve_outs=[])
    dna_b = _make_dna(carve_outs=["except: X"])
    direction, _, _ = detect_carve_out_change(dna_a, dna_b)
    assert direction is not None
    
    # Burden shift change
    dna_a = _make_dna(burden_shift=False)
    dna_b = _make_dna(burden_shift=True)
    direction, _, _ = detect_burden_shift_change(dna_a, dna_b)
    assert direction is not None
    
    # Numeric change
    dna_a = _make_dna(numbers={"limits": [500000]})
    dna_b = _make_dna(numbers={"limits": [1000000]})
    direction, _, _ = detect_numeric_change(dna_a, dna_b)
    assert direction is not None
    
    # Definition dependency change
    dna_a = _make_dna(definition_dependencies=["A"])
    dna_b = _make_dna(definition_dependencies=["A", "B"])
    direction, _, _ = detect_definition_dependency_change(dna_a, dna_b)
    assert direction is not None
    
    # Temporal change
    dna_a = _make_dna(temporal_constraints=["X"])
    dna_b = _make_dna(temporal_constraints=["X", "Y"])
    direction, _, _ = detect_temporal_change(dna_a, dna_b)
    assert direction is not None
