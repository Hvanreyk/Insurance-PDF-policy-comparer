"""Tests for Segment 4: Clause DNA Agent (Legal Feature Extraction)."""

from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "python-backend"))

from ucc.agents.clause_dna import (
    _extract_burden_shift,
    _extract_carve_outs,
    _extract_entities,
    _extract_numbers,
    _extract_polarity,
    _extract_scope_connectors,
    _extract_strictness,
    _extract_temporal_constraints,
    get_all_dna,
    get_clause_dna,
    get_dna_by_type,
    run_clause_dna_agent,
)
from ucc.agents.document_layout import doc_id_from_pdf, run_document_layout
from ucc.agents.definitions import run_definitions_agent
from ucc.agents.clause_classification import run_clause_classification
from ucc.storage.classification_store import ClauseType
from ucc.storage.dna_store import Polarity, Strictness


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_policy_a() -> bytes:
    return Path("tests/fixtures/policy_A.pdf").read_bytes()


# ---------------------------------------------------------------------------
# Unit Tests: Polarity Extraction
# ---------------------------------------------------------------------------


def test_polarity_from_exclusion_type():
    polarity, signals = _extract_polarity(ClauseType.EXCLUSION, "Some exclusion text")
    assert polarity == Polarity.REMOVE
    assert "clause_type=EXCLUSION" in signals[0]


def test_polarity_from_coverage_grant_type():
    polarity, signals = _extract_polarity(ClauseType.COVERAGE_GRANT, "We will pay for loss")
    assert polarity == Polarity.GRANT


def test_polarity_from_condition_type():
    polarity, signals = _extract_polarity(ClauseType.CONDITION, "You must notify us")
    assert polarity == Polarity.RESTRICT


def test_polarity_endorsement_extends_coverage():
    polarity, signals = _extract_polarity(
        ClauseType.ENDORSEMENT,
        "This endorsement extends to include cyber liability"
    )
    assert polarity == Polarity.GRANT
    assert any("extends coverage" in s for s in signals)


def test_polarity_endorsement_removes_coverage():
    polarity, signals = _extract_polarity(
        ClauseType.ENDORSEMENT,
        "This endorsement excludes all flood coverage"
    )
    assert polarity == Polarity.REMOVE


# ---------------------------------------------------------------------------
# Unit Tests: Strictness Extraction
# ---------------------------------------------------------------------------


def test_strictness_absolute():
    strictness, signals = _extract_strictness("We will not cover any loss arising from flood.")
    assert strictness == Strictness.ABSOLUTE
    assert any("absolute" in s for s in signals)


def test_strictness_conditional():
    strictness, signals = _extract_strictness("Cover is provided subject to the following conditions.")
    assert strictness == Strictness.CONDITIONAL


def test_strictness_discretionary():
    strictness, signals = _extract_strictness("We may, at our discretion, extend the period.")
    assert strictness == Strictness.DISCRETIONARY


def test_strictness_no_cover_provided():
    strictness, signals = _extract_strictness("No cover is provided for war or terrorism.")
    assert strictness == Strictness.ABSOLUTE


def test_strictness_unless():
    strictness, signals = _extract_strictness("You are covered unless the loss is caused by fraud.")
    assert strictness == Strictness.CONDITIONAL


# ---------------------------------------------------------------------------
# Unit Tests: Scope Connectors
# ---------------------------------------------------------------------------


def test_scope_connectors_arising_from():
    connectors, signals = _extract_scope_connectors("Loss arising from pollution is excluded.")
    assert "arising from" in connectors


def test_scope_connectors_in_connection_with():
    connectors, signals = _extract_scope_connectors("Claims in connection with cyber events.")
    assert "in connection with" in connectors


def test_scope_connectors_directly_or_indirectly():
    connectors, signals = _extract_scope_connectors("Loss directly or indirectly caused by war.")
    assert "directly or indirectly" in connectors


