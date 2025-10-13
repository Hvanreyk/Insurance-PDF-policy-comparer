"""Configuration loader for the Universal Clause Comparer."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent / "config.yml"


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """Load the YAML configuration for the comparer.

    The function caches the parsed YAML so repeated calls are inexpensive.
    """

    if not _CONFIG_PATH.exists():  # pragma: no cover - defensive
        raise FileNotFoundError(f"Config file not found at {_CONFIG_PATH}")
    with _CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data: Dict[str, Any] = yaml.safe_load(handle) or {}
    return data


def get_threshold(name: str, default: float = 0.0) -> float:
    """Convenience accessor for threshold values in the configuration."""

    thresholds = load_config().get("thresholds", {})
    value = thresholds.get(name, default)
    return float(value)
