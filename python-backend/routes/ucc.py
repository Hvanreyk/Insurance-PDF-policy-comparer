"""FastAPI router exposing the Universal Clause Comparer."""

from __future__ import annotations

import json
from typing import Dict, List, Optional
from uuid import uuid4

try:  # pragma: no cover - optional dependency
    import structlog

    logger = structlog.get_logger(__name__)
except Exception:  # pragma: no cover - fallback to stdlib logging
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ucc.models_ucc import UCCComparisonResult
from ucc.pipeline import ComparisonOptions, UCCComparer
from ucc.service import align_policy_blocks, diff_policy_facets, preprocess_policy
from tasks.comparison_chain import run_comparison_job
from ucc.delivery.service import DeliveryService

router = APIRouter()
legacy_router = APIRouter(prefix="/api", tags=["universal-clause-comparer"])
modern_router = APIRouter(prefix="/ucc", tags=["universal-clause-comparer"])


class BlockPayload(BaseModel):
    id: str
    text: str
    clause_type: str = Field(default="UNKNOWN")
    concepts: List[str] = Field(default_factory=list)
    section_path: List[str] = Field(default_factory=list)
    is_admin: bool = False
    ors: float | None = None


class AlignRequest(BaseModel):
    blocks_a: List[BlockPayload]
    blocks_b: List[BlockPayload]


class AlignResponse(BaseModel):
    alignments: List[Dict[str, object]]


class DiffMatch(BaseModel):
    clause_type: str
    block_id_a: str
    block_id_b: str


class DiffRequest(BaseModel):
    matches: List[DiffMatch]
    blocks_a: List[BlockPayload]
    blocks_b: List[BlockPayload]


