"""Similarity band configuration for UI display.

Single source of truth for similarity thresholds and band labels.
Based on Raindrop-style UI requirements.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


class SimilarityBand(str, Enum):
    """Similarity bands for visual categorization."""
    
    VERY_SIMILAR = "very_similar"
    HIGHLY_SIMILAR = "highly_similar"
    SOMEWHAT_SIMILAR = "somewhat_similar"
    SOMEWHAT_DIFFERENT = "somewhat_different"
    MODERATELY_DIFFERENT = "moderately_different"
    VERY_DIFFERENT = "very_different"


@dataclass(frozen=True)
class BandConfig:
    """Configuration for a similarity band."""
    
    band: SimilarityBand
    label: str
    min_score: float  # inclusive
    max_score: float  # exclusive (except for top band)
    color: str  # CSS color for frontend


# Similarity band thresholds (single source of truth)
# Ordered from highest to lowest similarity
SIMILARITY_BANDS: List[BandConfig] = [
    BandConfig(
        band=SimilarityBand.VERY_SIMILAR,
        label="Very Similar",
        min_score=0.90,
        max_score=1.01,  # Slightly above 1.0 to include it
        color="#E86A33",  # Dark orange
    ),
    BandConfig(
        band=SimilarityBand.HIGHLY_SIMILAR,
        label="Highly Similar",
        min_score=0.75,
        max_score=0.90,
        color="#F39C6B",  # Orange
    ),
    BandConfig(
        band=SimilarityBand.SOMEWHAT_SIMILAR,
        label="Somewhat Similar",
        min_score=0.50,
        max_score=0.75,
        color="#F9C49A",  # Light orange
    ),
    BandConfig(
        band=SimilarityBand.SOMEWHAT_DIFFERENT,
        label="Somewhat Different",
        min_score=0.35,
        max_score=0.50,
        color="#B8D4E3",  # Light blue
    ),
    BandConfig(
        band=SimilarityBand.MODERATELY_DIFFERENT,
        label="Moderately Different",
        min_score=0.20,
        max_score=0.35,
        color="#6BA3BE",  # Medium blue
    ),
    BandConfig(
        band=SimilarityBand.VERY_DIFFERENT,
        label="Very Different",
        min_score=0.0,
        max_score=0.20,
        color="#2D5F74",  # Dark blue
    ),
]


def get_similarity_band(score: float) -> BandConfig:
    """Get the band configuration for a similarity score.
    
    Args:
        score: Similarity score between 0.0 and 1.0
        
    Returns:
        BandConfig for the appropriate band.
    """
    # Clamp score to valid range
    score = max(0.0, min(1.0, score))
    
    for band_config in SIMILARITY_BANDS:
        if band_config.min_score <= score < band_config.max_score:
            return band_config
    
    # Fallback (shouldn't happen with proper configuration)
    return SIMILARITY_BANDS[-1]


def get_band_distribution(scores: List[float]) -> dict[str, int]:
    """Calculate distribution of scores across bands.
    
    Args:
        scores: List of similarity scores
        
    Returns:
        Dict mapping band labels to counts.
    """
    distribution = {band.label: 0 for band in SIMILARITY_BANDS}
    
    for score in scores:
        band = get_similarity_band(score)
        distribution[band.label] += 1
    
    return distribution
