"""Tests for Segment 7: Narrative Summarisation Agent."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import storage models first
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "python-backend"))

from ucc.storage.summary_store import (
    BulletDirection,
    BulletSeverity,
    EvidenceRef,
    NarrativeResult,
    SummaryBullet,
    SummaryCounts,
    SummaryStore,
)
from ucc.storage.delta_store import ClauseDelta, DeltaDirection, DeltaStore, DeltaType
from ucc.storage.alignment_store import AlignmentStore, AlignmentType, ClauseAlignment
from ucc.storage.layout_store import LayoutStore
from ucc.io.pdf_blocks import Block

from ucc.agents.narrative_summarisation import (
    _truncate,
    _format_list,
    _generate_scope_bullet,
    _generate_strictness_bullet,
    _generate_carve_out_bullet,
    _generate_numeric_bullet,
    _generate_definition_dependency_bullet,
    _generate_temporal_bullet,
    _compute_severity,
    _extract_evidence,
    run_narrative_summarisation,
    get_summary,
    get_bullets,
    MAX_QUOTE_LENGTH,
    REVIEW_CONFIDENCE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    """Create a temporary database for tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
def sample_delta_scope_broader():
    """Sample delta for scope broadening."""
    return ClauseDelta(
        doc_id_a="doc_A",
        block_id_a="block_1",
        doc_id_b="doc_B",
        block_id_b="block_2",
        delta_type=DeltaType.SCOPE_CHANGE,
        direction=DeltaDirection.BROADER,
        details={
            "added_connectors": ["arising from", "in connection with"],
            "removed_connectors": [],
        },
        evidence={
            "connectors_a": [],
            "connectors_b": ["arising from", "in connection with"],
        },
        confidence=0.8,
        clause_type="EXCLUSION",
    )


@pytest.fixture
def sample_delta_numeric():
    """Sample delta for numeric change."""
    return ClauseDelta(
        doc_id_a="doc_A",
        block_id_a="block_1",
        doc_id_b="doc_B",
        block_id_b="block_2",
        delta_type=DeltaType.NUMERIC_CHANGE,
        direction=DeltaDirection.NARROWER,
        details={
            "limit_decreased": {"from": 1000000, "to": 500000},
            "deductible": {"from": 1000, "to": 2500},
        },
        evidence={"limits_a": {"limit": 1000000}, "limits_b": {"limit": 500000}},
        confidence=0.9,
        clause_type="LIMIT",
    )


@pytest.fixture
def sample_delta_carve_out():
    """Sample delta for carve-out change."""
    return ClauseDelta(
        doc_id_a="doc_A",
        block_id_a="block_1",
        doc_id_b="doc_B",
        block_id_b="block_2",
        delta_type=DeltaType.CARVE_OUT_CHANGE,
        direction=DeltaDirection.BROADER,
        details={
            "added_carve_outs": ["except where negligence is proven"],
            "removed_carve_outs": [],
        },
        evidence={
            "carve_outs_a": [],
            "carve_outs_b": ["except where negligence is proven"],
        },
        confidence=0.75,
        clause_type="EXCLUSION",
    )


@pytest.fixture
def sample_delta_low_confidence():
    """Sample delta with low confidence."""
    return ClauseDelta(
        doc_id_a="doc_A",
        block_id_a="block_1",
        doc_id_b="doc_B",
        block_id_b="block_2",
        delta_type=DeltaType.DEFINITION_DEPENDENCY_CHANGE,
        direction=DeltaDirection.AMBIGUOUS,
        details={"added_dependencies": ["INSURED"]},
        evidence={"deps_a": [], "deps_b": ["INSURED"]},
        confidence=0.3,
        clause_type="COVERAGE_GRANT",
    )


# ---------------------------------------------------------------------------
# Unit Tests: Helper Functions
# ---------------------------------------------------------------------------


class TestTruncate:
    """Tests for _truncate function."""

    def test_short_text_unchanged(self):
        text = "Short text"
        assert _truncate(text, 50) == text

    def test_long_text_truncated(self):
        text = "This is a very long text that should be truncated because it exceeds the maximum length"
        result = _truncate(text, 50)
        assert len(result) <= 50
        assert result.endswith("...")

    def test_truncate_at_word_boundary(self):
        text = "The quick brown fox jumps over the lazy dog"
        result = _truncate(text, 30)
        assert not result.endswith(" ...")  # Should break at word boundary


