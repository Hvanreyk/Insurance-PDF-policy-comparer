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


@modern_router.post("/preprocess")
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
