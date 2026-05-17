"""
Support/Resistance level calculator from Options data.

This module calculates support and resistance levels from:
- Options walls (OI concentrations)
- Max Pain strike
- High volume strikes
- Whale activity concentrations

The S/R levels are used for:
- Stop loss placement
- Take profit targets
- Entry zone refinement
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from binance_signal_generator.models import (
    OptionsChain,
    WallAnalysis,
    WhaleAnalysis,
    SRLevel,
    SRLevels,
    SignalDirection,
)
from binance_signal_generator.analysis.wall_detector import WallDetector, WallDetectorConfig
from binance_signal_generator.analysis.max_pain import MaxPainCalculator, MaxPainConfig
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SRLevelConfig:
    """Configuration for S/R level calculation."""
    # Number of levels per side
    max_support_levels: int = 3
    max_resistance_levels: int = 3
    
    # Minimum distance between levels (%)
    min_level_distance_pct: float = 1.0
    
    # Weight factors
    wall_weight: float = 0.50
    max_pain_weight: float = 0.30
    volume_weight: float = 0.20
    
    # Default SL/TP distances
    default_sl_distance_pct: float = 2.0
    default_tp_ratios: List[float] = None  # RR ratios for TP
    
    def __post_init__(self):
        if self.default_tp_ratios is None:
            self.default_tp_ratios = [1.5, 3.0, 5.0]


class SRLevelCalculator:
    """
    Calculates support and resistance levels from Options data.
    
    Level Sources:
    1. Put walls -> Support levels
    2. Call walls -> Resistance levels
    3. Max Pain -> Magnetic level
    4. High volume strikes -> Additional levels
    
    Level Usage:
    - Support levels -> Stop loss for longs, TP for shorts
    - Resistance levels -> Stop loss for shorts, TP for longs
    - Max Pain -> Entry refinement
    
    Attributes:
        config: S/R level configuration
        wall_detector: Wall detector instance
        max_pain_calc: Max Pain calculator
    """
    
    def __init__(self, config: Optional[SRLevelConfig] = None):
        """
        Initialize S/R level calculator.
        
        Args:
            config: S/R level configuration
        """
        self.config = config or SRLevelConfig()
        self.wall_detector = WallDetector(WallDetectorConfig())
        self.max_pain_calc = MaxPainCalculator(MaxPainConfig())
        
        logger.info("S/R level calculator initialized")
    
    def calculate(
        self,
        chain: OptionsChain,
        whale_analysis: Optional[WhaleAnalysis] = None,
    ) -> SRLevels:
        """
        Calculate support and resistance levels.
        
        Args:
            chain: Options chain data
            whale_analysis: Optional whale analysis for additional levels
            
        Returns:
            SRLevels with all calculated levels
        """
        # Detect walls
        wall_analysis = self.wall_detector.detect(chain)
        
        # Calculate max pain
        max_pain = self.max_pain_calc.calculate(chain)
        
        # Build support levels from put walls
        support_levels = self._build_support_levels(
            wall_analysis=wall_analysis,
            max_pain=max_pain.max_pain_strike,
            spot_price=chain.spot_price,
        )
        
        # Build resistance levels from call walls
        resistance_levels = self._build_resistance_levels(
            wall_analysis=wall_analysis,
            max_pain=max_pain.max_pain_strike,
            spot_price=chain.spot_price,
        )
        
        # Filter and deduplicate
        support_levels = self._filter_levels(support_levels, chain.spot_price, "BELOW")
        resistance_levels = self._filter_levels(resistance_levels, chain.spot_price, "ABOVE")
        
        return SRLevels(
            support=support_levels[:self.config.max_support_levels],
            resistance=resistance_levels[:self.config.max_resistance_levels],
            stop_loss=None,  # Set separately based on signal direction
            take_profit_levels=[],
            risk_reward_ratio=0.0,
            stop_distance_pct=0.0,
            avg_tp_distance_pct=0.0,
        )
    
    def _build_support_levels(
        self,
        wall_analysis: WallAnalysis,
        max_pain: float,
        spot_price: float,
    ) -> List[SRLevel]:
        """
        Build support levels from put walls.
        
        Args:
            wall_analysis: Wall analysis
            max_pain: Max pain strike
            spot_price: Current spot price
            
        Returns:
            List of support SRLevels
        """
        levels = []
        
        # Add put walls as support
        for i, wall in enumerate(wall_analysis.put_walls[:self.config.max_support_levels]):
            level = SRLevel(
                level=i + 1,
                price=wall.strike,
                type="PUT_WALL",
                strength=wall.strength_score,
                confidence=min(wall.oi_percentage * 5, 1.0),
                source="wall_detector",
                wall_data={
                    "oi": wall.open_interest,
                    "concentration": wall.oi_percentage,
                    "is_major": wall.is_major_wall,
                },
            )
            levels.append(level)
        
        # Add max pain as potential support if below spot
        if max_pain < spot_price:
            # Check if not already included
            existing_prices = [l.price for l in levels]
            if max_pain not in existing_prices:
                mp_distance = (spot_price - max_pain) / spot_price
                levels.append(SRLevel(
                    level=len(levels) + 1,
                    price=max_pain,
                    type="MAX_PAIN",
                    strength=0.6,
                    confidence=0.5,
                    source="max_pain",
                ))
        
        # Sort by price (descending for support - closest first)
        levels.sort(key=lambda l: l.price, reverse=True)
        
        # Reassign levels
        for i, level in enumerate(levels):
            level.level = i + 1
        
        return levels
    
    def _build_resistance_levels(
        self,
        wall_analysis: WallAnalysis,
        max_pain: float,
        spot_price: float,
    ) -> List[SRLevel]:
        """
        Build resistance levels from call walls.
        
        Args:
            wall_analysis: Wall analysis
            max_pain: Max pain strike
            spot_price: Current spot price
            
        Returns:
            List of resistance SRLevels
        """
        levels = []
        
        # Add call walls as resistance
        for i, wall in enumerate(wall_analysis.call_walls[:self.config.max_resistance_levels]):
            level = SRLevel(
                level=i + 1,
                price=wall.strike,
                type="CALL_WALL",
                strength=wall.strength_score,
                confidence=min(wall.oi_percentage * 5, 1.0),
                source="wall_detector",
                wall_data={
                    "oi": wall.open_interest,
                    "concentration": wall.oi_percentage,
                    "is_major": wall.is_major_wall,
                },
            )
            levels.append(level)
        
        # Add max pain as potential resistance if above spot
        if max_pain > spot_price:
            existing_prices = [l.price for l in levels]
            if max_pain not in existing_prices:
                levels.append(SRLevel(
                    level=len(levels) + 1,
                    price=max_pain,
                    type="MAX_PAIN",
                    strength=0.6,
                    confidence=0.5,
                    source="max_pain",
                ))
        
        # Sort by price (ascending for resistance - closest first)
        levels.sort(key=lambda l: l.price)
        
        # Reassign levels
        for i, level in enumerate(levels):
            level.level = i + 1
        
        return levels
    
    def _filter_levels(
        self,
        levels: List[SRLevel],
        spot_price: float,
        side: str,
    ) -> List[SRLevel]:
        """
        Filter and deduplicate levels.
        
        Args:
            levels: List of levels
            spot_price: Current spot price
            side: "ABOVE" or "BELOW" spot
            
        Returns:
            Filtered list
        """
        filtered = []
        min_distance = spot_price * (self.config.min_level_distance_pct / 100)
        
        for level in levels:
            # Check side
            if side == "ABOVE" and level.price <= spot_price:
                continue
            if side == "BELOW" and level.price >= spot_price:
                continue
            
            # Check minimum distance from existing levels
            is_close = False
            for existing in filtered:
                if abs(level.price - existing.price) < min_distance:
                    is_close = True
                    break
            
            if not is_close:
                filtered.append(level)
        
        return filtered