class TestFormatList:
    """Tests for _format_list function."""

    def test_empty_list(self):
        assert _format_list([]) == ""

    def test_single_item(self):
        assert _format_list(["foo"]) == '"foo"'

    def test_multiple_items(self):
        result = _format_list(["foo", "bar", "baz"])
        assert '"foo"' in result
        assert '"bar"' in result
        assert '"baz"' in result

    def test_truncates_long_list(self):
        items = ["a", "b", "c", "d", "e"]
        result = _format_list(items, max_items=3)
        assert "(+2 more)" in result


# ---------------------------------------------------------------------------
# Unit Tests: Bullet Templates
# ---------------------------------------------------------------------------


class TestScopeBulletTemplate:
    """Tests for scope change bullet generation."""

    def test_broader_with_connectors(self, sample_delta_scope_broader):
        bullet = _generate_scope_bullet(sample_delta_scope_broader)
        assert "broader" in bullet.lower()
        assert "arising from" in bullet
        assert "in connection with" in bullet

    def test_narrower_scope(self):
        delta = ClauseDelta(
            doc_id_a="a",
            block_id_a="b1",
            doc_id_b="b",
            block_id_b="b2",
            delta_type=DeltaType.SCOPE_CHANGE,
            direction=DeltaDirection.NARROWER,
            details={"removed_connectors": ["related to"]},
            evidence={},
            confidence=0.8,
            clause_type="EXCLUSION",
        )
        bullet = _generate_scope_bullet(delta)
        assert "narrower" in bullet.lower()


class TestStrictnessBulletTemplate:
    """Tests for strictness change bullet generation."""

    def test_strictness_increased(self):
        delta = ClauseDelta(
            doc_id_a="a",
            block_id_a="b1",
            doc_id_b="b",
            block_id_b="b2",
            delta_type=DeltaType.STRICTNESS_CHANGE,
            direction=DeltaDirection.NARROWER,
            details={"from_strictness": "conditional", "to_strictness": "absolute"},
            evidence={},
            confidence=0.8,
            clause_type="CONDITION",
        )
        bullet = _generate_strictness_bullet(delta)
        assert "conditional" in bullet
        assert "absolute" in bullet
        assert "rigidly" in bullet.lower()


class TestNumericBulletTemplate:
    """Tests for numeric change bullet generation."""

    def test_numeric_with_numbers_from_details(self, sample_delta_numeric):
        bullet = _generate_numeric_bullet(sample_delta_numeric)
        # Should only use numbers from delta.details
        assert "$1,000,000" in bullet or "1000000" in bullet
        assert "$500,000" in bullet or "500000" in bullet

    def test_no_hallucinated_numbers(self):
        delta = ClauseDelta(
            doc_id_a="a",
            block_id_a="b1",
            doc_id_b="b",
            block_id_b="b2",
            delta_type=DeltaType.NUMERIC_CHANGE,
            direction=DeltaDirection.AMBIGUOUS,
            details={},  # Empty details - no numbers to show
            evidence={},
            confidence=0.8,
            clause_type="LIMIT",
        )
        bullet = _generate_numeric_bullet(delta)
        # Should not contain any specific numbers
        assert "review" in bullet.lower()


class TestCarveOutBulletTemplate:
    """Tests for carve-out change bullet generation."""

    def test_carve_out_added(self, sample_delta_carve_out):
        bullet = _generate_carve_out_bullet(sample_delta_carve_out)
        assert "negligence" in bullet.lower()
        assert "carve-out" in bullet.lower() or "exception" in bullet.lower()


class TestDefinitionDependencyBulletTemplate:
    """Tests for definition dependency bullet generation."""

    def test_dependency_change(self, sample_delta_low_confidence):
        bullet = _generate_definition_dependency_bullet(sample_delta_low_confidence)
        assert "INSURED" in bullet
        assert "definition" in bullet.lower()


class TestTemporalBulletTemplate:
    """Tests for temporal constraint bullet generation."""

    def test_temporal_constraint_added(self):
        delta = ClauseDelta(
            doc_id_a="a",
            block_id_a="b1",
            doc_id_b="b",
            block_id_b="b2",
            delta_type=DeltaType.TEMPORAL_CHANGE,
            direction=DeltaDirection.NARROWER,
            details={"added_constraints": ["within 30 days"]},
            evidence={},
            confidence=0.8,
            clause_type="CONDITION",
        )
        bullet = _generate_temporal_bullet(delta)
        assert "30 days" in bullet


