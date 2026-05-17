"""
Asset selector for choosing top assets for analysis.

This module selects the top N assets from the activity-ranked list
for detailed Options analysis and signal generation.

Selection Criteria:
- Activity score >= minimum threshold
- Sufficient liquidity
- Has Options data available
- Not in exclusion list
"""

from typing import List, Set, Optional, Dict, Any
from dataclasses import dataclass

from binance_signal_generator.models import (
    ActivityMetrics,
    RankedAsset,
)
from binance_signal_generator.ranking.activity_scorer import ActivityScorer, ActivityScanResult
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SelectionConfig:
    """Configuration for asset selection."""
    top_n: int = 5
    min_activity_score: float = 0.15  # Lowered from 0.30 to allow more assets
    min_options_volume: float = 100_000  # $100K minimum (lowered from $1M)
    min_active_strikes: int = 5
    excluded_symbols: Set[str] = None
    
    def __post_init__(self):
        if self.excluded_symbols is None:
            self.excluded_symbols = set()


class AssetSelector:
    """
    Selects top N assets for detailed analysis.
    
    Purpose:
        From all available assets, select the ones with highest
        activity scores for full signal generation pipeline.
    
    Selection Criteria:
        1. Activity score >= min_threshold
        2. Sufficient liquidity (min volume, min strikes)
        3. Not in exclusion list
    
    Attributes:
        config: Selection configuration
    """
    
    def __init__(
        self,
        config: Optional[SelectionConfig] = None,
        top_n: int = 5,
        min_activity_score: float = 0.30,
        min_options_volume: float = 1_000_000,
        min_active_strikes: int = 5,
        excluded_symbols: Optional[Set[str]] = None,
    ):
        """
        Initialize asset selector.
        
        Args:
            config: Selection configuration object (overrides other args)
            top_n: Number of assets to select
            min_activity_score: Minimum activity score threshold
            min_options_volume: Minimum 24h options volume in $
            min_active_strikes: Minimum number of active strikes
            excluded_symbols: Set of symbols to exclude
        """
        if config:
            self.config = config
        else:
            self.config = SelectionConfig(
                top_n=top_n,
                min_activity_score=min_activity_score,
                min_options_volume=min_options_volume,
                min_active_strikes=min_active_strikes,
                excluded_symbols=excluded_symbols or set(),
            )
        
        logger.info(
            "Asset selector initialized",
            extra={"data": {
                "top_n": self.config.top_n,
                "min_score": self.config.min_activity_score,
                "excluded": list(self.config.excluded_symbols),
            }}
        )
    
    def select(
        self,
        metrics_list: List[ActivityMetrics],
    ) -> List[RankedAsset]:
        """
        Select top assets from activity metrics.
        
        Args:
            metrics_list: List of activity metrics (should be pre-scored)
            
        Returns:
            List of RankedAsset for detailed analysis
        """
        selected = []
        
        # Sort by score if not already sorted
        sorted_metrics = sorted(
            metrics_list,
            key=lambda m: m.activity_score,
            reverse=True,
        )
        
        for rank, metrics in enumerate(sorted_metrics, 1):
            # Check activity score threshold
            if metrics.activity_score < self.config.min_activity_score:
                logger.debug(
                    f"{metrics.symbol} below threshold: {metrics.activity_score:.2f}"
                )
                continue
            
            # Check exclusion list
            if metrics.symbol in self.config.excluded_symbols:
                logger.debug(f"{metrics.symbol} in exclusion list")
                continue
            
            # Check liquidity
            if not self._check_liquidity(metrics):
                logger.debug(f"{metrics.symbol} insufficient liquidity")
                continue
            
            # Create ranked asset
            selected.append(RankedAsset(
                symbol=metrics.symbol,
                rank=len(selected) + 1,
                activity_score=metrics.activity_score,
                primary_driver=metrics.primary_driver,
                quick_metrics={
                    "oi_change_pct": metrics.oi_change_pct,
                    "volume": metrics.total_options_volume,
                    "iv_percentile": metrics.iv_percentile,
                    "pcr_extremeness": metrics.pcr_extremeness,
                    "active_strikes": metrics.num_strikes_active,
                },
                selection_reason=f"High {metrics.primary_driver}",
            ))
            
            logger.debug(
                f"Selected {metrics.symbol}",
                extra={"data": {
                    "rank": selected[-1].rank,
                    "score": metrics.activity_score,
                    "driver": metrics.primary_driver,
                }}
            )
            
            # Stop at top N
            if len(selected) >= self.config.top_n:
                break
        
        logger.info(
            f"Selected {len(selected)} assets from {len(metrics_list)} candidates"
        )
        
        return selected
    
    def _check_liquidity(self, metrics: ActivityMetrics) -> bool:
        """
        Check if asset has sufficient liquidity.
        
        Args:
            metrics: Activity metrics for the asset
            
        Returns:
            True if liquid enough
        """
        return (
            metrics.total_options_volume >= self.config.min_options_volume and
            metrics.num_strikes_active >= self.config.min_active_strikes
        )
    
    def select_from_scan_result(
        self,
        scan_result: ActivityScanResult,
    ) -> List[RankedAsset]:
        """
        Select assets from scan result.
        
        Args:
            scan_result: Activity scan result
            
        Returns:
            List of RankedAsset
        """
        metrics_list = list(scan_result.metrics_by_symbol.values())
        return self.select(metrics_list)
    
    def get_selection_summary(
        self,
        selected: List[RankedAsset],
    ) -> Dict[str, Any]:
        """
        Get summary of selection results.
        
        Args:
            selected: List of selected assets
            
        Returns:
            Dictionary with selection summary
        """
        if not selected:
            return {
                "selected_count": 0,
                "symbols": [],
                "avg_score": 0.0,
                "drivers": {},
            }
        
        drivers = {}
        for asset in selected:
            driver = asset.primary_driver
            drivers[driver] = drivers.get(driver, 0) + 1
        
        return {
            "selected_count": len(selected),
            "symbols": [a.symbol for a in selected],
            "avg_score": sum(a.activity_score for a in selected) / len(selected),
            "top_score": selected[0].activity_score if selected else 0.0,
            "bottom_score": selected[-1].activity_score if selected else 0.0,
            "drivers": drivers,
        }
    
    def add_exclusion(self, symbol: str) -> None:
        """
        Add a symbol to the exclusion list.
        
        Args:
            symbol: Symbol to exclude
        """
        self.config.excluded_symbols.add(symbol)
        logger.info(f"Added {symbol} to exclusion list")
    
    def remove_exclusion(self, symbol: str) -> None:
        """
        Remove a symbol from the exclusion list.
        
        Args:
            symbol: Symbol to remove from exclusion
        """
        self.config.excluded_symbols.discard(symbol)
        logger.info(f"Removed {symbol} from exclusion list")
    
    def set_excluded_symbols(self, symbols: Set[str]) -> None:
        """
        Set the exclusion list.
        
        Args:
            symbols: Set of symbols to exclude
        """
        self.config.excluded_symbols = symbols.copy()
        logger.info(f"Set exclusion list: {symbols}")
    
    def update_thresholds(
        self,
        min_activity_score: Optional[float] = None,
        min_options_volume: Optional[float] = None,
        min_active_strikes: Optional[int] = None,
    ) -> None:
        """
        Update selection thresholds.
        
        Args:
            min_activity_score: New minimum activity score
            min_options_volume: New minimum options volume
            min_active_strikes: New minimum active strikes
        """
        if min_activity_score is not None:
            self.config.min_activity_score = min_activity_score
        if min_options_volume is not None:
            self.config.min_options_volume = min_options_volume
        if min_active_strikes is not None:
            self.config.min_active_strikes = min_active_strikes
        
        logger.info(
            "Updated selection thresholds",
            extra={"data": {
                "min_score": self.config.min_activity_score,
                "min_volume": self.config.min_options_volume,
                "min_strikes": self.config.min_active_strikes,
            }}
        )