def _parse_options(options_raw: Optional[str]) -> ComparisonOptions:
    if not options_raw:
        return ComparisonOptions()
    try:
        data = json.loads(options_raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - validation path
        raise HTTPException(status_code=400, detail=f"Invalid options payload: {exc}")

    options = ComparisonOptions()
    if "embedder" in data:
        options.embedder = str(data["embedder"])
    if "similarity_threshold" in data:
        options.similarity_threshold = float(data["similarity_threshold"])
    if "return_token_diffs" in data:
        options.return_token_diffs = bool(data["return_token_diffs"])
    if "max_candidates_per_clause" in data:
        options.max_candidates_per_clause = int(data["max_candidates_per_clause"])
    return options


@legacy_router.post("/compare-clauses", response_model=UCCComparisonResult)
async def compare_clauses(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
    options: Optional[str] = Form(None),
) -> UCCComparisonResult:
    trace_id = str(uuid4())
    supports_structlog = hasattr(logger, "bind")
    log = logger.bind(trace_id=trace_id, endpoint="compare_clauses") if supports_structlog else logger

    try:
        contents_a = await file_a.read()
        contents_b = await file_b.read()
        if not contents_a:
            raise HTTPException(status_code=400, detail="file_a is empty")
        if not contents_b:
            raise HTTPException(status_code=400, detail="file_b is empty")

        comparer = UCCComparer(options=_parse_options(options))
        result = comparer.compare(contents_a, contents_b)
        return result
    except HTTPException:
        if hasattr(log, "warning"):
            if supports_structlog:
                log.warning("request rejected", reason="validation_error")
            else:
                log.warning("request rejected: validation_error")
        raise
    except ValueError as exc:
        if hasattr(log, "warning"):
            if supports_structlog:
                log.warning("comparison failed", error=str(exc))
            else:
                log.warning("comparison failed: %s", str(exc))
        raise HTTPException(status_code=422, detail={"message": str(exc), "trace_id": trace_id})
    except Exception as exc:  # pragma: no cover - defensive programming
        if hasattr(log, "error"):
            if supports_structlog:
                log.error("comparison failed", error=str(exc))
            else:
                log.error("comparison failed: %s", str(exc))
        raise HTTPException(status_code=500, detail={"message": "Internal error", "trace_id": trace_id})


@modern_router.post("/compare", response_model=UCCComparisonResult)
async def compare_endpoint(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
    options: Optional[str] = Form(None),
    use_segments: bool = Form(True, description="Use new 7-segment pipeline (recommended)"),
) -> UCCComparisonResult:
    """Compare two policies using the improved 7-segment pipeline.
    
    This endpoint uses the new async infrastructure with better comparison results:
    - Segment 1: Document layout analysis (block extraction)
    - Segment 2: Definitions extraction & expansion
    - Segment 3: Clause classification
    - Segment 4: Clause DNA extraction (structural analysis)
    - Segment 5: Semantic alignment (like-to-like matching)
    - Segment 6: Delta interpretation (change detection)
    - Segment 7: Narrative summarisation (human-readable summary)
    
    For immediate results (no async), set use_segments=false to use legacy pipeline.
    For production, use /jobs/compare endpoint for better scalability.
    
    Args:
        file_a: First policy PDF
        file_b: Second policy PDF
        options: Optional JSON config (similarity_threshold, etc)
        use_segments: Use new 7-segment pipeline (default: true)
    
    Returns:
        UCCComparisonResult with improved structure
    """
    trace_id = str(uuid4())
    supports_structlog = hasattr(logger, "bind")
    log = logger.bind(trace_id=trace_id, endpoint="compare_v2") if supports_structlog else logger

    try:
        contents_a = await file_a.read()
        contents_b = await file_b.read()
        if not contents_a:
            raise HTTPException(status_code=400, detail="file_a is empty")
        if not contents_b:
            raise HTTPException(status_code=400, detail="file_b is empty")

        # Use new 7-segment pipeline (blocking call for immediate results)
        if use_segments:
            if hasattr(log, "info"):
                if supports_structlog:
                    log.info("using 7-segment pipeline", trace_id=trace_id)
                else:
                    log.info(f"Using 7-segment pipeline (trace: {trace_id})")
            
            # Submit job and wait for completion (blocking)
            job_id, celery_task_id = run_comparison_job(
                pdf_bytes_a=contents_a,
                pdf_bytes_b=contents_b,
                file_name_a=file_a.filename,
                file_name_b=file_b.filename,
            )
            
            # Wait for job to complete synchronously (for API compatibility)
            from celery.result import AsyncResult
            import time
            
            result_obj = AsyncResult(celery_task_id)
            max_wait = 600  # 10 minutes max
            start_time = time.time()
            
            while not result_obj.ready() and (time.time() - start_time) < max_wait:
                time.sleep(0.5)
            
            if not result_obj.ready():
                raise HTTPException(
                    status_code=504,
                    detail="Comparison took too long to complete"
                )
            
            if result_obj.failed():
                raise HTTPException(
                    status_code=500,
                    detail=f"Comparison failed: {result_obj.info}"
                )
            
            # Get result from DeliveryService
            delivery = DeliveryService()
            from ucc.agents.document_layout import doc_id_from_pdf
            doc_id_a = doc_id_from_pdf(contents_a)
            doc_id_b = doc_id_from_pdf(contents_b)
            
            result_dict = delivery.get_comparison_result(doc_id_a, doc_id_b)
            return UCCComparisonResult(**result_dict)
        
        else:
            # Legacy pipeline (old code path)
            if hasattr(log, "info"):
                if supports_structlog:
                    log.info("using legacy pipeline", trace_id=trace_id)
                else:
                    log.info(f"Using legacy pipeline (trace: {trace_id})")
            
            return await compare_clauses(file_a=file_a, file_b=file_b, options=options)
            
    except HTTPException:
        if hasattr(log, "warning"):
            if supports_structlog:
                log.warning("request rejected", reason="validation_error")
            else:
                log.warning("request rejected: validation_error")
        raise
    except ValueError as exc:
        if hasattr(log, "warning"):
            if supports_structlog:
                log.warning("comparison failed", error=str(exc))
            else:
                log.warning("comparison failed: %s", str(exc))
        raise HTTPException(status_code=422, detail={"message": str(exc), "trace_id": trace_id})
    except Exception as exc:  # pragma: no cover - defensive programming
        if hasattr(log, "error"):
            if supports_structlog:
                log.error("comparison failed", error=str(exc))
            else:
                log.error("comparison failed: %s", str(exc))
        raise HTTPException(status_code=500, detail={"message": "Internal error", "trace_id": trace_id})


@modern_router.post("/compare-advanced", response_model=UCCComparisonResult)
async def compare_advanced_endpoint(
    file_a: UploadFile = File(..., description="First policy PDF"),
    file_b: UploadFile = File(..., description="Second policy PDF"),
    mode: str = Form("segments", description="'segments' (new 7-segment) or 'legacy' (old)"),
) -> UCCComparisonResult:
    """Advanced comparison endpoint with explicit mode selection.
    
    **New 7-Segment Pipeline (mode='segments') - RECOMMENDED:**
    
    Uses the improved infrastructure with better accuracy:
    - Segment 1: Document Layout Analysis
      * Block-level extraction from PDFs
      * Section hierarchy detection
      * Page-aware block ordering
    
    - Segment 2: Definitions Extraction
      * Find and index defined terms
      * Expand blocks with definition context
      * Build dependency map
    
    - Segment 3: Clause Classification
      * Classify each block (EXCLUSION, CONDITION, LIMIT, etc)
      * Admin vs operational filtering
    
    - Segment 4: Clause DNA Extraction
      * Polarity detection (GRANT/REMOVE)
      * Strictness analysis (ABSOLUTE/CONDITIONAL/DISCRETIONARY)
      * Entity extraction
      * Carve-out identification
      * Burden shift detection
    
    - Segment 5: Semantic Alignment
      * Like-to-like clause matching using DNA + semantics
      * Context-aware similarity (not just text distance)
      * Confidence scoring
    
    - Segment 6: Delta Interpretation
      * Structured change detection
      * Scope changes, strictness shifts, numeric deltas
      * Burden analysis
    
    - Segment 7: Narrative Summarisation
      * Human-readable summary bullets
      * Evidence references
      * Severity/materiality scoring
    
    **Legacy Pipeline (mode='legacy'):**
    
    Uses simple embedding-based matching:
    - Basic token-level differences
    - No structural understanding
    - Faster but less accurate
    
    **Comparison:**
    
    | Feature | Segments | Legacy |
    |---------|----------|--------|
    | Accuracy | ⭐⭐⭐⭐⭐ | ⭐⭐ |
    | Speed | Medium | Fast |
    | Structural analysis | Yes | No |
    | DNA features | Yes | No |
    | Confidence scoring | Yes | No |
    | Evidence references | Yes | No |
    | Scalable | Yes (async) | Limited |
    
    For production use, use /jobs/compare for non-blocking execution with progress tracking.
    """
    if mode not in ("segments", "legacy"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode}'. Use 'segments' or 'legacy'"
        )
    
    return await compare_endpoint(
        file_a=file_a,
        file_b=file_b,
        options=None,
        use_segments=(mode == "segments"),
    )


