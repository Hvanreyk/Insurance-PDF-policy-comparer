"""TOC parsing and section path assignment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

try:  # pragma: no cover - optional dependency
    import regex as re
except ModuleNotFoundError:  # pragma: no cover - test environment fallback
    import re  # type: ignore

from ..config_loader import load_config
from ..io.pdf_blocks import Block


HEADING_PATTERN = re.compile(r"^(?:\d+(?:\.\d+)*)?\s*[A-Z][A-Za-z0-9 ,/&-]{0,80}$")
TOC_LINE_PATTERN = re.compile(r"^.+\s+\d{1,3}$")


@dataclass
class SectionContext:
    level: int
    title: str
    is_admin: bool


class Sectioniser:
    """Assigns section paths to blocks using light-weight heuristics."""

    def __init__(self, whitelist: Sequence[str], blacklist: Sequence[str]) -> None:
        self.whitelist = [w.lower() for w in whitelist]
        self.blacklist = [b.lower() for b in blacklist]
        self.stack: List[SectionContext] = []
        self.detected_toc_pages: set[int] = set()

    def _is_toc_line(self, block: Block) -> bool:
        text = block.text.strip()
        if len(text.split()) < 2:
            return False
        return bool(TOC_LINE_PATTERN.match(text))

    def detect_toc_pages(self, blocks: Sequence[Block]) -> None:
        candidate_counts: Dict[int, int] = {}
        for block in blocks:
            if self._is_toc_line(block):
                candidate_counts[block.page_number] = candidate_counts.get(block.page_number, 0) + 1
        for page, count in candidate_counts.items():
            if count >= 6:
                self.detected_toc_pages.add(page)

    def _heading_level(self, text: str) -> int | None:
        numbered = re.match(r"^(\d+(?:\.\d+)*)", text)
        if numbered:
            return numbered.group(1).count(".") + 1
        if text.isupper():
            return 1
        if len(text.split()) <= 6:
            return 1
        return None

    def _is_admin_section(self, title: str) -> bool:
        lower = title.lower()
        if any(word in lower for word in self.whitelist):
            return False
        if any(word in lower for word in self.blacklist):
            return True
        return False

    def _push_heading(self, level: int, title: str) -> None:
        while self.stack and self.stack[-1].level >= level:
            self.stack.pop()
        is_admin = self._is_admin_section(title)
        self.stack.append(SectionContext(level=level, title=title, is_admin=is_admin))

    def assign(self, blocks: Sequence[Block]) -> None:
        self.detect_toc_pages(blocks)
        for block in blocks:
            block.section_path = []  # type: ignore[attr-defined]
            block.is_admin = False  # type: ignore[attr-defined]

        for block in blocks:
            if block.page_number in self.detected_toc_pages:
                block.section_path = []  # type: ignore[attr-defined]
                block.is_admin = True  # type: ignore[attr-defined]
                continue

            text = block.text.strip()
            if not text:
                continue

            if HEADING_PATTERN.match(text):
                level = self._heading_level(text) or 1
                self._push_heading(level, text)
                block.section_path = [ctx.title for ctx in self.stack]  # type: ignore[attr-defined]
                block.is_admin = any(ctx.is_admin for ctx in self.stack)  # type: ignore[attr-defined]
                continue

            block.section_path = [ctx.title for ctx in self.stack]  # type: ignore[attr-defined]
            block.is_admin = any(ctx.is_admin for ctx in self.stack)  # type: ignore[attr-defined]


def apply_sections(blocks: Sequence[Block]) -> None:
    config = load_config()
    whitelist = config.get("whitelist_headings", [])
    blacklist = config.get("admin_blacklist", [])
    sectioniser = Sectioniser(whitelist, blacklist)
    sectioniser.assign(blocks)
