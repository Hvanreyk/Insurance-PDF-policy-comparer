"""Command line helpers for the Universal Clause Comparer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ucc.pipeline import ComparisonOptions, UCCComparer


def _load_file(path: Path) -> bytes:
    return path.read_bytes()


def _write_output(result: Any, path: Path | None) -> None:
    if not path:
        print(json.dumps(result, indent=2))
        return
    path.write_text(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Clause Comparer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare_parser = subparsers.add_parser("compare", help="Compare two policy documents")
    compare_parser.add_argument("file_a", type=Path, help="Expiring policy document")
    compare_parser.add_argument("file_b", type=Path, help="Quoted policy document")
    compare_parser.add_argument(
        "--json",
        dest="json_output",
        type=Path,
        help="Write the comparison result to a JSON file",
    )
    compare_parser.add_argument(
        "--embedder",
        choices=["auto", "local", "openai"],
        default="auto",
        help="Embedder backend to use",
    )
    compare_parser.add_argument(
        "--threshold",
        type=float,
        default=0.72,
        help="Similarity threshold for clause alignment",
    )

    args = parser.parse_args()

    if args.command == "compare":
        options = ComparisonOptions(
            embedder=args.embedder,
            similarity_threshold=args.threshold,
        )
        comparer = UCCComparer(options=options)
        result = comparer.compare(_load_file(args.file_a), _load_file(args.file_b))
        _write_output(result.model_dump(), args.json_output)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
