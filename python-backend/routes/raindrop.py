"""Segment 8: Raindrop-style API routes for UI delivery.

Thin layer that shapes persisted data for the frontend.
Does NOT re-run parsing, embeddings, alignment, or deltas.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ucc.agents.document_layout import doc_id_from_pdf, run_document_layout
from ucc.agents.definitions import run_definitions_agent
from ucc.agents.clause_classification import run_clause_classification
from ucc.agents.clause_dna import run_clause_dna_agent
from ucc.agents.semantic_alignment import run_semantic_alignment
from ucc.agents.delta_interpretation import run_delta_interpretation
from ucc.agents.narrative_summarisation import run_narrative_summarisation

from ucc.delivery import (
    SIMILARITY_BANDS,
    list_policies,
    get_policy_sections,
    get_section_detail,
    get_clause_pair,
    get_similarity_summary,
    register_policy,
)


router = APIRouter(prefix="/raindrop", tags=["raindrop-ui"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class PolicyMetadata(BaseModel):
    """Metadata for registering a policy."""
    name: str
    insurer: Optional[str] = None
    year: Optional[int] = None
    category: Optional[str] = None
    scope: Optional[str] = None


class PolicySummaryResponse(BaseModel):
    """Summary of a policy."""
    doc_id: str
    name: str
    insurer: Optional[str] = None
    year: Optional[int] = None
    category: Optional[str] = None
    scope: Optional[str] = None
    block_count: int = 0
    section_count: int = 0


class SectionItemResponse(BaseModel):
    """A section within a policy."""
    section_id: str
    title: str
    section_path: List[str]
    clause_count: int = 0
    similarity_score: Optional[float] = None
    similarity_band: Optional[str] = None
    similarity_color: Optional[str] = None
    matched_count: int = 0
    unmatched_count: int = 0
    delta_count: int = 0


class ClauseItemResponse(BaseModel):
    """A clause within a section."""
    block_id: str
    text: str
    clause_type: str
    section_path: List[str]
    page_number: int = 0
    is_matched: bool = False
    matched_block_id: Optional[str] = None
    similarity_score: Optional[float] = None
    similarity_band: Optional[str] = None
    delta_count: int = 0
    confidence: float = 0.5


class DeltaItem(BaseModel):
    """A delta between clauses."""
    delta_type: str
    direction: str
    details: Dict[str, Any]
    confidence: float


class ClausePairResponse(BaseModel):
    """Detail view of a matched clause pair."""
    block_id_a: str
    block_id_b: str
    text_a: str
    text_b: str
    clause_type: str
    section_path_a: List[str]
    section_path_b: List[str]
    alignment_score: float
    confidence: float
    deltas: List[Dict[str, Any]]
    evidence: Dict[str, Any]
    summary_bullets: List[Dict[str, Any]] = Field(default_factory=list)


class SimilaritySummaryResponse(BaseModel):
    """Similarity summary for the right panel."""
    doc_id: str
    name: str
    insurer: Optional[str] = None
    overall_score: float
    band: str
    color: str
    matched_count: int
    unmatched_count: int
    delta_count: int
    band_distribution: Dict[str, int] = Field(default_factory=dict)


class BandConfigResponse(BaseModel):
    """Configuration for a similarity band."""
    band: str
    label: str
    min_score: float
    max_score: float
    color: str


class UploadResponse(BaseModel):
    """Response after uploading a policy."""
    doc_id: str
    name: str
    block_count: int
    section_count: int
    message: str


class CompareResponse(BaseModel):
    """Response after comparing two policies."""
    doc_id_a: str
    doc_id_b: str
    alignment_count: int
    delta_count: int
    bullet_count: int
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/bands", response_model=List[BandConfigResponse])
async def get_bands() -> List[BandConfigResponse]:
    """Get similarity band configuration for UI legend.
    
    Returns the thresholds, labels, and colors for similarity bands.
    """
    return [
        BandConfigResponse(
            band=b.band.value,
            label=b.label,
            min_score=b.min_score,
            max_score=b.max_score,
            color=b.color,
        )
        for b in SIMILARITY_BANDS
    ]


@router.get("/policies", response_model=List[PolicySummaryResponse])
async def list_policies_endpoint(
    category: Optional[str] = Query(None, description="Filter by category"),
    scope: Optional[str] = Query(None, description="Filter by scope"),
    insurer: Optional[str] = Query(None, description="Filter by insurer"),
) -> List[PolicySummaryResponse]:
    """List all available policies.
    
    Returns policies that have been uploaded and processed.
    Optionally filter by category, scope, or insurer.
    """
    policies = list_policies(category=category, scope=scope, insurer=insurer)
    return [PolicySummaryResponse(**asdict(p)) for p in policies]


@router.get("/policies/{doc_id}/sections", response_model=List[SectionItemResponse])
async def get_sections_endpoint(
    doc_id: str,
    compare_to: Optional[str] = Query(None, description="Other policy doc_id to compare against"),
) -> List[SectionItemResponse]:
    """Get section tree for a policy with similarity indicators.
    
    If compare_to is provided, includes similarity scores and bands
    for each section based on clause alignments.
    """
    sections = get_policy_sections(doc_id, compare_to_doc_id=compare_to)
    return [SectionItemResponse(**asdict(s)) for s in sections]


@router.get("/policies/{doc_id}/sections/{section_id}/clauses", response_model=List[ClauseItemResponse])
async def get_section_clauses_endpoint(
    doc_id: str,
    section_id: str,
    compare_to: Optional[str] = Query(None, description="Other policy doc_id to compare against"),
) -> List[ClauseItemResponse]:
    """Get clauses within a section.
    
    The section_id is the section path joined by underscores (e.g., "cover_fire").
    Returns clauses with match status and delta counts if comparing.
    """
    # Convert section_id back to path
    section_path = [s.replace("_", " ").title() for s in section_id.split("_")]
    
    clauses = get_section_detail(doc_id, section_path, compare_to_doc_id=compare_to)
    return [ClauseItemResponse(**asdict(c)) for c in clauses]


@router.get("/clause-pair", response_model=ClausePairResponse)
async def get_clause_pair_endpoint(
    doc_id_a: str = Query(..., description="First policy doc_id"),
    block_id_a: str = Query(..., description="Block ID from first policy"),
    doc_id_b: str = Query(..., description="Second policy doc_id"),
) -> ClausePairResponse:
    """Get detailed drill-down view of a matched clause pair.
    
    Returns both clause texts, all detected deltas, evidence, and
    relevant summary bullets.
    """
    pair = get_clause_pair(doc_id_a, block_id_a, doc_id_b)
    if not pair:
        raise HTTPException(status_code=404, detail="Clause pair not found or not matched")
    return ClausePairResponse(**asdict(pair))


@router.get("/policies/{doc_id}/similarity-summary", response_model=List[SimilaritySummaryResponse])
async def get_similarity_summary_endpoint(
    doc_id: str,
    category: Optional[str] = Query(None, description="Filter by category"),
    scope: Optional[str] = Query(None, description="Filter by scope"),
) -> List[SimilaritySummaryResponse]:
    """Get similarity ranking of other policies compared to this one.
    
    Returns other policies sorted by overall similarity score,
    for the right-side similarity summary panel.
    """
    summary = get_similarity_summary(doc_id, category=category, scope=scope)
    return [SimilaritySummaryResponse(**asdict(s)) for s in summary]


@router.post("/upload", response_model=UploadResponse)
async def upload_policy_endpoint(
    file: UploadFile = File(...),
    name: str = Form(...),
    insurer: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    category: Optional[str] = Form(None),
    scope: Optional[str] = Form(None),
) -> UploadResponse:
    """Upload and process a new policy PDF.
    
    Runs Segments 1-4 (layout, definitions, classification, DNA)
    and registers the policy for listing/comparison.
    """
    if not file.filename or not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    
    try:
        doc_id = doc_id_from_pdf(contents)
        
        # Run Segments 1-4
        layout = run_document_layout(contents, doc_id=doc_id, source_uri=file.filename)
        run_definitions_agent(doc_id)
        run_clause_classification(doc_id)
        run_clause_dna_agent(doc_id)
        
        # Register metadata
        register_policy(
            doc_id,
            name,
            insurer=insurer,
            year=year,
            category=category,
            scope=scope,
            source_uri=file.filename,
        )
        
        # Count sections
        sections = set()
        for block in layout.blocks:
            if block.section_path:
                sections.add(tuple(block.section_path))
        
        return UploadResponse(
            doc_id=doc_id,
            name=name,
            block_count=len(layout.blocks),
            section_count=len(sections),
            message="Policy uploaded and processed successfully",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing policy: {str(e)}")


@router.post("/compare", response_model=CompareResponse)
async def compare_policies_endpoint(
    doc_id_a: str = Form(...),
    doc_id_b: str = Form(...),
) -> CompareResponse:
    """Run comparison between two already-uploaded policies.
    
    Runs Segments 5-7 (alignment, deltas, summarisation).
    Both policies must have been uploaded and processed first.
    """
    try:
        # Segment 5: Semantic Alignment
        alignment_result = run_semantic_alignment(doc_id_a, doc_id_b)
        
        # Segment 6: Delta Interpretation
        delta_result = run_delta_interpretation(doc_id_a, doc_id_b)
        
        # Segment 7: Narrative Summarisation
        summary_result = run_narrative_summarisation(doc_id_a, doc_id_b)
        
        return CompareResponse(
            doc_id_a=doc_id_a,
            doc_id_b=doc_id_b,
            alignment_count=len(alignment_result.alignments),
            delta_count=len(delta_result.deltas),
            bullet_count=len(summary_result.bullets),
            message="Comparison completed successfully",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error comparing policies: {str(e)}")


@router.get("/policies/{doc_id}/summary")
async def get_policy_summary_bullets(
    doc_id: str,
    compare_to: str = Query(..., description="Other policy doc_id"),
) -> Dict[str, Any]:
    """Get narrative summary bullets for a policy comparison.
    
    Returns the human-readable summary from Segment 7.
    """
    from ucc.storage.summary_store import SummaryStore
    
    store = SummaryStore()
    summary = store.get_summary(doc_id, compare_to)
    
    if not summary:
        raise HTTPException(status_code=404, detail="No summary found for this comparison")
    
    return {
        "doc_id_a": summary.doc_id_a,
        "doc_id_b": summary.doc_id_b,
        "bullets": [b.to_dict() for b in summary.bullets],
        "counts": summary.counts.to_dict(),
        "confidence": summary.confidence,
        "generated_at": summary.generated_at,
    }
