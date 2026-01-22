"""Public service functions for the Universal Clause Comparer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from .agents.document_layout import (
    LayoutResult,
    doc_id_from_pdf,
    run_document_layout,
)
from .agents.definitions import (
    get_all_expanded_blocks,
    get_definitions,
    run_definitions_agent,
)
from .agents.clause_classification import (
    get_all_classifications,
    run_clause_classification,
)
from .config_loader import get_threshold
from .cues.grammar import detect_cues, within_operational_length
from .facets.extract import diff_facets as compute_facet_diff
from .facets.extract import extract_facets
from .ontology.schema import link_concepts
from .prototypes.library import load_library
from .retrieval.align import align_blocks
from .scoring.ors import compute_ors
from .storage.classification_store import BlockClassification
from .storage.definitions_store import BlockExpansion, Definition
from .typing.clauses import classify_clause


@dataclass
class PolicyPreprocessResult:
    """Result of full policy preprocessing (Segments 1 + 2 + 3)."""

    doc_id: str
    blocks: List[Dict[str, object]]
    definitions: List[Definition]
    expansions: List[BlockExpansion]
    classifications: List[BlockClassification]


def preprocess_policy(
    pdf_bytes: bytes,
    *,
    layout: LayoutResult | None = None,
) -> List[Dict[str, object]]:
    """Full preprocessing pipeline returning structured block information.

    Args:
        pdf_bytes: Raw PDF content.
        layout: Optional pre-computed layout result. If not provided, the
            document layout pipeline will be executed.
    """
    if layout is None:
        layout = run_document_layout(pdf_bytes, doc_id=doc_id_from_pdf(pdf_bytes))
    filtered_blocks = layout.blocks

    library = load_library()
    proto_scores = library.score([block.text for block in filtered_blocks])
    ors_theta = get_threshold("ors_theta", 0.55)

    processed: List[Dict[str, object]] = []
    for block, proto in zip(filtered_blocks, proto_scores):
        cues = detect_cues(block.text)
        if not within_operational_length(block.text):
            continue

        clause_type = classify_clause(block.text, cues)
        concepts = link_concepts(block.text)
        ors = compute_ors(
            pos_sim=proto.max_sim_positive,
            neg_sim=proto.max_sim_negative,
            cue_count=len(cues),
            section_admin=block.is_admin,
            has_concepts=bool(concepts),
        )
        block.clause_type = clause_type.value
        block.concepts = concepts
        block.ors = ors
        block.max_sim_positive = proto.max_sim_positive
        block.max_sim_negative = proto.max_sim_negative

        why_kept = []
        if cues:
            why_kept.append(f"cues={sorted(cues)}")
        if block.section_path:
            why_kept.append(f"section={' > '.join(block.section_path)}")
        why_kept.append("length within operational window")
        why_kept.append(f"pos_sim={proto.max_sim_positive:.2f}")
        why_kept.append(f"neg_sim={proto.max_sim_negative:.2f}")
        why_kept.append(f"ors={ors:.2f} (theta={ors_theta:.2f})")
        if block.is_admin:
            why_kept.append("section tagged as admin/compliance")
        if concepts:
            why_kept.append(f"concepts={concepts}")

        processed.append(
            {
                "id": block.id,
                "page_number": block.page_number,
                "text": block.text,
                "bbox": tuple(block.bbox),
                "section_path": block.section_path,
                "is_admin": block.is_admin,
                "clause_type": clause_type.value,
                "ors": ors,
                "ors_threshold": ors_theta,
                "is_operational": ors >= ors_theta and not block.is_admin,
                "max_sim_positive": proto.max_sim_positive,
                "max_sim_negative": proto.max_sim_negative,
                "concepts": concepts,
                "cues": sorted(cues),
                "why_kept": why_kept,
            }
        )
    return processed


def preprocess_policy_full(pdf_bytes: bytes) -> PolicyPreprocessResult:
    """
    Full preprocessing pipeline: Segments 1-3.

    - Segment 1: Document Layout
    - Segment 2: Definitions extraction + expansion
    - Segment 3: Clause classification

    Returns structured block information with definitions, expansions, and classifications.
    """
    doc_id = doc_id_from_pdf(pdf_bytes)

    # Segment 1: Document Layout
    layout = run_document_layout(pdf_bytes, doc_id=doc_id)

    # Segment 2: Definitions
    run_definitions_agent(doc_id)

    # Segment 3: Clause Classification
    run_clause_classification(doc_id)

    # Build result reusing the layout we already computed
    blocks = preprocess_policy(pdf_bytes, layout=layout)
    definitions = get_definitions(doc_id)
    expansions = get_all_expanded_blocks(doc_id)
    classifications = get_all_classifications(doc_id)

    return PolicyPreprocessResult(
        doc_id=doc_id,
        blocks=blocks,
        definitions=definitions,
        expansions=expansions,
        classifications=classifications,
    )


def align_policy_blocks(
    blocks_a: Sequence[Dict[str, object]],
    blocks_b: Sequence[Dict[str, object]],
) -> List[Dict[str, object]]:
    alignments = align_blocks(blocks_a, blocks_b)
    results: List[Dict[str, object]] = []
    for alignment in alignments:
        results.append(
            {
                "clause_type": alignment.clause_type,
                "block_id_a": alignment.block_id_a,
                "block_id_b": alignment.block_id_b,
                "bm25_score": alignment.bm25_score,
                "tfidf_score": alignment.tfidf_score,
                "concept_bonus": alignment.concept_bonus,
                "final_score": alignment.final_score,
                "rationale": alignment.rationale,
            }
        )
    return results


def diff_policy_facets(
    matches: Sequence[Dict[str, object]],
    lookup_a: Dict[str, Dict[str, object]],
    lookup_b: Dict[str, Dict[str, object]],
) -> List[Dict[str, object]]:
    diffs: List[Dict[str, object]] = []
    for match in matches:
        block_a = lookup_a.get(match["block_id_a"])
        block_b = lookup_b.get(match["block_id_b"])
        if not block_a or not block_b:
            continue
        facets_a = extract_facets(str(block_a.get("text", "")), block_a.get("concepts", []))
        facets_b = extract_facets(str(block_b.get("text", "")), block_b.get("concepts", []))
        diff = compute_facet_diff(facets_a, facets_b)
        diffs.append(
            {
                "clause_type": match.get("clause_type"),
                "block_id_a": match.get("block_id_a"),
                "block_id_b": match.get("block_id_b"),
                "broader": diff["broader"],
                "narrower": diff["narrower"],
                "ambiguous": diff["ambiguous"],
                "changed_facets": diff["changed_facets"],
            }
        )
    return diffs
