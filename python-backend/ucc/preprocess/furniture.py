"""Furniture removal utilities for PDF blocks."""

from __future__ import annotations

from collections import defaultdict
from typing import List, Sequence

try:  # pragma: no cover - optional dependency
    import regex as re
except ModuleNotFoundError:  # pragma: no cover - test environment fallback
    import re  # type: ignore

from ..config_loader import load_config
from ..io.pdf_blocks import Block


FURNITURE_REGEX = re.compile(
    r"""
    (?:^\s*(page\s*\d+|\d+\s*/\s*\d+)\s*$)  # page numbers
    |(?:abn|acn|afsl)                             # registration numbers
    |(?:contact\s+us|call\s+\d{3,})             # contact details
    |(?:https?://|www\.)                         # URLs
    |(?:copyright|\u00a9)                        # copyright symbols
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _normalise(text: str) -> str:
    text = text.lower()
    try:
        text = re.sub(r"[\d\p{P}\s]+", "", text)
    except re.error:  # pragma: no cover - fallback when regex module missing
        text = re.sub(r"[\d\W_]+", "", text)
    return text


def dehyphenate(text: str) -> str:
    """Join hyphenated line endings deterministically."""

    return re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", text)


def remove_furniture(blocks: Sequence[Block]) -> List[Block]:
    """Filter out layout furniture based on deterministic rules."""

    if not blocks:
        return []

    cfg = load_config()
    layout = cfg.get("layout", {})
    top_bottom_pct = float(layout.get("top_bottom_margin_pct", 0.1))
    side_pct = float(layout.get("side_margin_pct", 0.05))
    repeat_pct = float(layout.get("repeat_pages_pct", 0.5))

    # Compute repeated content across pages
    pages = {block.page_number for block in blocks}
    normalised_to_pages: defaultdict[str, set[int]] = defaultdict(set)
    for block in blocks:
        norm = _normalise(block.text)
        if norm:
            normalised_to_pages[norm].add(block.page_number)

    def is_repeated(block: Block) -> bool:
        norm = _normalise(block.text)
        if not norm:
            return False
        occurrences = normalised_to_pages[norm]
        if not occurrences:
            return False
        if len(occurrences) < 2:
            return False
        return len(occurrences) / max(len(pages), 1) >= repeat_pct

    filtered: List[Block] = []
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        text = dehyphenate(text)
        block.text = text

        # drop by region rules
        x0, y0, x1, y1 = block.bbox
        height = block.page_height or 1.0
        width = block.page_width or 1.0
        if height <= 0 or width <= 0:
            height = 1.0
            width = 1.0
        centre_y = (y0 + y1) / 2.0
        centre_x = (x0 + x1) / 2.0
        if centre_y <= height * top_bottom_pct:
            continue
        if centre_y >= height * (1 - top_bottom_pct):
            continue
        if centre_x <= width * side_pct:
            continue
        if centre_x >= width * (1 - side_pct):
            continue

        if FURNITURE_REGEX.search(text):
            continue
        if is_repeated(block):
            continue

        filtered.append(block)
    return filtered
