from typing import Dict, Any, Optional

def compare_policies(policy_a: Dict[str, Any], policy_b: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Compare two insurance policies and calculate deltas
    """
    result = {}

    # Compare sums insured
    sums_a = policy_a.get("sums_insured", {})
    sums_b = policy_b.get("sums_insured", {})

    if sums_a.get("contents") is not None or sums_b.get("contents") is not None:
        result["Contents"] = calculate_delta(
            sums_a.get("contents"),
            sums_b.get("contents")
        )

    if sums_a.get("theft_total") is not None or sums_b.get("theft_total") is not None:
        result["Theft (Contents & Stock)"] = calculate_delta(
            sums_a.get("theft_total"),
            sums_b.get("theft_total")
        )

    if sums_a.get("bi_turnover") is not None or sums_b.get("bi_turnover") is not None:
        result["Business Interruption (Turnover)"] = calculate_delta(
            sums_a.get("bi_turnover"),
            sums_b.get("bi_turnover")
        )

    if sums_a.get("public_liability") is not None or sums_b.get("public_liability") is not None:
        result["Public Liability"] = calculate_delta(
            sums_a.get("public_liability"),
            sums_b.get("public_liability")
        )

    if sums_a.get("property_in_your_control") is not None or sums_b.get("property_in_your_control") is not None:
        result["Property in Control"] = calculate_delta(
            sums_a.get("property_in_your_control"),
            sums_b.get("property_in_your_control")
        )

    # Compare premium components
    premium_a = policy_a.get("premium", {})
    premium_b = policy_b.get("premium", {})

    if premium_a.get("base") is not None or premium_b.get("base") is not None:
        result["Premium (Base)"] = calculate_delta(
            premium_a.get("base"),
            premium_b.get("base")
        )

    if premium_a.get("fsl") is not None or premium_b.get("fsl") is not None:
        result["Premium (FSL/ESL)"] = calculate_delta(
            premium_a.get("fsl"),
            premium_b.get("fsl")
        )

    if premium_a.get("gst") is not None or premium_b.get("gst") is not None:
        result["Premium (GST)"] = calculate_delta(
            premium_a.get("gst"),
            premium_b.get("gst")
        )

    if premium_a.get("stamp") is not None or premium_b.get("stamp") is not None:
        result["Premium (Stamp Duty)"] = calculate_delta(
            premium_a.get("stamp"),
            premium_b.get("stamp")
        )

    if premium_a.get("total") is not None or premium_b.get("total") is not None:
        result["Total Premium"] = calculate_delta(
            premium_a.get("total"),
            premium_b.get("total")
        )

    return result


def calculate_delta(a: Optional[float], b: Optional[float]) -> Dict[str, Any]:
    """
    Calculate the delta between two values
    """
    if a is None or b is None:
        return {
            "a": a,
            "b": b,
            "delta_abs": None,
            "delta_pct": None
        }

    delta_abs = b - a
    delta_pct = ((b - a) / a * 100) if a != 0 else None

    return {
        "a": a,
        "b": b,
        "delta_abs": delta_abs,
        "delta_pct": delta_pct
    }