def test_scope_connectors_multiple():
    text = "Loss arising from or in connection with pollution, directly or indirectly caused."
    connectors, signals = _extract_scope_connectors(text)
    assert len(connectors) >= 2
    assert "arising from" in connectors
    assert "in connection with" in connectors


def test_scope_connectors_widening_vs_narrowing():
    # Widening language
    wide_connectors, _ = _extract_scope_connectors("howsoever caused or arising")
    assert "howsoever caused/arising" in wide_connectors
    
    # Narrowing language
    narrow_connectors, _ = _extract_scope_connectors("directly caused by fire")
    assert "directly caused by" in narrow_connectors


# ---------------------------------------------------------------------------
# Unit Tests: Carve-outs
# ---------------------------------------------------------------------------


def test_carve_out_except():
    carve_outs, signals = _extract_carve_outs("We exclude flood except for flash flooding.")
    assert len(carve_outs) == 1
    assert "except" in carve_outs[0].lower()
    assert "flash flooding" in carve_outs[0]


def test_carve_out_unless():
    carve_outs, signals = _extract_carve_outs("Not covered unless approved in writing.")
    assert len(carve_outs) == 1
    assert "approved in writing" in carve_outs[0]


def test_carve_out_provided_that():
    carve_outs, signals = _extract_carve_outs("Cover applies provided that notice is given within 30 days.")
    assert len(carve_outs) >= 1
    assert any("notice" in c for c in carve_outs)


def test_carve_out_multiple():
    text = "Excluded except for sudden events, unless pre-approved, provided that documented."
    carve_outs, signals = _extract_carve_outs(text)
    assert len(carve_outs) >= 2


def test_carve_out_truncation():
    long_text = "Except for " + "a " * 150 + "very long exception text."
    carve_outs, signals = _extract_carve_outs(long_text)
    if carve_outs:
        assert len(carve_outs[0]) <= 220  # Should be truncated


# ---------------------------------------------------------------------------
# Unit Tests: Entity Extraction
# ---------------------------------------------------------------------------


def test_entities_perils():
    entities, signals = _extract_entities("Loss caused by fire, flood, or earthquake.")
    peril_entities = [e for e in entities if e.startswith("peril:")]
    assert "peril:fire" in peril_entities
    assert "peril:flood" in peril_entities
    assert "peril:earthquake" in peril_entities


def test_entities_cyber():
    entities, signals = _extract_entities("Cyber liability including data breach and ransomware.")
    assert "peril:cyber" in entities


def test_entities_property_types():
    entities, signals = _extract_entities("Coverage for building and contents damage.")
    property_entities = [e for e in entities if e.startswith("property:")]
    assert "property:building" in property_entities
    assert "property:contents" in property_entities


def test_entities_subjects():
    entities, signals = _extract_entities("The insured and any employee acting in good faith.")
    subject_entities = [e for e in entities if e.startswith("subject:")]
    assert "subject:insured" in subject_entities
    assert "subject:employee" in subject_entities


def test_entities_pollution():
    entities, signals = _extract_entities("Pollution and contamination exclusion applies.")
    assert "peril:pollution" in entities


# ---------------------------------------------------------------------------
# Unit Tests: Number Extraction
# ---------------------------------------------------------------------------


def test_numbers_currency():
    numbers, signals = _extract_numbers(
        "The limit of liability is $1,000,000 any one event.",
        ClauseType.LIMIT
    )
    assert "limits" in numbers or "amounts" in numbers


def test_numbers_deductible():
    numbers, signals = _extract_numbers(
        "The excess is $5,000 each and every claim.",
        ClauseType.LIMIT
    )
    assert "deductibles" in numbers or "amounts" in numbers


def test_numbers_percentage():
    numbers, signals = _extract_numbers(
        "We will pay 80% of the replacement cost.",
        ClauseType.COVERAGE_GRANT
    )
    assert "percentages" in numbers
    assert 80.0 in numbers["percentages"]


