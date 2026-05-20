"""
Asset activity scorer for ranking assets by Options activity.

This module scores assets based on their Options market activity
to identify which assets have the most interesting activity for
detailed analysis and signal generation.

Activity Score Components:
- Open Interest change (25%)
- Volume spike (20%)
- IV percentile (15%)
- PCR extremeness (15%)
- Whale activity (15%)
- Total volume (10%)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from binance_signal_generator.models import (
    ActivityMetrics,
    ActivityDriver,
    OptionsChain,
)
from binance_signal_generator.config import load_config, ActivityScorerConfig
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ActivityScanResult:
    """Result of activity scan across all assets."""

    timestamp: datetime
    total_assets_scanned: int
    metrics_by_symbol: Dict[str, ActivityMetrics]
    ranked_symbols: List[str]
    scan_duration_seconds: float


class ActivityScorer:
    """
    Scores assets by Options market activity level.

    Purpose:
        Quickly scan all assets to identify which have the most
        interesting Options activity for detailed analysis.

    Activity Score Formula:
        score = w1*oi_change + w2*volume_spike + w3*iv_percentile
              + w4*pcr_extreme + w5*whale_activity + w6*total_volume

    Attributes:
        config: Activity scorer configuration (loaded from config.yaml)
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize activity scorer.

        Config is loaded from config.yaml via load_config().
        Single source of truth - no fallback defaults.

        Args:
            config_path: Optional path to config file
        """
        loaded_config = load_config(config_path)
        self.config = loaded_config.activity_scorer

        # Build weights dict from config
        self.weights = {
            ActivityDriver.OI_CHANGE: self.config.weight_oi_change,
            ActivityDriver.VOLUME_SPIKE: self.config.weight_volume_spike,
            ActivityDriver.IV_INTEREST: self.config.weight_iv_interest,
            ActivityDriver.PCR_EXTREME: self.config.weight_pcr_extreme,
            ActivityDriver.WHALE_ACTIVITY: self.config.weight_whale_activity,
            ActivityDriver.TOTAL_VOLUME: self.config.weight_total_volume,
        }
        self.oi_change_max = self.config.oi_change_max
        self.volume_spike_max = self.config.volume_spike_max
        self.total_volume_max = self.config.total_volume_max

        logger.info(
            "Activity scorer initialized",
            extra={"data": {"weights": {k.value: v for k, v in self.weights.items()}}},
        )

    def calculate_score(self, metrics: ActivityMetrics) -> float:
        """
        Calculate normalized activity score (0-1).

        Higher score = More interesting activity.

        Args:
            metrics: Activity metrics for an asset

        Returns:
            Score between 0 and 1
        """
        # Normalize each component to 0-1 range
        oi_change_norm = min(abs(metrics.oi_change_pct) / self.oi_change_max, 1.0)
        volume_norm = min(metrics.volume_spike_score / self.volume_spike_max, 1.0)
        iv_norm = metrics.iv_percentile
        pcr_norm = metrics.pcr_extremeness
        whale_norm = metrics.whale_activity
        volume_total_norm = min(metrics.total_options_volume / self.total_volume_max, 1.0)

        # Weighted sum
        score = (
            self.weights[ActivityDriver.OI_CHANGE] * oi_change_norm
            + self.weights[ActivityDriver.VOLUME_SPIKE] * volume_norm
            + self.weights[ActivityDriver.IV_INTEREST] * iv_norm
            + self.weights[ActivityDriver.PCR_EXTREME] * pcr_norm
            + self.weights[ActivityDriver.WHALE_ACTIVITY] * whale_norm
            + self.weights[ActivityDriver.TOTAL_VOLUME] * volume_total_norm
        )

        logger.debug(
            f"Activity score for {metrics.symbol}: {score:.3f} "
            f"(vol={metrics.total_options_volume:.0f}, pcr={pcr_norm:.3f})"
        )

        return min(score, 1.0)

    def identify_primary_driver(self, metrics: ActivityMetrics) -> ActivityDriver:
        """
        Identify which metric is driving the most activity.

        Args:
            metrics: Activity metrics for an asset

        Returns:
            The ActivityDriver with highest contribution
        """
        # Calculate normalized contributions
        contributions = {
            ActivityDriver.OI_CHANGE: abs(metrics.oi_change_pct) / self.oi_change_max,
            ActivityDriver.VOLUME_SPIKE: metrics.volume_spike_score / self.volume_spike_max,
            ActivityDriver.IV_INTEREST: metrics.iv_percentile,
            ActivityDriver.PCR_EXTREME: metrics.pcr_extremeness,
            ActivityDriver.WHALE_ACTIVITY: metrics.whale_activity,
            ActivityDriver.TOTAL_VOLUME: min(
                metrics.total_options_volume / self.total_volume_max, 1.0
            ),
        }

        return max(contributions, key=contributions.get)

    def score_metrics(self, metrics: ActivityMetrics) -> ActivityMetrics:
        """
        Calculate and populate score in metrics object.

        Args:
            metrics: Activity metrics to score

        Returns:
            The same metrics object with score populated
        """
        metrics.activity_score = self.calculate_score(metrics)
        metrics.primary_driver = self.identify_primary_driver(metrics).value
        return metrics

    def score_from_chain(
        self,
        chain: OptionsChain,
        whale_activity: float = 0.0,
        oi_change_pct: float = 0.0,
        volume_spike_score: float = 0.0,
    ) -> ActivityMetrics:
        """
        Score an asset from its options chain.

        This is a convenience method that extracts metrics from
        the options chain and calculates the score.

        Args:
            chain: Options chain data
            whale_activity: Whale activity score (0-1), calculated externally
            oi_change_pct: OI change percentage (e.g., 5.0 for +5%), from /futures/data/openInterestHist
            volume_spike_score: Volume spike ratio (e.g., 2.5 for 2.5x avg), from /fapi/v1/klines

        Returns:
            ActivityMetrics with score
        """
        # Calculate metrics from chain
        total_oi = chain.total_call_oi + chain.total_put_oi
        # BUG FIX (Bug #14): Use notional (USDT) volume for total_options_volume,
        # not contract count. After Bug #4 fix, total_call_volume/total_put_volume
        # are contract counts. The scoring normalization uses total_volume_max
        # ($10M by default) which is a USDT amount. Using contract count would
        # make volume_total_norm ≈ 0 for all assets (5000 contracts / $10M = 0.0005).
        total_volume_notional = chain.total_call_notional + chain.total_put_notional
        active_strikes = len(
            [
                s
                for s in chain.strikes.values()
                if s.call.open_interest > 0 or s.put.open_interest > 0
            ]
        )

        # Calculate PCR extremeness
        pcr = chain.get_pcr()
        pcr_extremeness = self._calc_pcr_extremeness(pcr)

        # Get IV percentile from real mark price data
        iv_percentile = self._estimate_iv_percentile(chain)

        # Create metrics with historical data (now passed as parameters)
        metrics = ActivityMetrics(
            symbol=chain.underlying,
            timestamp=datetime.utcnow(),
            oi_change_pct=oi_change_pct,  # From /futures/data/openInterestHist
            volume_spike_score=volume_spike_score,  # From /fapi/v1/klines
            iv_percentile=iv_percentile,
            pcr_extremeness=pcr_extremeness,
            whale_activity=whale_activity,
            total_options_volume=total_volume_notional,  # BUG FIX (Bug #14): Use notional for scoring
            num_strikes_active=active_strikes,
        )

        # Score the metrics
        return self.score_metrics(metrics)

    def _calc_pcr_extremeness(self, pcr: float) -> float:
        """
        Calculate how extreme PCR is.

        PCR = 1.0 is neutral.
        PCR > 1.5 or < 0.5 is very extreme.

        Args:
            pcr: Put/Call ratio

        Returns:
            Extremeness score (0-1)
        """
        if pcr <= 0:
            return 0.0

        if pcr > 1.0:
            # Put heavy - scale: 1.0 -> 0, 1.5 -> 1.0
            return min((pcr - 1.0) / 0.5, 1.0)
        else:
            # Call heavy - scale: 1.0 -> 0, 0.5 -> 1.0
            return min((1.0 - pcr) / 0.5, 1.0)

    def _estimate_iv_percentile(self, chain: OptionsChain) -> float:
        """
        Calculate IV percentile from options chain.

        Uses the average IV from mark prices (real data from API).
        The IV is returned as decimal (e.g., 1.45 = 145% annualized).

        Args:
            chain: Options chain with avg_call_iv and avg_put_iv populated

        Returns:
            IV percentile (0-1) based on typical crypto IV ranges
        """
        # Use average IV from chain (populated from mark price API)
        avg_iv = chain.avg_call_iv if chain.avg_call_iv > 0 else chain.avg_put_iv

        # If both are available, use weighted average
        if chain.avg_call_iv > 0 and chain.avg_put_iv > 0:
            avg_iv = (chain.avg_call_iv + chain.avg_put_iv) / 2

        if avg_iv == 0:
            return 0.5  # Default neutral if no IV data

        # IV normalization for crypto options
        # Binance returns IV as decimal (1.45 = 145% annualized)
        # Typical crypto IV ranges:
        # - Low IV: < 50% (0.50 decimal)
        # - Normal IV: 50-100% (0.50-1.00 decimal)
        # - High IV: > 100% (1.00 decimal)
        # Very high IV: > 150% (1.50 decimal)

        if avg_iv < 0.5:
            return 0.2  # Low IV
        elif avg_iv < 0.75:
            return 0.4  # Below average
        elif avg_iv < 1.0:
            return 0.5  # Normal
        elif avg_iv < 1.25:
            return 0.65  # Above average
        elif avg_iv < 1.5:
            return 0.8  # High IV
        else:
            return 0.95  # Very high IV

    def rank_assets(
        self,
        metrics_list: List[ActivityMetrics],
    ) -> List[ActivityMetrics]:
        """
        Rank assets by activity score.

        Args:
            metrics_list: List of activity metrics

        Returns:
            List sorted by score (highest first)
        """
        # Score all metrics
        scored = [self.score_metrics(m) for m in metrics_list]

        # Sort by score descending
        return sorted(scored, key=lambda m: m.activity_score, reverse=True)

    def get_top_assets(
        self,
        metrics_list: List[ActivityMetrics],
        n: int = 5,
        min_score: float = 0.3,
    ) -> List[ActivityMetrics]:
        """
        Get top N assets by activity score.

        Args:
            metrics_list: List of activity metrics
            n: Number of top assets to return
            min_score: Minimum score threshold

        Returns:
            List of top N metrics
        """
        ranked = self.rank_assets(metrics_list)

        # Filter by minimum score
        filtered = [m for m in ranked if m.activity_score >= min_score]

        return filtered[:n]

    def get_activity_summary(self, metrics: ActivityMetrics) -> Dict[str, Any]:
        """
        Get a summary of activity for an asset.

        Args:
            metrics: Activity metrics

        Returns:
            Dictionary with activity summary
        """
        return {
            "symbol": metrics.symbol,
            "activity_score": round(metrics.activity_score, 3),
            "primary_driver": metrics.primary_driver,
            "components": {
                "oi_change_pct": round(metrics.oi_change_pct, 2),
                "volume_spike_score": round(metrics.volume_spike_score, 2),
                "iv_percentile": round(metrics.iv_percentile, 3),
                "pcr_extremeness": round(metrics.pcr_extremeness, 3),
                "whale_activity": round(metrics.whale_activity, 3),
                "total_options_volume": round(metrics.total_options_volume, 0),
                "active_strikes": metrics.num_strikes_active,
            },
        }
