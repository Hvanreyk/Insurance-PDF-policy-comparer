import re
from io import BytesIO
from typing import Dict, Any, List, Optional

import pdfplumber
try:  # pragma: no cover - optional dependency
    import structlog

    logger = structlog.get_logger(__name__)
except Exception:  # pragma: no cover - fallback to stdlib logging
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from ucc.models_ucc import Clause
from ucc.normalization import RawClauseBlock, normalise_blocks

MAX_CLAUSES = 3000


def _split_page_into_blocks(text: str) -> List[str]:
    """Split page text into blocks separated by blank lines."""

    lines = (text or "").splitlines()
    blocks: List[str] = []
    current: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        if _is_heading(stripped) and current:
            blocks.append("\n".join(current).strip())
            current = [stripped]
        else:
            current.append(stripped)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def _is_heading(line: str) -> bool:
    """Determine whether a line is likely to be a heading."""

    if not line:
        return False
    stripped = line.strip()
    if len(stripped) <= 3:
        return False
    upper_ratio = sum(1 for c in stripped if c.isupper()) / max(len(stripped), 1)
    if upper_ratio > 0.65:
        return True
    if stripped.endswith(":"):
        return True
    if re.match(r"^(\d+(?:\.\d+)*)\.?(?:\s+.+)?$", stripped):
        return True
    tokens = stripped.split()
    if len(tokens) <= 4 and all(token[:1].isupper() for token in tokens if token):
        return True
    return False


def _update_section_stack(stack: List[str], heading: str) -> List[str]:
    """Update the current section stack with a new heading."""

    heading = re.sub(r"[:]+$", "", heading).strip()
    if not heading:
        return stack
    tokens = heading.split()
    numeric_prefix = tokens[0] if tokens else ""
    if re.match(r"\d+(\.\d+)*", numeric_prefix):
        depth = numeric_prefix.count(".") + 1
        cleaned_heading = " ".join(tokens[1:]) or heading
    else:
        depth = 1
        cleaned_heading = heading
    new_stack = stack[: depth - 1]
    new_stack.append(cleaned_heading)
    return new_stack


def _estimate_confidence(text: str) -> float:
    """Heuristic confidence based on token count and formatting."""

    token_count = len(text.split())
    if token_count >= 80:
        return 0.95
    if token_count >= 40:
        return 0.9
    if token_count >= 10:
        return 0.85
    return 0.7