def test_numbers_time_days():
    numbers, signals = _extract_numbers(
        "You must notify us within 30 days.",
        ClauseType.CONDITION
    )
    assert "time_days" in numbers or "waiting_period_days" in numbers


def test_numbers_waiting_period():
    numbers, signals = _extract_numbers(
        "A waiting period of 72 hours applies.",
        ClauseType.CONDITION
    )
    assert "waiting_period_hours" in numbers


# ---------------------------------------------------------------------------
# Unit Tests: Temporal Constraints
# ---------------------------------------------------------------------------


def test_temporal_during_period():
    constraints, signals = _extract_temporal_constraints(
        "Claims first made during the period of insurance."
    )
    assert "during the period of insurance" in constraints


def test_temporal_prior_to_inception():
    constraints, signals = _extract_temporal_constraints(
        "No cover for matters known prior to inception."
    )
    assert "prior to inception" in constraints


def test_temporal_within_days():
    constraints, signals = _extract_temporal_constraints(
        "Notice must be given within 14 days."
    )
    assert any("14" in c and "days" in c for c in constraints)


def test_temporal_at_all_times():
    constraints, signals = _extract_temporal_constraints(
        "You must maintain security at all times."
    )
    assert "at all times" in constraints


def test_temporal_as_soon_as_practicable():
    constraints, signals = _extract_temporal_constraints(
        "Notify us as soon as reasonably practicable."
    )
    assert "as soon as practicable" in constraints


# ---------------------------------------------------------------------------
# Unit Tests: Burden Shift
# ---------------------------------------------------------------------------


def test_burden_shift_you_must():
    burden, signals = _extract_burden_shift("You must notify us immediately.")
    assert burden is True


def test_burden_shift_your_duty():
    burden, signals = _extract_burden_shift("Your duty to mitigate loss.")
    assert burden is True


def test_burden_shift_notify_us():
    burden, signals = _extract_burden_shift("Please notify us of any claim.")
    assert burden is True


def test_burden_shift_proof_of_loss():
    burden, signals = _extract_burden_shift("Submit proof of loss within 30 days.")
    assert burden is True


def test_burden_shift_no_burden():
    burden, signals = _extract_burden_shift("We will pay for covered loss.")
    assert burden is False


def test_burden_shift_condition_that_you():
    burden, signals = _extract_burden_shift(
        "It is a condition of this policy that you maintain records."
    )
    assert burden is True


# ---------------------------------------------------------------------------
# Unit Tests: Stability / Determinism
# ---------------------------------------------------------------------------


def test_extraction_deterministic():
    text = "We will not cover any loss arising from or in connection with pollution."
    
    # Run twice
    strictness1, _ = _extract_strictness(text)
    connectors1, _ = _extract_scope_connectors(text)
    entities1, _ = _extract_entities(text)
    
    strictness2, _ = _extract_strictness(text)
    connectors2, _ = _extract_scope_connectors(text)
    entities2, _ = _extract_entities(text)
    
    assert strictness1 == strictness2
    assert connectors1 == connectors2
    assert entities1 == entities2


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


def test_run_clause_dna_agent_with_sample_pdf(tmp_path, monkeypatch, sample_policy_a):
    """Integration test: run full DNA extraction on sample PDF."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    # Run Segments 1-3 first
    run_document_layout(sample_policy_a, doc_id=doc_id)
    run_definitions_agent(doc_id)
    run_clause_classification(doc_id)
    
    # Run Segment 4
    result = run_clause_dna_agent(doc_id)
    
    assert result.doc_id == doc_id
    assert len(result.dna_records) > 0
    assert isinstance(result.stats, dict)
    assert result.stats["total"] == len(result.dna_records)


def test_dna_persistence_round_trip(tmp_path, monkeypatch, sample_policy_a):
    """Test that DNA records are correctly persisted and retrieved."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    # Run all segments
    run_document_layout(sample_policy_a, doc_id=doc_id)
    run_definitions_agent(doc_id)
    run_clause_classification(doc_id)
    result = run_clause_dna_agent(doc_id)
    
    # Retrieve from persistence
    persisted = get_all_dna(doc_id)
    
    assert len(persisted) == len(result.dna_records)
    
    if result.dna_records:
        first = result.dna_records[0]
        retrieved = get_clause_dna(doc_id, first.block_id)
        assert retrieved is not None
        assert retrieved.clause_type == first.clause_type
        assert retrieved.polarity == first.polarity
        assert retrieved.strictness == first.strictness