# ---------------------------------------------------------------------------
# Unit Tests: Severity Scoring
# ---------------------------------------------------------------------------


class TestSeverityScoring:
    """Tests for severity computation."""

    def test_low_confidence_gets_review(self, sample_delta_low_confidence):
        severity, confidence = _compute_severity(sample_delta_low_confidence, 0.8)
        assert severity == BulletSeverity.REVIEW
        assert confidence < REVIEW_CONFIDENCE_THRESHOLD

    def test_high_clause_type_higher_severity(self, sample_delta_scope_broader):
        severity, confidence = _compute_severity(sample_delta_scope_broader, 0.8)
        # EXCLUSION is a high-severity clause type
        assert severity in (BulletSeverity.HIGH, BulletSeverity.MEDIUM)

    def test_narrower_direction_increases_severity(self, sample_delta_numeric):
        severity, confidence = _compute_severity(sample_delta_numeric, 0.8)
        # NARROWER direction should contribute to severity
        assert severity == BulletSeverity.HIGH


# ---------------------------------------------------------------------------
# Unit Tests: Evidence Extraction
# ---------------------------------------------------------------------------


class TestEvidenceExtraction:
    """Tests for evidence reference extraction."""

    def test_evidence_includes_block_ids(self, sample_delta_scope_broader):
        evidence = _extract_evidence(sample_delta_scope_broader, "text A", "text B")
        assert evidence.block_id_a == "block_1"
        assert evidence.block_id_b == "block_2"

    def test_evidence_includes_delta_id(self, sample_delta_scope_broader):
        evidence = _extract_evidence(sample_delta_scope_broader, "text A", "text B")
        assert len(evidence.delta_ids) == 1
        assert len(evidence.delta_ids[0]) == 12  # Truncated hash

    def test_evidence_includes_quote_fragments(self, sample_delta_scope_broader):
        evidence = _extract_evidence(sample_delta_scope_broader, "text A", "text B")
        # Should have some fragments from evidence or text
        assert len(evidence.quote_fragments) > 0


# ---------------------------------------------------------------------------
# Integration Tests: Storage
# ---------------------------------------------------------------------------


class TestSummaryStorage:
    """Tests for summary persistence."""

    def test_persist_and_retrieve(self, temp_db):
        store = SummaryStore(db_path=temp_db)

        evidence = EvidenceRef(
            block_id_a="b1",
            block_id_b="b2",
            delta_ids=["d1"],
            quote_fragments=["fragment"],
        )
        bullet = SummaryBullet(
            bullet_id="bullet_1",
            text="Test bullet",
            severity=BulletSeverity.HIGH,
            delta_types=["scope_change"],
            direction=BulletDirection.BROADER,
            evidence_refs=evidence,
            clause_type="EXCLUSION",
            confidence=0.8,
        )
        counts = SummaryCounts(
            matched_clauses=5,
            unmatched_clauses=2,
            deltas_by_type={"scope_change": 3},
            review_needed=1,
            total_bullets=1,
        )
        result = NarrativeResult(
            doc_id_a="doc_A",
            doc_id_b="doc_B",
            bullets=[bullet],
            counts=counts,
            confidence=0.8,
        )

        store.persist_summary(result)
        retrieved = store.get_summary("doc_A", "doc_B")

        assert retrieved is not None
        assert retrieved.doc_id_a == "doc_A"
        assert retrieved.doc_id_b == "doc_B"
        assert len(retrieved.bullets) == 1
        assert retrieved.bullets[0].text == "Test bullet"
        assert retrieved.bullets[0].evidence_refs.block_id_a == "b1"
        assert retrieved.counts.matched_clauses == 5

    def test_idempotent_persist(self, temp_db):
        store = SummaryStore(db_path=temp_db)

        result = NarrativeResult(
            doc_id_a="doc_A",
            doc_id_b="doc_B",
            bullets=[],
            counts=SummaryCounts(),
            confidence=0.5,
        )

        store.persist_summary(result)
        store.persist_summary(result)  # Should not error

        # Should still only have one record
        with sqlite3.connect(temp_db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM comparison_summaries"
            ).fetchone()[0]
            assert count == 1

    def test_get_bullets_by_severity(self, temp_db):
        store = SummaryStore(db_path=temp_db)

        evidence = EvidenceRef("b1", "b2", ["d1"], [])
        bullets = [
            SummaryBullet(
                "b1",
                "High",
                BulletSeverity.HIGH,
                [],
                BulletDirection.BROADER,
                evidence,
            ),
            SummaryBullet(
                "b2",
                "Low",
                BulletSeverity.LOW,
                [],
                BulletDirection.NEUTRAL,
                evidence,
            ),
        ]
        result = NarrativeResult(
            "doc_A", "doc_B", bullets, SummaryCounts(), 0.7
        )
        store.persist_summary(result)

        high_bullets = store.get_bullets("doc_A", "doc_B", BulletSeverity.HIGH)
        assert len(high_bullets) == 1
        assert high_bullets[0].text == "High"