def parse_policy_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Parse insurance policy PDF and extract structured data
    """
    policy_data = {
        "sums_insured": {},
        "premium": {},
        "raw_text": ""
    }

    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"

            policy_data["raw_text"] = full_text

            # Extract basic policy info
            policy_data["insurer"] = extract_value(full_text, ["AAI Limited", "Vero Insurance"])
            policy_data["insured"] = extract_value(full_text, ["Simeoni", "Simeoni and Co", "Simeoni & Co"])
            policy_data["policy_number"] = extract_pattern(full_text, r"(?:Policy|Reference)\s+Number[:\s]*([A-Z0-9\-\/]+)")

            # Extract period of insurance
            period = extract_period(full_text)
            if period:
                policy_data["period_of_insurance"] = period
                policy_data["policy_year"] = period["to"][:4]

            # Extract sums insured
            policy_data["sums_insured"]["contents"] = extract_currency(full_text, [
                r"Contents\s+\$?([\d,]+)",
                r"Contents Replacement Value[:\s]+\$?([\d,]+)"
            ])

            policy_data["sums_insured"]["theft_total"] = extract_currency(full_text, [
                r"Contents and Stock\s+\$?([\d,]+)",
                r"Theft[^\n]*Contents and Stock[^\n]*\$?([\d,]+)"
            ])

            policy_data["sums_insured"]["bi_turnover"] = extract_currency(full_text, [
                r"Turnover[:\s]+\$?([\d,]+)",
                r"Gross.*?Revenue[:\s]+\$?([\d,]+)"
            ])

            policy_data["sums_insured"]["public_liability"] = extract_currency(full_text, [
                r"Public Liability\s+\$?([\d,]+)",
                r"Limit of Liability[^\n]*Public Liability[^\n]*\$?([\d,]+)"
            ])

            policy_data["sums_insured"]["property_in_your_control"] = extract_currency(full_text, [
                r"Property in Your Custody or Control\s+\$?([\d,]+)",
                r"Property in.*?Control[:\s]+\$?([\d,]+)"
            ])

            # Extract premiums using table-aware parsing
            premiums = extract_premium_table(full_text, pdf.pages)
            policy_data["premium"] = premiums

            logger.info(f"Extracted premiums: {premiums}")

    except Exception as e:
        logger.error(f"Error parsing PDF: {str(e)}")
        raise

    return policy_data


def extract_value(text: str, patterns: list) -> Optional[str]:
    """Extract first matching value from text"""
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    return None


def extract_pattern(text: str, pattern: str) -> Optional[str]:
    """Extract value using regex pattern"""
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


def extract_currency(text: str, patterns: list) -> Optional[int]:
    """Extract currency value from text"""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).replace(",", "").replace("$", "")
            try:
                return int(value)
            except ValueError:
                continue
    return None


def extract_period(text: str) -> Optional[Dict[str, str]]:
    """Extract period of insurance"""
    pattern = r"Period\s+[Oo]f\s+[Ii]nsurance[:\s]*(\d{2})\s+(\w+)\s+(\d{4})\s+(?:to|To)\s+(?:\d+:\d+[ap]m\s+on\s+)?(\d{2})\s+(\w+)\s+(\d{4})"
    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        months = {
            "january": "01", "february": "02", "march": "03", "april": "04",
            "may": "05", "june": "06", "july": "07", "august": "08",
            "september": "09", "october": "10", "november": "11", "december": "12"
        }

        from_month = months.get(match.group(2).lower(), "01")
        to_month = months.get(match.group(5).lower(), "01")

        return {
            "from": f"{match.group(3)}-{from_month}-{match.group(1)}",
            "to": f"{match.group(6)}-{to_month}-{match.group(4)}"
        }
    return None


def extract_premium_table(text: str, pages: list) -> Dict[str, Optional[float]]:
    """
    Extract premium breakdown from table structure
    This is much more robust with pdfplumber's table extraction
    """
    result = {}

    # Try to extract table data directly
    for page in pages:
        tables = page.extract_tables()

        for table in tables:
            # Look for premium table (has headers like Base Premium, FSL/ESL, GST, Stamp Duty, Total)
            for i, row in enumerate(table):
                if not row:
                    continue

                row_text = " ".join([str(cell) if cell else "" for cell in row])

                # Check if this is the Total Premium row
                if "Total Premium" in row_text or "Total premium" in row_text:
                    logger.info(f"Found Total Premium row: {row}")

                    # Extract all numeric values from the row
                    values = []
                    for cell in row:
                        if cell:
                            # Extract number from cell
                            match = re.search(r"([\d,]+\.\d{2})", str(cell))
                            if match:
                                values.append(float(match.group(1).replace(",", "")))

                    # Assign values based on expected order: Base, FSL/ESL, GST, Stamp Duty, Total
                    if len(values) >= 5:
                        result["base"] = values[0]
                        result["fsl"] = values[1]
                        result["gst"] = values[2]
                        result["stamp"] = values[3]
                        result["total"] = values[4]
                        logger.info(f"Extracted from table: {result}")
                        return result

    # Fallback to regex extraction if table parsing didn't work
    logger.info("Table extraction failed, falling back to regex")

    # Try to find the Total Premium line with all values
    total_pattern = r"Total\s+Premium[^\n]*?([\d,]+\.\d{2})[^\n]*?([\d,]+\.\d{2})[^\n]*?([\d,]+\.\d{2})[^\n]*?([\d,]+\.\d{2})[^\n]*?([\d,]+\.\d{2})"
    match = re.search(total_pattern, text, re.IGNORECASE)

    if match:
        result["base"] = float(match.group(1).replace(",", ""))
        result["fsl"] = float(match.group(2).replace(",", ""))
        result["gst"] = float(match.group(3).replace(",", ""))
        result["stamp"] = float(match.group(4).replace(",", ""))
        result["total"] = float(match.group(5).replace(",", ""))
        logger.info(f"Extracted via regex: {result}")
        return result

    # Individual field extraction as last resort
    base_match = re.search(r"Base\s+Premium[^\d]*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if base_match:
        result["base"] = float(base_match.group(1).replace(",", ""))

    fsl_match = re.search(r"FSL[/\\]?ESL[^\d]*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if fsl_match:
        result["fsl"] = float(fsl_match.group(1).replace(",", ""))

    gst_match = re.search(r"GST[^\d]*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if gst_match:
        result["gst"] = float(gst_match.group(1).replace(",", ""))

    stamp_match = re.search(r"Stamp\s+Duty[^\d]*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if stamp_match:
        result["stamp"] = float(stamp_match.group(1).replace(",", ""))

    total_match = re.search(r"Total\s+Premium[^\d]*([\d,]+\.\d{2})", text, re.IGNORECASE | re.MULTILINE)
    if total_match:
        result["total"] = float(total_match.group(1).replace(",", ""))

    logger.info(f"Individual extraction result: {result}")
    return result


def parse_document_to_clauses(pdf_bytes: bytes) -> List[Clause]:
    """Parse a policy document into a list of Clause objects."""

    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            raw_blocks: List[RawClauseBlock] = []
            section_stack: List[str] = ["Document"]

            for page_index, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                for block_text in _split_page_into_blocks(page_text):
                    lines = [line.strip() for line in block_text.split("\n") if line.strip()]
                    if not lines:
                        continue

                    heading_candidate = lines[0]
                    is_heading = _is_heading(heading_candidate)
                    if is_heading and len(lines) == 1:
                        section_stack = _update_section_stack(section_stack, heading_candidate)
                        continue

                    title = heading_candidate if is_heading else None
                    if is_heading:
                        section_stack = _update_section_stack(section_stack, heading_candidate)
                        content_lines = lines[1:] or []
                    else:
                        content_lines = lines

                    content = " ".join(content_lines).strip()
                    if not content:
                        continue

                    block = RawClauseBlock(
                        text=content,
                        section_path=">".join(section_stack) or "Document",
                        title=title,
                        page_start=page_index,
                        page_end=page_index,
                        confidence=_estimate_confidence(content),
                    )
                    raw_blocks.append(block)

            if len(raw_blocks) > MAX_CLAUSES:
                raise ValueError(
                    f"document contains {len(raw_blocks)} clauses which exceeds limit of {MAX_CLAUSES}"
                )

            clauses = normalise_blocks(raw_blocks)
            return clauses
    except pdfplumber.pdf.PDFSyntaxError as exc:  # pragma: no cover - library specific
        logger.error("Failed to parse PDF syntax", error=str(exc))
        raise

    return []