def test_get_dna_by_type_api(tmp_path, monkeypatch, sample_policy_a):
    """Test the get_dna_by_type retrieval API."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    run_document_layout(sample_policy_a, doc_id=doc_id)
    run_definitions_agent(doc_id)
    run_clause_classification(doc_id)
    result = run_clause_dna_agent(doc_id)
    
    # Find a clause type that has records
    if result.dna_records:
        clause_type = result.dna_records[0].clause_type
        by_type = get_dna_by_type(doc_id, clause_type)
        assert all(dna.clause_type == clause_type for dna in by_type)


def test_dna_idempotent(tmp_path, monkeypatch, sample_policy_a):
    """Running DNA extraction twice should not duplicate data."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    # Run Segments 1-3
    run_document_layout(sample_policy_a, doc_id=doc_id)
    run_definitions_agent(doc_id)
    run_clause_classification(doc_id)
    
    # Run Segment 4 twice
    result1 = run_clause_dna_agent(doc_id)
    result2 = run_clause_dna_agent(doc_id)
    
    # Results should be identical
    assert len(result1.dna_records) == len(result2.dna_records)
    assert result1.stats == result2.stats


def test_dna_has_raw_signals(tmp_path, monkeypatch, sample_policy_a):
    """Verify that DNA records include explainable raw signals."""
    db_path = tmp_path / "layout.db"
    monkeypatch.setenv("UCC_LAYOUT_DB_PATH", str(db_path))
    
    doc_id = doc_id_from_pdf(sample_policy_a)
    
    run_document_layout(sample_policy_a, doc_id=doc_id)
    run_definitions_agent(doc_id)
    run_clause_classification(doc_id)
    result = run_clause_dna_agent(doc_id)
    
    # Every DNA record should have raw_signals
    for dna in result.dna_records:
        assert isinstance(dna.raw_signals, dict)
        # Should have at least polarity and strictness signals
        assert "polarity" in dna.raw_signals
        assert "strictness" in dna.raw_signals


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------


def test_empty_text_extraction():
    """Empty text should still produce valid (neutral) results."""
    strictness, _ = _extract_strictness("")
    assert strictness == Strictness.CONDITIONAL  # Default
    
    connectors, _ = _extract_scope_connectors("")
    assert connectors == []
    
    burden, _ = _extract_burden_shift("")
    assert burden is False


def test_complex_clause_extraction():
    """Test extraction from a complex real-world clause."""
    text = """
    We will not cover any loss or damage arising from or in connection with 
    cyber events, except where such loss is caused by fire resulting from 
    a cyber attack, provided that you notify us within 30 days of discovery.
    The limit of liability is $500,000 any one occurrence.
    """
    
    strictness, _ = _extract_strictness(text)
    assert strictness == Strictness.ABSOLUTE
    
    connectors, _ = _extract_scope_connectors(text)
    assert "arising from" in connectors
    
    carve_outs, _ = _extract_carve_outs(text)
    assert len(carve_outs) >= 1
    
    entities, _ = _extract_entities(text)
    assert "peril:cyber" in entities
    assert "peril:fire" in entities
    
    temporal, _ = _extract_temporal_constraints(text)
    assert any("30" in t and "days" in t for t in temporal)
    
    numbers, _ = _extract_numbers(text, ClauseType.EXCLUSION)
    assert numbers  # Should have some numbers extracted