# ---------------------------------------------------------------------------
# Integration Tests: Full Pipeline (Mocked)
# ---------------------------------------------------------------------------


class TestNarrativeSummarisation:
    """Integration tests for run_narrative_summarisation."""

    def test_bullets_always_have_evidence_refs(self, temp_db):
        """Template bullets must include evidence_refs always."""
        # Mock stores
        with (
            patch("ucc.agents.narrative_summarisation.AlignmentStore") as MockAlignmentStore,
            patch("ucc.agents.narrative_summarisation.DeltaStore") as MockDeltaStore,
            patch("ucc.agents.narrative_summarisation.LayoutStore") as MockLayoutStore,
            patch("ucc.agents.narrative_summarisation.SummaryStore") as MockSummaryStore,
        ):
            # Setup mocks
            mock_alignment_store = MagicMock()
            mock_alignment_store.get_alignments.return_value = [
                ClauseAlignment(
                    doc_id_a="doc_A",
                    block_id_a="b1",
                    doc_id_b="doc_B",
                    block_id_b="b2",
                    clause_type="EXCLUSION",
                    alignment_score=0.8,
                    score_components={},
                    confidence=0.8,
                    alignment_type=AlignmentType.ONE_TO_ONE,
                )
            ]
            MockAlignmentStore.return_value = mock_alignment_store

            mock_delta_store = MagicMock()
            mock_delta_store.get_deltas.return_value = [
                ClauseDelta(
                    doc_id_a="doc_A",
                    block_id_a="b1",
                    doc_id_b="doc_B",
                    block_id_b="b2",
                    delta_type=DeltaType.SCOPE_CHANGE,
                    direction=DeltaDirection.BROADER,
                    details={"added_connectors": ["arising from"]},
                    evidence={"connectors_b": ["arising from"]},
                    confidence=0.8,
                    clause_type="EXCLUSION",
                )
            ]
            MockDeltaStore.return_value = mock_delta_store

            mock_layout_store = MagicMock()
            mock_layout_store.get_blocks.return_value = [
                Block(
                    id="b1",
                    page_number=1,
                    text="Sample text A",
                    bbox=(0, 0, 100, 100),
                    page_width=612,
                    page_height=792,
                    fonts=[],
                ),
                Block(
                    id="b2",
                    page_number=1,
                    text="Sample text B",
                    bbox=(0, 0, 100, 100),
                    page_width=612,
                    page_height=792,
                    fonts=[],
                ),
            ]
            MockLayoutStore.return_value = mock_layout_store

            mock_summary_store = MagicMock()
            MockSummaryStore.return_value = mock_summary_store

            result = run_narrative_summarisation("doc_A", "doc_B")

            # All bullets must have evidence_refs
            for bullet in result.bullets:
                assert bullet.evidence_refs is not None
                assert bullet.evidence_refs.block_id_a is not None
                assert len(bullet.evidence_refs.delta_ids) > 0

    def test_no_hallucinated_numbers(self, temp_db):
        """No bullet should include numbers not present in delta.details."""
        with (
            patch("ucc.agents.narrative_summarisation.AlignmentStore") as MockAlignmentStore,
            patch("ucc.agents.narrative_summarisation.DeltaStore") as MockDeltaStore,
            patch("ucc.agents.narrative_summarisation.LayoutStore") as MockLayoutStore,
            patch("ucc.agents.narrative_summarisation.SummaryStore") as MockSummaryStore,
        ):
            mock_alignment_store = MagicMock()
            mock_alignment_store.get_alignments.return_value = [
                ClauseAlignment(
                    doc_id_a="doc_A",
                    block_id_a="b1",
                    doc_id_b="doc_B",
                    block_id_b="b2",
                    clause_type="LIMIT",
                    alignment_score=0.8,
                    score_components={},
                    confidence=0.8,
                    alignment_type=AlignmentType.ONE_TO_ONE,
                )
            ]
            MockAlignmentStore.return_value = mock_alignment_store

            # Delta with specific numbers in details
            mock_delta_store = MagicMock()
            mock_delta_store.get_deltas.return_value = [
                ClauseDelta(
                    doc_id_a="doc_A",
                    block_id_a="b1",
                    doc_id_b="doc_B",
                    block_id_b="b2",
                    delta_type=DeltaType.NUMERIC_CHANGE,
                    direction=DeltaDirection.NARROWER,
                    details={"limit": {"from": 100000, "to": 50000}},
                    evidence={},
                    confidence=0.9,
                    clause_type="LIMIT",
                )
            ]
            MockDeltaStore.return_value = mock_delta_store

            mock_layout_store = MagicMock()
            mock_layout_store.get_blocks.return_value = []
            MockLayoutStore.return_value = mock_layout_store

            mock_summary_store = MagicMock()
            MockSummaryStore.return_value = mock_summary_store

            result = run_narrative_summarisation("doc_A", "doc_B")

            # Check that bullet text only contains numbers from details
            for bullet in result.bullets:
                if DeltaType.NUMERIC_CHANGE.value in bullet.delta_types:
                    # Bullet can contain 100000 or 50000 (formatted or not)
                    # but not arbitrary numbers like 999999
                    text = bullet.text.replace(",", "").replace("$", "")
                    import re

                    numbers = re.findall(r"\d+", text)
                    for num in numbers:
                        num_int = int(num)
                        # Allow only numbers from details or small reference numbers
                        assert num_int in (100000, 50000) or num_int < 100

    def test_low_confidence_produces_review_severity(self, temp_db):
        """Low-confidence alignments should produce 'review' severity bullets."""
        with (
            patch("ucc.agents.narrative_summarisation.AlignmentStore") as MockAlignmentStore,
            patch("ucc.agents.narrative_summarisation.DeltaStore") as MockDeltaStore,
            patch("ucc.agents.narrative_summarisation.LayoutStore") as MockLayoutStore,
            patch("ucc.agents.narrative_summarisation.SummaryStore") as MockSummaryStore,
        ):
            mock_alignment_store = MagicMock()
            mock_alignment_store.get_alignments.return_value = [
                ClauseAlignment(
                    doc_id_a="doc_A",
                    block_id_a="b1",
                    doc_id_b="doc_B",
                    block_id_b="b2",
                    clause_type="COVERAGE_GRANT",
                    alignment_score=0.3,
                    score_components={},
                    confidence=0.3,  # Low confidence
                    alignment_type=AlignmentType.ONE_TO_ONE,
                )
            ]
            MockAlignmentStore.return_value = mock_alignment_store

            mock_delta_store = MagicMock()
            mock_delta_store.get_deltas.return_value = [
                ClauseDelta(
                    doc_id_a="doc_A",
                    block_id_a="b1",
                    doc_id_b="doc_B",
                    block_id_b="b2",
                    delta_type=DeltaType.SCOPE_CHANGE,
                    direction=DeltaDirection.AMBIGUOUS,
                    details={},
                    evidence={},
                    confidence=0.4,  # Also low
                    clause_type="COVERAGE_GRANT",
                )
            ]
            MockDeltaStore.return_value = mock_delta_store

            mock_layout_store = MagicMock()
            mock_layout_store.get_blocks.return_value = []
            MockLayoutStore.return_value = mock_layout_store

            mock_summary_store = MagicMock()
            MockSummaryStore.return_value = mock_summary_store

            result = run_narrative_summarisation("doc_A", "doc_B")

            # At least one bullet should be REVIEW
            assert any(b.severity == BulletSeverity.REVIEW for b in result.bullets)

    def test_deterministic_output(self, temp_db):
        """Same inputs should produce same bullets."""
        with (
            patch("ucc.agents.narrative_summarisation.AlignmentStore") as MockAlignmentStore,
            patch("ucc.agents.narrative_summarisation.DeltaStore") as MockDeltaStore,
            patch("ucc.agents.narrative_summarisation.LayoutStore") as MockLayoutStore,
            patch("ucc.agents.narrative_summarisation.SummaryStore") as MockSummaryStore,
        ):
            mock_alignment_store = MagicMock()
            mock_alignment_store.get_alignments.return_value = [
                ClauseAlignment(
                    doc_id_a="doc_A",
                    block_id_a="b1",
                    doc_id_b="doc_B",
                    block_id_b="b2",
                    clause_type="CONDITION",
                    alignment_score=0.8,
                    score_components={},
                    confidence=0.8,
                    alignment_type=AlignmentType.ONE_TO_ONE,
                )
            ]
            MockAlignmentStore.return_value = mock_alignment_store

            mock_delta_store = MagicMock()
            mock_delta_store.get_deltas.return_value = [
                ClauseDelta(
                    doc_id_a="doc_A",
                    block_id_a="b1",
                    doc_id_b="doc_B",
                    block_id_b="b2",
                    delta_type=DeltaType.STRICTNESS_CHANGE,
                    direction=DeltaDirection.NARROWER,
                    details={"from_strictness": "conditional", "to_strictness": "absolute"},
                    evidence={},
                    confidence=0.85,
                    clause_type="CONDITION",
                ),
                ClauseDelta(
                    doc_id_a="doc_A",
                    block_id_a="b3",
                    doc_id_b="doc_B",
                    block_id_b="b4",
                    delta_type=DeltaType.CARVE_OUT_CHANGE,
                    direction=DeltaDirection.BROADER,
                    details={"added_carve_outs": ["unless prior approval"]},
                    evidence={},
                    confidence=0.75,
                    clause_type="EXCLUSION",
                ),
            ]
            MockDeltaStore.return_value = mock_delta_store

            mock_layout_store = MagicMock()
            mock_layout_store.get_blocks.return_value = []
            MockLayoutStore.return_value = mock_layout_store

            mock_summary_store = MagicMock()
            MockSummaryStore.return_value = mock_summary_store

            # Run twice
            result1 = run_narrative_summarisation("doc_A", "doc_B")
            result2 = run_narrative_summarisation("doc_A", "doc_B")

            # Should produce identical bullets
            assert len(result1.bullets) == len(result2.bullets)
            for b1, b2 in zip(result1.bullets, result2.bullets):
                assert b1.bullet_id == b2.bullet_id
                assert b1.text == b2.text
                assert b1.severity == b2.severity