@modern_router.get("/compare-info")
async def compare_info() -> Dict[str, object]:
    """Get information about comparison modes and recommendations.
    
    Returns detailed information about the different comparison pipelines
    and recommendations for when to use each.
    """
    return {
        "modes": {
            "segments": {
                "name": "New 7-Segment Pipeline",
                "recommended": True,
                "accuracy": 5,
                "speed": 3,
                "features": [
                    "Structural analysis",
                    "DNA extraction",
                    "Context-aware alignment",
                    "Confidence scoring",
                    "Evidence references",
                    "Severity analysis",
                ],
                "use_cases": [
                    "High-accuracy comparisons",
                    "Insurance policy analysis",
                    "Legal document comparison",
                    "Regulatory compliance checks",
                ],
            },
            "legacy": {
                "name": "Legacy Embedding Pipeline",
                "recommended": False,
                "accuracy": 2,
                "speed": 5,
                "features": [
                    "Token-level diff",
                    "Embedding similarity",
                    "Basic status classification",
                ],
                "use_cases": [
                    "Quick checks",
                    "Testing",
                    "Non-critical comparisons",
                ],
            },
        },
        "recommended_flows": {
            "immediate_results": {
                "endpoint": "POST /ucc/compare",
                "params": {"use_segments": True},
                "description": "Blocks until complete (up to 10 minutes)",
            },
            "scalable_production": {
                "endpoint": "POST /jobs/compare",
                "description": "Async with WebSocket progress tracking",
                "benefits": [
                    "Non-blocking",
                    "Real-time progress",
                    "Better resource utilization",
                    "Horizontal scaling",
                ],
            },
        },
        "segments_pipeline": [
            {
                "number": 1,
                "name": "Document Layout",
                "purpose": "Extract and organize document structure",
                "outputs": ["blocks", "sections", "page_mapping"],
            },
            {
                "number": 2,
                "name": "Definitions",
                "purpose": "Find and index defined terms",
                "outputs": ["definitions", "expansions", "dependencies"],
            },
            {
                "number": 3,
                "name": "Classification",
                "purpose": "Classify clause types",
                "outputs": ["clause_types", "confidence_scores"],
            },
            {
                "number": 4,
                "name": "Clause DNA",
                "purpose": "Extract structural DNA",
                "outputs": ["dna_features", "polarity", "strictness"],
            },
            {
                "number": 5,
                "name": "Semantic Alignment",
                "purpose": "Match clauses across documents",
                "outputs": ["alignments", "similarity_scores"],
            },
            {
                "number": 6,
                "name": "Delta Interpretation",
                "purpose": "Detect and interpret changes",
                "outputs": ["deltas", "change_types", "severity"],
            },
            {
                "number": 7,
                "name": "Narrative Summary",
                "purpose": "Generate human-readable summary",
                "outputs": ["summary_bullets", "evidence", "materiality"],
            },
        ],
    }

async def preprocess_endpoint(file: UploadFile = File(...)) -> Dict[str, List[Dict[str, object]]]:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    blocks = preprocess_policy(contents)
    return {"blocks": blocks}


@modern_router.post("/align", response_model=AlignResponse)
async def align_endpoint(request: AlignRequest) -> AlignResponse:
    alignments = align_policy_blocks(
        [block.dict() for block in request.blocks_a],
        [block.dict() for block in request.blocks_b],
    )
    return AlignResponse(alignments=alignments)


@modern_router.post("/diff")
async def diff_endpoint(request: DiffRequest) -> Dict[str, List[Dict[str, object]]]:
    lookup_a = {block.id: block.dict() for block in request.blocks_a}
    lookup_b = {block.id: block.dict() for block in request.blocks_b}
    diffs = diff_policy_facets(
        [match.dict() for match in request.matches],
        lookup_a,
        lookup_b,
    )
    return {"diffs": diffs}


router.include_router(legacy_router)
router.include_router(modern_router)
