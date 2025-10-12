# Universal Clause Comparer (UCC)

The Universal Clause Comparer (UCC) analyses two insurance policy documents at clause level and returns a structured diff highlighting new, removed, and modified provisions together with materiality and wording strictness signals.

## Quickstart

1. Ensure Python dependencies from `python-backend/requirements.txt` are installed.
2. Run the FastAPI server:

```bash
cd python-backend
uvicorn main:app --reload
```

3. Compare two policies with the API:

```bash
curl -F file_a=@tests/fixtures/policy_A.pdf \
     -F file_b=@tests/fixtures/policy_B.pdf \
     http://localhost:8000/api/compare-clauses | jq
```

4. Or use the CLI:

```bash
python -m ucc.cli compare tests/fixtures/policy_A.pdf tests/fixtures/policy_B.pdf --json comparison.json
```

The CLI and API both return the `UCCComparisonResult` schema defined in `python-backend/ucc/models_ucc.py`. An example payload is available at `examples/ucc_result.json`.

## Options

The `/api/compare-clauses` endpoint accepts an optional `options` form field containing JSON with the following keys:

- `embedder`: `"auto"` (default), `"local"`, or `"openai"`.
- `similarity_threshold`: Alignment threshold (default `0.72`).
- `return_token_diffs`: Set to `false` to omit token-level diffs.
- `max_candidates_per_clause`: Maximum similar clauses to retain (default `2`).

Environment variables:

- `UCC_EMBEDDER`: Overrides the default embedder backend.
- `OPENAI_API_KEY`: Required when `embedder` is set to `openai`.

## Limitations & Next Steps

- The parser focuses on text-based PDFs; scanned documents should be OCRed upstream.
- Alignment heuristics prioritise clause type and headings; extremely restructured documents may require manual review.
- Multi-policy comparisons and persistent storage are out of scope for this iteration.
