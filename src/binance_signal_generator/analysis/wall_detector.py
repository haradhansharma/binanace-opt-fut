"""
Wall detector for identifying Options walls (large OI concentrations).

This module detects Options walls - strike prices with significant
Open Interest concentrations that act as support or resistance levels.

Wall Types:
- Call Wall: Strike with large call OI above spot (resistance)
- Put Wall: Strike with large put OI below spot (support)
- Max Pain: Strike where option holders have max loss
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    OptionWall,
    WallAnalysis,
)
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WallDetectorConfig:
    """Configuration for wall detection."""
    # OI concentration threshold
    # ANALYSIS: With ~18K total OI across 70+ strikes for BTC, OI is very distributed.
    # Max single-strike OI observed: ~121 contracts (0.67% of total)
    # Previous threshold of 2% (361 contracts) was too high - no walls detected.
    # New threshold: 0.5% allows strikes with ~90+ contracts to be detected.
    min_oi_concentration: float = 0.005   # 0.5% of total OI (lowered from 2%)

    # Major wall threshold - also lowered proportionally
    major_wall_concentration: float = 0.02  # 2% of total OI (lowered from 10%)

    # Distance from spot (in %)
    max_wall_distance: float = 15.0  # 15% from spot

    # Minimum absolute OI - lowered to catch smaller but significant walls
    min_absolute_oi: int = 25  # Lowered from 50 for better detection


class WallDetector:
    """
    Detects Options walls (OI concentrations) from Options data.
    
    Wall Definition:
        - Call Wall: Strike above spot with high call OI
        - Put Wall: Strike below spot with high put OI
    
    Purpose:
        Identify strikes that act as support/resistance due to
        large option positions that market makers need to hedge.
    
    Signal Impact:
        - Put walls below spot = Support levels
        - Call walls above spot = Resistance levels
        - Strongest walls used for SL/TP
    
    Attributes:
        config: Wall detection configuration
    """
    
    def __init__(self, config: Optional[WallDetectorConfig] = None):
        """
        Initialize wall detector.
        
        Args:
            config: Wall detection configuration
        """
        self.config = config or WallDetectorConfig()
        
        logger.info(
            "Wall detector initialized",
            extra={"data": {
                "min_concentration": self.config.min_oi_concentration,
                "major_concentration": self.config.major_wall_concentration,
            }}
        )
    
    def detect(self, chain: OptionsChain) -> WallAnalysis:
        """
        Detect walls from options chain.
        
        Args:
            chain: Options chain data
            
        Returns:
            WallAnalysis with all detected walls
        """
        total_oi = chain.total_call_oi + chain.total_put_oi
        
        logger.info(
            f"Wall detection for {chain.underlying}: total_oi={total_oi}, "
            f"call_oi={chain.total_call_oi}, put_oi={chain.total_put_oi}, "
            f"strikes={len(chain.strikes)}, spot={chain.spot_price}"
        )
        
        if total_oi < self.config.min_absolute_oi:
            logger.warning(f"Insufficient total OI for wall detection: {total_oi} < {self.config.min_absolute_oi}")
            return self._create_empty_analysis(chain)
        
        # Detect call walls (above spot - resistance)
        call_walls = self._detect_call_walls(chain, total_oi)
        
        # Detect put walls (below spot - support)
        put_walls = self._detect_put_walls(chain, total_oi)
        
        # Find strongest and nearest walls
        strongest_put = self._find_strongest(put_walls)
        strongest_call = self._find_strongest(call_walls)
        nearest_put = self._find_nearest(put_walls, chain.spot_price)
        nearest_call = self._find_nearest(call_walls, chain.spot_price)
        
        # Calculate metrics
        wall_intensity = self._calculate_wall_intensity(put_walls, call_walls)
        wall_imbalance = self._calculate_wall_imbalance(put_walls, call_walls)
        
        # Generate S/R levels
        support_levels = [w.strike for w in put_walls[:3]]
        resistance_levels = [w.strike for w in call_walls[:3]]
        
        analysis = WallAnalysis(
            symbol=chain.underlying,
            spot_price=chain.spot_price,
            timestamp=datetime.utcnow(),
            
            put_walls=put_walls,
            call_walls=call_walls,
            
            strongest_put_wall=strongest_put,
            strongest_call_wall=strongest_call,
            nearest_put_wall=nearest_put,
            nearest_call_wall=nearest_call,
            
            total_walls=len(put_walls) + len(call_walls),
            wall_intensity=wall_intensity,
            wall_imbalance=wall_imbalance,
            
            support_levels=support_levels,
            resistance_levels=resistance_levels,
        )
        
        logger.info(
            f"Wall detection complete for {chain.underlying}",
            extra={"data": {
                "put_walls": len(put_walls),
                "call_walls": len(call_walls),
                "wall_intensity": wall_intensity,
            }}
        )
        
        return analysis
    
    def _detect_call_walls(
        self,
        chain: OptionsChain,
        total_oi: int,
    ) -> List[OptionWall]:
        """
        Detect call walls (resistance above spot).
        
        Args:
            chain: Options chain
            total_oi: Total open interest
            
        Returns:
            List of call walls
        """
        walls = []
        spot = chain.spot_price
        max_distance = spot * (self.config.max_wall_distance / 100)
        
        # Track potential walls for debug
        candidates = 0
        filtered_distance = 0
        filtered_oi = 0
        filtered_concentration = 0
        
        for strike_price, strike_data in chain.strikes.items():
            # Only consider strikes above spot
            if strike_price <= spot:
                continue
            
            # Check distance
            if strike_price - spot > max_distance:
                filtered_distance += 1
                continue
            
            call_oi = strike_data.call.open_interest
            
            if call_oi < self.config.min_absolute_oi:
                filtered_oi += 1
                continue
            
            candidates += 1
            
            # Calculate concentration
            concentration = call_oi / total_oi
            
            if concentration < self.config.min_oi_concentration:
                filtered_concentration += 1
                continue
            
            # Create wall
            wall = OptionWall(
                strike=strike_price,
                wall_type="CALL_WALL",
                open_interest=call_oi,
                oi_percentage=concentration,
                oi_change_24h=0.0,  # Requires historical data
                volume=strike_data.call.volume,
                volume_vs_avg=1.0,
                distance_from_spot=(strike_price - spot) / spot,
                side="ABOVE",
                strength_score=self._calculate_strength(concentration, call_oi),
                is_major_wall=concentration >= self.config.major_wall_concentration,
            )
            
            walls.append(wall)
        
        # Sort by strength
        walls.sort(key=lambda w: w.strength_score, reverse=True)
        
        logger.debug(
            f"Call wall detection: {candidates} candidates, "
            f"{len(walls)} walls found (filtered: {filtered_distance} distance, "
            f"{filtered_oi} low_oi, {filtered_concentration} low_concentration)"
        )
        
        return walls
    
    def _detect_put_walls(
        self,
        chain: OptionsChain,
        total_oi: int,
    ) -> List[OptionWall]:
        """
        Detect put walls (support below spot).
        
        Args:
            chain: Options chain
            total_oi: Total open interest
            
        Returns:
            List of put walls
        """
        walls = []
        spot = chain.spot_price
        max_distance = spot * (self.config.max_wall_distance / 100)
        
        # Track potential walls for debug
        candidates = 0
        filtered_distance = 0
        filtered_oi = 0
        filtered_concentration = 0
        
        for strike_price, strike_data in chain.strikes.items():
            # Only consider strikes below spot
            if strike_price >= spot:
                continue
            
            # Check distance
            if spot - strike_price > max_distance:
                filtered_distance += 1
                continue
            
            put_oi = strike_data.put.open_interest
            
            if put_oi < self.config.min_absolute_oi:
                filtered_oi += 1
                continue
            
            candidates += 1
            
            # Calculate concentration
            concentration = put_oi / total_oi
            
            if concentration < self.config.min_oi_concentration:
                filtered_concentration += 1
                continue
            
            # Create wall
            wall = OptionWall(
                strike=strike_price,
                wall_type="PUT_WALL",
                open_interest=put_oi,
                oi_percentage=concentration,
                oi_change_24h=0.0,
                volume=strike_data.put.volume,
                volume_vs_avg=1.0,
                distance_from_spot=(spot - strike_price) / spot,
                side="BELOW",
                strength_score=self._calculate_strength(concentration, put_oi),
                is_major_wall=concentration >= self.config.major_wall_concentration,
            )
            
            walls.append(wall)
        
        # Sort by strength
        walls.sort(key=lambda w: w.strength_score, reverse=True)
        
        logger.debug(
            f"Put wall detection: {candidates} candidates, "
            f"{len(walls)} walls found (filtered: {filtered_distance} distance, "
            f"{filtered_oi} low_oi, {filtered_concentration} low_concentration)"
        )
        
        return walls
    
    def _calculate_strength(
        self,
        concentration: float,
        oi: int,
    ) -> float:
        """
        Calculate wall strength score.
        
        Args:
            concentration: OI concentration
            oi: Absolute OI
            
        Returns:
            Strength score (0-1)
        """
        # Concentration component (0-0.5)
        conc_score = min(concentration / 0.3, 0.5)
        
        # Size component (0-0.5)
        # Larger OI = stronger wall
        size_score = min(oi / 10_000, 0.5)
        
        return conc_score + size_score
    
    def _find_strongest(
        self,
        walls: List[OptionWall],
    ) -> Optional[OptionWall]:
        """Find strongest wall."""
        if not walls:
            return None
        return max(walls, key=lambda w: w.strength_score)
    
    def _find_nearest(
        self,
        walls: List[OptionWall],
        spot: float,
    ) -> Optional[OptionWall]:
        """Find nearest wall to spot."""
        if not walls:
            return None
        return min(walls, key=lambda w: abs(w.strike - spot))
    
    def _calculate_wall_intensity(
        self,
        put_walls: List[OptionWall],
        call_walls: List[OptionWall],
    ) -> float:
        """
        Calculate overall wall intensity.
        
        Higher intensity = more significant walls present.
        
        Args:
            put_walls: List of put walls
            call_walls: List of call walls
            
        Returns:
            Intensity score (0-1)
        """
        all_walls = put_walls + call_walls
        
        if not all_walls:
            return 0.0
        
        # Sum of strength scores, normalized
        total_strength = sum(w.strength_score for w in all_walls)
        
        return min(total_strength / 2.0, 1.0)
    
    def _calculate_wall_imbalance(
        self,
        put_walls: List[OptionWall],
        call_walls: List[OptionWall],
    ) -> float:
        """
        Calculate wall imbalance.
        
        Positive = More put walls (bullish support)
        Negative = More call walls (bearish resistance)
        
        Args:
            put_walls: List of put walls
            call_walls: List of call walls
            
        Returns:
            Imbalance score (-1 to 1)
        """
        put_strength = sum(w.strength_score for w in put_walls)
        call_strength = sum(w.strength_score for w in call_walls)
        
        total = put_strength + call_strength
        
        if total == 0:
            return 0.0
        
        return (put_strength - call_strength) / total
    
    def _create_empty_analysis(self, chain: OptionsChain) -> WallAnalysis:
        """Create empty wall analysis."""
        return WallAnalysis(
            symbol=chain.underlying,
            spot_price=chain.spot_price,
            timestamp=datetime.utcnow(),
        )
    
    def get_wall_summary(self, analysis: WallAnalysis) -> Dict[str, Any]:
        """
        Get summary of wall analysis.
        
        Args:
            analysis: Wall analysis
            
        Returns:
            Summary dictionary
        """
        return {
            "symbol": analysis.symbol,
            "spot_price": analysis.spot_price,
            "total_walls": analysis.total_walls,
            "put_walls": len(analysis.put_walls),
            "call_walls": len(analysis.call_walls),
            "wall_intensity": round(analysis.wall_intensity, 3),
            "wall_imbalance": round(analysis.wall_imbalance, 3),
            "nearest_support": analysis.nearest_put_wall.strike if analysis.nearest_put_wall else None,
            "nearest_resistance": analysis.nearest_call_wall.strike if analysis.nearest_call_wall else None,
            "support_levels": analysis.support_levels,
            "resistance_levels": analysis.resistance_levels,
        }
    
    def get_sr_from_walls(
        self,
        analysis: WallAnalysis,
    ) -> Tuple[List[float], List[float]]:
        """
        Get support and resistance levels from walls.
        
        Args:
            analysis: Wall analysis
            
        Returns:
            Tuple of (support_levels, resistance_levels)
        """
        return analysis.support_levels, analysis.resistance_levels