# ---------------------------------------------------------------------------
# Guardrail Tests
# ---------------------------------------------------------------------------


class TestGuardrails:
    """Tests ensuring guardrails are enforced."""

    def test_no_legal_advice_words(self):
        """Bullet text should not contain legal advice words."""
        # Test all template functions
        deltas = [
            ClauseDelta("a", "b1", "b", "b2", DeltaType.SCOPE_CHANGE, DeltaDirection.BROADER, {}, {}, 0.8),
            ClauseDelta("a", "b1", "b", "b2", DeltaType.STRICTNESS_CHANGE, DeltaDirection.NARROWER, {"from_strictness": "conditional", "to_strictness": "absolute"}, {}, 0.8),
            ClauseDelta("a", "b1", "b", "b2", DeltaType.NUMERIC_CHANGE, DeltaDirection.NARROWER, {}, {}, 0.8),
        ]

        forbidden_phrases = [
            "you should",
            "we recommend",
            "this is better",
            "this is worse",
            "you must",
            "we advise",
        ]

        for delta in deltas:
            if delta.delta_type == DeltaType.SCOPE_CHANGE:
                bullet = _generate_scope_bullet(delta)
            elif delta.delta_type == DeltaType.STRICTNESS_CHANGE:
                bullet = _generate_strictness_bullet(delta)
            elif delta.delta_type == DeltaType.NUMERIC_CHANGE:
                bullet = _generate_numeric_bullet(delta)
            else:
                continue

            bullet_lower = bullet.lower()
            for phrase in forbidden_phrases:
                assert phrase not in bullet_lower, f"Forbidden phrase '{phrase}' in: {bullet}"

    def test_allowed_directional_words(self):
        """Bullets should use allowed directional words."""
        delta_broader = ClauseDelta(
            doc_id_a="a",
            block_id_a="b1",
            doc_id_b="b",
            block_id_b="b2",
            delta_type=DeltaType.SCOPE_CHANGE,
            direction=DeltaDirection.BROADER,
            details={"added_connectors": ["test"]},
            evidence={},
            confidence=0.8,
            clause_type="EXCLUSION",
        )
        bullet = _generate_scope_bullet(delta_broader)

        # Should contain allowed word
        allowed_words = ["broader", "narrower", "added", "removed", "increased", "decreased"]
        has_allowed = any(w in bullet.lower() for w in allowed_words)
        assert has_allowed, f"No allowed directional word in: {bullet}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
