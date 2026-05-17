"""
Pipeline orchestrator for coordinating signal generation.

This module orchestrates the complete signal generation pipeline:
1. Activity Scan - Scan all assets for activity scores
2. Asset Selection - Select top N assets by activity
3. Data Fetching - Fetch Options and Futures data
4. Analysis - Run IV, PCR, OI, Max Pain analysis
5. Signal Generation - Create trading signals
6. Output - Output JSON to stdout

The orchestrator coordinates all modules and handles errors gracefully.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from binance_signal_generator.config.loader import Config
from binance_signal_generator.data.options_fetcher import OptionsFetcher
from binance_signal_generator.data.futures_fetcher import FuturesFetcher
from binance_signal_generator.ranking.activity_scorer import ActivityScorer
from binance_signal_generator.ranking.asset_selector import AssetSelector, SelectionConfig
from binance_signal_generator.analysis.signal_scorer import SignalScorer
from binance_signal_generator.whale.whale_detector import WhaleDetector, WhaleDetectorConfig
from binance_signal_generator.analysis.wall_detector import WallDetector, WallDetectorConfig
from binance_signal_generator.analysis.gamma_exposure import GammaExposureCalculator, GammaExposureConfig
from binance_signal_generator.analysis.sentiment import SentimentAnalyzer, SentimentConfig
from binance_signal_generator.output.sr_levels import SRLevelCalculator, SRLevelConfig
from binance_signal_generator.models import (
    OptionsChain,
    FuturesData,
    ActivityMetrics,
    RankedAsset,
    OptionsSignal,
    TradingSignal,
    SignalDirection,
    SignalStrength,
    EntryZone,
    StopLoss,
    TakeProfitLevel,
    ExecutionResult,
)
from binance_signal_generator.utils.logging import get_logger
from binance_signal_generator.utils.exceptions import PipelineError
from binance_signal_generator.utils.rate_limiter import RateLimiter

logger = get_logger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for pipeline execution."""
    # Timing
    timeout_seconds: int = 600
    activity_scan_timeout: int = 60
    data_fetch_timeout: int = 180
    analysis_timeout: int = 180
    
    # Selection
    top_n_assets: int = 5
    min_activity_score: float = 0.30
    
    # Signal generation
    min_signal_confidence: float = 0.50
    max_signals_per_run: int = 5
    
    # Output
    output_to_stdout: bool = True
    save_to_database: bool = False


class PipelineOrchestrator:
    """
    Orchestrates the signal generation pipeline.
    
    Pipeline Stages:
    1. Activity Scan: Quick scan of all assets
    2. Asset Selection: Select top N by activity
    3. Data Fetching: Fetch Options/Futures data
    4. Analysis: Run all analyzers
    5. Signal Generation: Create trading signals
    6. Output: JSON to stdout
    
    Attributes:
        config: Pipeline configuration
        options_fetcher: Options data fetcher
        futures_fetcher: Futures data fetcher
        activity_scorer: Activity scoring module
        asset_selector: Asset selection module
        signal_scorer: Signal scoring module
    """
    
    def __init__(
        self,
        config: Config,
        pipeline_config: Optional[PipelineConfig] = None,
    ):
        """
        Initialize pipeline orchestrator.
        
        Args:
            config: Application configuration
            pipeline_config: Pipeline-specific configuration
        """
        self.config = config
        self.pipeline_config = pipeline_config or PipelineConfig()
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(
            requests_per_second=15.0,
            burst=30,
        )
        
        # Initialize data fetchers
        self.options_fetcher = OptionsFetcher(
            api_key=config.binance.api_key,
            api_secret=config.binance.api_secret,
            testnet=config.binance.testnet,
            rate_limiter=self.rate_limiter,
        )
        
        self.futures_fetcher = FuturesFetcher(
            api_key=config.binance.api_key,
            api_secret=config.binance.api_secret,
            testnet=config.binance.testnet,
            rate_limiter=self.rate_limiter,
        )
        
        # Initialize analysis modules
        self.activity_scorer = ActivityScorer()
        self.asset_selector = AssetSelector(
            SelectionConfig(
                top_n=self.pipeline_config.top_n_assets,
                min_activity_score=self.pipeline_config.min_activity_score,
            )
        )
        self.signal_scorer = SignalScorer()
        
        # Initialize whale detector with config thresholds
        whale_config = WhaleDetectorConfig(
            min_premium=config.whale.min_premium,
            block_threshold=config.whale.block_threshold,
            lookback_hours=config.whale.lookback_hours,
            asset_thresholds=config.whale.asset_thresholds,
        )
        self.whale_detector = WhaleDetector(whale_config)
        
        # Initialize wall detector
        self.wall_detector = WallDetector(WallDetectorConfig())
        self.sr_calculator = SRLevelCalculator(SRLevelConfig())
        
        # Initialize gamma exposure calculator
        self.gamma_calculator = GammaExposureCalculator(GammaExposureConfig())
        
        # Initialize sentiment analyzer for L/S ratios and funding rates
        self.sentiment_analyzer = SentimentAnalyzer(SentimentConfig())
        
        # Execution tracking
        self._api_calls_made = 0
        self._errors: List[str] = []
        
        logger.info(
            "Pipeline orchestrator initialized",
            extra={"data": {
                "top_n": self.pipeline_config.top_n_assets,
                "min_score": self.pipeline_config.min_activity_score,
            }}
        )
    
    async def run(
        self,
        symbols: Optional[List[str]] = None,
    ) -> ExecutionResult:
        """
        Run the complete signal generation pipeline.
        
        Args:
            symbols: Optional specific symbols (bypasses activity scan)
            
        Returns:
            ExecutionResult with generated signals
        """
        start_time = datetime.utcnow()
        execution_id = f"EXEC_{start_time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        logger.info(
            f"Starting pipeline execution: {execution_id}",
            extra={"data": {"symbols": symbols}}
        )
        
        try:
            # Stage 1 & 2: Asset Selection
            if symbols:
                selected_assets = await self._select_specific_symbols(symbols)
            else:
                selected_assets = await self._run_activity_scan()
            
            if not selected_assets:
                logger.warning("No assets selected for analysis")
                return self._create_empty_result(execution_id, start_time)
            
            # Stage 3 & 4: Data Fetching and Analysis
            signals = await self._analyze_assets(selected_assets)
            
            # Stage 5 & 6: Signal Generation and Filtering
            valid_signals = self._filter_signals(signals)
            
            # Create result
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            result = ExecutionResult(
                execution_id=execution_id,
                timestamp=start_time,
                execution_duration_seconds=duration,
                assets_analyzed=len(selected_assets),
                signals_generated=len(valid_signals),
                selected_assets=[{
                    "symbol": a.symbol,
                    "rank": a.rank,
                    "activity_score": a.activity_score,
                    "primary_driver": a.primary_driver,
                } for a in selected_assets],
                signals=valid_signals,
                config_path=self.config.config_path,
                api_calls_made=self._api_calls_made,
                errors=self._errors,
            )
            
            logger.info(
                f"Pipeline completed: {execution_id}",
                extra={"data": {
                    "duration_seconds": duration,
                    "assets_analyzed": len(selected_assets),
                    "signals_generated": len(valid_signals),
                    "api_calls": self._api_calls_made,
                }}
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            self._errors.append(str(e))
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            return ExecutionResult(
                execution_id=execution_id,
                timestamp=start_time,
                execution_duration_seconds=duration,
                assets_analyzed=0,
                signals_generated=0,
                errors=[str(e)],
            )
    
    async def _run_activity_scan(self) -> List[RankedAsset]:
        """
        Run activity scan to select top assets.

        Returns:
            List of selected RankedAsset
        """
        logger.info("Starting activity scan")

        try:
            # Get available underlyings
            underlyings = await self.options_fetcher.get_available_underlyings()
            self._api_calls_made += 1

            logger.info(f"Found {len(underlyings)} underlyings")

            # Fetch activity metrics for each
            metrics_list: List[ActivityMetrics] = []

            # Process in batches to avoid rate limits
            batch_size = 10
            for i in range(0, min(len(underlyings), 50), batch_size):
                batch = underlyings[i:i + batch_size]

                # Fetch historical data for batch (OI change and volume spike)
                # This recovers the missing 45% of scoring weight!
                historical_data_tasks = []
                for underlying in batch:
                    historical_data_tasks.append(self._fetch_historical_data(underlying))

                historical_results = await asyncio.gather(*historical_data_tasks, return_exceptions=True)

                # Create tasks with historical data
                tasks = []
                for j, underlying in enumerate(batch):
                    hist_data = historical_results[j]
                    if isinstance(hist_data, Exception):
                        logger.debug(f"Historical data fetch failed for {underlying}: {hist_data}")
                        hist_data = (0.0, 0.0)  # Use defaults

                    oi_change_pct, volume_spike_score = hist_data
                    tasks.append(
                        self.options_fetcher.get_activity_summary(
                            underlying,
                            oi_change_pct=oi_change_pct,
                            volume_spike_score=volume_spike_score,
                        )
                    )

                results = await asyncio.gather(*tasks, return_exceptions=True)
                self._api_calls_made += len(batch) * 3  # Options chain + OI history + Volume history

                for result in results:
                    if isinstance(result, ActivityMetrics):
                        metrics_list.append(result)
                    elif isinstance(result, Exception):
                        logger.debug(f"Failed to get metrics: {result}")

            # Score and rank
            for metrics in metrics_list:
                self.activity_scorer.score_metrics(metrics)

            # Select top assets
            selected = self.asset_selector.select(metrics_list)

            logger.info(f"Selected {len(selected)} assets from {len(metrics_list)} candidates")

            return selected

        except Exception as e:
            logger.error(f"Activity scan failed: {e}")
            raise PipelineError(f"Activity scan failed: {e}")

    async def _fetch_historical_data(self, symbol: str) -> tuple:
        """
        Fetch historical data for OI change and volume spike calculations.

        Uses:
        - /futures/data/openInterestHist (weight: 0) for OI change
        - /fapi/v1/klines (weight: 2) for volume spike

        Supports intraday mode (15m intervals) or daily mode based on config.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")

        Returns:
            Tuple of (oi_change_pct, volume_spike_score)
        """
        try:
            # Get intraday settings from config
            intraday_config = getattr(self.config, 'intraday', None)
            use_intraday = intraday_config and intraday_config.enabled
            
            # Determine periods based on mode
            if use_intraday:
                oi_period = intraday_config.oi_period
                oi_limit = intraday_config.oi_limit
                volume_interval = intraday_config.volume_interval
                volume_limit = intraday_config.volume_limit
                logger.debug(f"Using intraday mode for {symbol}: oi_period={oi_period}, vol_interval={volume_interval}")
            else:
                oi_period = "1d"
                oi_limit = 7
                volume_interval = "1d"
                volume_limit = 30
                logger.debug(f"Using daily mode for {symbol}")

            # Fetch OI history
            oi_stats = await self.futures_fetcher.get_oi_statistics(
                symbol=symbol,
                period=oi_period,
                limit=oi_limit,
            )

            # Fetch volume history
            volume_history = await self.futures_fetcher.get_volume_history(
                symbol=symbol,
                interval=volume_interval,
                limit=volume_limit,
            )

            # Calculate OI change percentage
            # For intraday: compares current vs 4h ago (16 candles of 15m)
            # For daily: compares current vs 7 days ago
            oi_change_pct = 0.0
            if len(oi_stats) >= 2:
                latest_oi = oi_stats[-1].get("sum_open_interest", 0)
                
                if use_intraday:
                    # For intraday, compare with 4h ago (16 candles back)
                    # or start of period if less data
                    comparison_idx = max(0, min(16, len(oi_stats) - 1))
                    comparison_oi = oi_stats[comparison_idx].get("sum_open_interest", 0)
                else:
                    # For daily, compare with start
                    comparison_oi = oi_stats[0].get("sum_open_interest", 0)
                
                if comparison_oi > 0:
                    oi_change_pct = (latest_oi - comparison_oi) / comparison_oi * 100

            # Calculate volume spike score
            # For intraday: compares current vs last 4h avg
            # For daily: compares current vs 30-day avg
            volume_spike_score = 0.0
            if len(volume_history) >= 4:
                volumes = [v.get("volume", 0) for v in volume_history]
                current_volume = volumes[-1]
                
                if use_intraday:
                    # For intraday, use last 16 candles (4h) for average
                    avg_volume = sum(volumes[-17:-1]) / 16 if len(volumes) >= 17 else sum(volumes[:-1]) / max(1, len(volumes) - 1)
                else:
                    # For daily, use all but last for average
                    avg_volume = sum(volumes[:-1]) / max(1, len(volumes) - 1)

                if avg_volume > 0:
                    spike_ratio = current_volume / avg_volume
                    # Convert ratio to score: 1x = 0, 2x = 1.0, 3x+ = 2.0+
                    volume_spike_score = max(0, spike_ratio - 1)

            logger.debug(
                f"Historical data for {symbol}: oi_change={oi_change_pct:.2f}%, "
                f"volume_spike={volume_spike_score:.2f}x (mode={'intraday' if use_intraday else 'daily'})"
            )

            return (oi_change_pct, volume_spike_score)

        except Exception as e:
            logger.debug(f"Failed to fetch historical data for {symbol}: {e}")
            return (0.0, 0.0)
    
    async def _select_specific_symbols(
        self,
        symbols: List[str],
    ) -> List[RankedAsset]:
        """
        Create RankedAsset list for specific symbols.
        
        Args:
            symbols: List of symbols to analyze
            
        Returns:
            List of RankedAsset
        """
        selected = []
        for i, symbol in enumerate(symbols[:self.pipeline_config.top_n_assets]):
            selected.append(RankedAsset(
                symbol=symbol,
                rank=i + 1,
                activity_score=1.0,  # Max score for manually selected
                primary_driver="MANUAL",
                quick_metrics={},
                selection_reason="User specified",
            ))
        return selected
    
    async def _analyze_assets(
        self,
        assets: List[RankedAsset],
    ) -> List[TradingSignal]:
        """
        Analyze selected assets and generate signals.
        
        Args:
            assets: List of assets to analyze
            
        Returns:
            List of generated TradingSignal
        """
        signals = []
        
        for asset in assets:
            try:
                signal = await self._analyze_single_asset(asset)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Failed to analyze {asset.symbol}: {e}")
                self._errors.append(f"{asset.symbol}: {e}")
        
        return signals
    
    async def _analyze_single_asset(
        self,
        asset: RankedAsset,
    ) -> Optional[TradingSignal]:
        """
        Analyze a single asset and generate a signal.
        
        Args:
            asset: Asset to analyze
            
        Returns:
            TradingSignal or None
        """
        symbol = asset.symbol
        logger.debug(f"Analyzing {symbol}")
        
        try:
            # Fetch Options chain
            options_chain = await self.options_fetcher.get_option_chain(symbol)
            self._api_calls_made += 1
            
            # Fetch Futures data
            futures_data = await self.futures_fetcher.get_all_data(symbol)
            self._api_calls_made += 4  # price + OI + funding + mark
            
            # Fetch block trades for whale detection (using block trades API, not regular trades)
            # Block trades API accepts no symbol parameter (fetches all)
            block_trades = await self.options_fetcher.get_block_trades(limit=500)
            self._api_calls_made += 1
            
            # Run whale detection using block trades
            whale_analysis = self.whale_detector.analyze_block_trades(block_trades, options_chain)
            
            # Run wall detection
            wall_analysis = self.wall_detector.detect(options_chain)
            
            # Run gamma exposure analysis for dealer hedging levels
            gamma_analysis = self.gamma_calculator.calculate(options_chain)
            
            # Fetch sentiment data (L/S ratios + funding rate history)
            # Weight: 0 (L/S ratios) + 5 (funding rate) = 5 total
            sentiment_data = await self.futures_fetcher.get_sentiment_data(symbol)
            self._api_calls_made += 5  # Approximate: 0 + 0 + 5
            
            # Run sentiment analysis
            sentiment_analysis = self.sentiment_analyzer.analyze(
                symbol=symbol,
                top_trader_position_data=sentiment_data.get("top_trader_position", []),
                top_trader_account_data=sentiment_data.get("top_trader_account", []),
                funding_rate_data=sentiment_data.get("funding_rate_history", []),
            )
            
            logger.debug(
                f"Sentiment analysis for {symbol}: "
                f"position_ratio={sentiment_analysis.top_trader_position_ratio:.2f}, "
                f"account_ratio={sentiment_analysis.top_trader_account_ratio:.2f}, "
                f"funding_rate={sentiment_analysis.current_funding_rate:.6f}, "
                f"combined={sentiment_analysis.sentiment_score:.2f}, "
                f"signal={sentiment_analysis.signal.value}, "
                f"contrarian={sentiment_analysis.is_contrarian_signal}"
            )
            
            # Run Options analysis with sentiment and gamma exposure
            options_signal = self.signal_scorer.analyze(
                options_chain, 
                sentiment_analysis,
                gamma_analysis,
            )
            
            # Debug: Log analysis results
            logger.debug(
                f"Analysis for {symbol}: direction={options_signal.direction.value}, "
                f"confidence={options_signal.confidence:.3f}, raw_score={options_signal.raw_score:.3f}, "
                f"min_required={self.pipeline_config.min_signal_confidence}"
            )
            
            # Attach whale analysis to signal
            options_signal.whale_analysis = whale_analysis
            
            # Generate trading signal if confidence is sufficient
            if options_signal.confidence >= self.pipeline_config.min_signal_confidence:
                logger.info(f"Signal generated for {symbol}: {options_signal.direction.value} ({options_signal.confidence:.2f})")
                return self._create_trading_signal(
                    asset=asset,
                    options_signal=options_signal,
                    options_chain=options_chain,
                    futures_data=futures_data,
                    whale_analysis=whale_analysis,
                    wall_analysis=wall_analysis,
                    gamma_analysis=gamma_analysis,
                    sentiment_analysis=sentiment_analysis,
                )
            else:
                logger.debug(f"Signal confidence {options_signal.confidence:.3f} below threshold {self.pipeline_config.min_signal_confidence}")
            
            return None
            
        except Exception as e:
            logger.error(f"Analysis failed for {symbol}: {e}")
            raise
    
    def _create_trading_signal(
        self,
        asset: RankedAsset,
        options_signal: OptionsSignal,
        options_chain: OptionsChain,
        futures_data: FuturesData,
        whale_analysis: Optional[Any] = None,
        wall_analysis: Optional[Any] = None,
        gamma_analysis: Optional[Any] = None,
        sentiment_analysis: Optional[Any] = None,
    ) -> TradingSignal:
        """
        Create a complete trading signal.
        
        Args:
            asset: Ranked asset
            options_signal: Options analysis signal
            options_chain: Options chain data
            futures_data: Futures data
            whale_analysis: Whale activity analysis
            wall_analysis: Wall detection analysis
            gamma_analysis: Gamma exposure analysis for dealer hedging levels
            sentiment_analysis: Sentiment analysis from L/S ratios and funding rates
            
        Returns:
            Complete TradingSignal
        """
        signal_id = f"SIG_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{asset.symbol}"
        
        # Determine signal strength
        # Boost confidence if whale activity aligns
        confidence = options_signal.confidence
        if whale_analysis and whale_analysis.confidence_boost > 0:
            confidence = min(confidence + whale_analysis.confidence_boost, 1.0)
        
        if confidence >= 0.8:
            strength = SignalStrength.VERY_STRONG
        elif confidence >= 0.65:
            strength = SignalStrength.STRONG
        elif confidence >= 0.50:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK
        
        # Calculate entry zone (around current price)
        current_price = futures_data.price
        entry_zone = EntryZone(
            min=current_price * 0.995,  # 0.5% below
            max=current_price * 1.005,  # 0.5% above
            ideal=current_price,
        )
        
        # Calculate S/R levels from walls
        support_levels = []
        resistance_levels = []
        
        if wall_analysis:
            # Use wall-based support/resistance
            support_levels = [
                {"level": i + 1, "price": w.strike, "oi": w.open_interest, 
                 "distance_pct": round(w.distance_from_spot * 100, 2)}
                for i, w in enumerate(wall_analysis.put_walls[:3])
            ]
            resistance_levels = [
                {"level": i + 1, "price": w.strike, "oi": w.open_interest,
                 "distance_pct": round(w.distance_from_spot * 100, 2)}
                for i, w in enumerate(wall_analysis.call_walls[:3])
            ]
            
            # Use wall-based SL if available
            if options_signal.direction == SignalDirection.LONG and wall_analysis.nearest_put_wall:
                sl_price = wall_analysis.nearest_put_wall.strike
                sl_distance = (current_price - sl_price) / current_price * 100
                stop_loss = StopLoss(
                    price=sl_price,
                    type="WALL_BASED",
                    distance_pct=sl_distance,
                )
            elif options_signal.direction == SignalDirection.SHORT and wall_analysis.nearest_call_wall:
                sl_price = wall_analysis.nearest_call_wall.strike
                sl_distance = (sl_price - current_price) / current_price * 100
                stop_loss = StopLoss(
                    price=sl_price,
                    type="WALL_BASED",
                    distance_pct=sl_distance,
                )
            else:
                # Fallback to percentage-based
                if options_signal.direction == SignalDirection.LONG:
                    sl_price = current_price * 0.98
                else:
                    sl_price = current_price * 1.02
                stop_loss = StopLoss(
                    price=sl_price,
                    type="PERCENTAGE",
                    distance_pct=2.0,
                )
        else:
            # Fallback S/R from OI
            support_levels = self._get_support_levels(options_chain)
            resistance_levels = self._get_resistance_levels(options_chain)
            
            if options_signal.direction == SignalDirection.LONG:
                sl_price = current_price * 0.98
            else:
                sl_price = current_price * 1.02
            stop_loss = StopLoss(
                price=sl_price,
                type="PERCENTAGE",
                distance_pct=2.0,
            )
        
        # Calculate take profit levels
        take_profit_levels = self._calculate_take_profit(
            current_price=current_price,
            direction=options_signal.direction,
        )
        
        # Build whale metrics
        whale_metrics = {}
        if whale_analysis:
            whale_metrics = {
                "whale_buy_volume": whale_analysis.whale_buy_volume,
                "whale_sell_volume": whale_analysis.whale_sell_volume,
                "whale_net_volume": whale_analysis.whale_net_volume,
                "whale_direction": whale_analysis.whale_net_direction,
                "whale_activity_score": whale_analysis.whale_activity_score,
                "large_trades_count": whale_analysis.large_trades_count,
            }
        
        options_metrics = {
            "pcr_combined": options_signal.pcr_analysis.pcr_combined if options_signal.pcr_analysis else 1.0,
            "iv_percentile": options_signal.iv_analysis.iv_percentile if options_signal.iv_analysis else 0.5,
            "max_pain_distance": options_signal.max_pain_analysis.distance_pct if options_signal.max_pain_analysis else 0.0,
            "wall_intensity": wall_analysis.wall_intensity if wall_analysis else 0.0,
            "wall_imbalance": wall_analysis.wall_imbalance if wall_analysis else 0.0,
        }
        
        # Add gamma exposure metrics
        gamma_metrics = {}
        if gamma_analysis:
            gamma_metrics = {
                "gex_regime": gamma_analysis.gex_regime,
                "dealer_hedge_pressure": gamma_analysis.dealer_hedge_pressure,
                "gamma_flip": gamma_analysis.gamma_flip,
                "total_gex": gamma_analysis.total_gex,
                "gamma_risk_score": gamma_analysis.gamma_risk_score,
                # DTE (Days to Expiry) metrics
                "dte_days": round(gamma_analysis.dte_days, 1),
                "dte_weight": round(gamma_analysis.dte_weight, 2),
                "expiry_imminent": gamma_analysis.expiry_imminent,
            }
            
            # Use gamma levels to enhance support/resistance if walls are missing
            if not resistance_levels and gamma_analysis.gex_resistance_levels:
                resistance_levels = [
                    {"level": i + 1, "price": l.strike, "gex": round(l.gex_value, 2),
                     "strength": round(l.strength, 2), "type": "GAMMA_RESISTANCE"}
                    for i, l in enumerate(gamma_analysis.gex_resistance_levels[:3])
                ]
            if not support_levels and gamma_analysis.gex_support_levels:
                support_levels = [
                    {"level": i + 1, "price": l.strike, "gex": round(l.gex_value, 2),
                     "strength": round(l.strength, 2), "type": "GAMMA_SUPPORT"}
                    for i, l in enumerate(gamma_analysis.gex_support_levels[:3])
                ]
        
        # Merge gamma metrics into options_metrics
        options_metrics.update(gamma_metrics)
        
        # Add sentiment metrics (L/S ratios + funding rates)
        sentiment_metrics = {}
        if sentiment_analysis:
            sentiment_metrics = {
                "top_trader_position_ratio": round(sentiment_analysis.top_trader_position_ratio, 3),
                "top_trader_account_ratio": round(sentiment_analysis.top_trader_account_ratio, 3),
                "current_funding_rate": sentiment_analysis.current_funding_rate,
                "funding_rate_avg_7d": sentiment_analysis.funding_rate_avg_7d,
                "funding_rate_extreme": sentiment_analysis.funding_rate_extreme,
                "sentiment_score": round(sentiment_analysis.sentiment_score, 3),
                "combined_sentiment": sentiment_analysis.combined_sentiment,
                "is_contrarian_signal": sentiment_analysis.is_contrarian_signal,
            }
        
        # Merge sentiment metrics into options_metrics
        options_metrics.update(sentiment_metrics)
        
        futures_metrics = {
            "price": futures_data.price,
            "volume_24h": futures_data.volume_24h,
            "open_interest": futures_data.open_interest,
            "funding_rate": futures_data.funding_rate,
        }
        
        # Calculate risk/reward
        avg_tp_distance = sum(tp.distance_pct for tp in take_profit_levels) / len(take_profit_levels) if take_profit_levels else 0
        risk_reward = avg_tp_distance / stop_loss.distance_pct if stop_loss.distance_pct > 0 else 0
        
        return TradingSignal(
            signal_id=signal_id,
            timestamp=datetime.utcnow(),
            symbol=asset.symbol,
            asset_rank=asset.rank,
            activity_score=asset.activity_score,
            direction=options_signal.direction,
            confidence_score=confidence,
            signal_strength=strength,
            entry_zone=entry_zone,
            stop_loss=stop_loss,
            take_profit_levels=take_profit_levels,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            whale_metrics=whale_metrics,
            options_metrics=options_metrics,
            futures_metrics=futures_metrics,
            risk_reward_ratio=risk_reward,
        )
    
    def _calculate_take_profit(
        self,
        current_price: float,
        direction: SignalDirection,
    ) -> List[TakeProfitLevel]:
        """
        Calculate take profit levels.
        
        Args:
            current_price: Current price
            direction: Signal direction
            
        Returns:
            List of TakeProfitLevel
        """
        levels = []
        
        if direction == SignalDirection.LONG:
            # For longs: TP above entry
            tp_configs = [
                (1, 1.5, 0.015),   # TP1: 1.5% up, RR 1:1.5
                (2, 3.0, 0.030),   # TP2: 3% up, RR 1:3
                (3, 5.0, 0.050),   # TP3: 5% up, RR 1:5
            ]
            
            for level, ratio, distance in tp_configs:
                levels.append(TakeProfitLevel(
                    level=level,
                    price=current_price * (1 + distance),
                    ratio=ratio,
                    distance_pct=distance * 100,
                ))
        else:
            # For shorts: TP below entry
            tp_configs = [
                (1, 1.5, 0.015),   # TP1: 1.5% down
                (2, 3.0, 0.030),   # TP2: 3% down
                (3, 5.0, 0.050),   # TP3: 5% down
            ]
            
            for level, ratio, distance in tp_configs:
                levels.append(TakeProfitLevel(
                    level=level,
                    price=current_price * (1 - distance),
                    ratio=ratio,
                    distance_pct=distance * 100,
                ))
        
        return levels
    
    def _get_support_levels(self, chain: OptionsChain) -> List[Dict]:
        """Get support levels from put walls."""
        # Find strikes with high put OI below spot
        support = []
        spot = chain.spot_price
        
        put_strikes = [
            (strike, data.put.open_interest)
            for strike, data in chain.strikes.items()
            if strike < spot and data.put.open_interest > 0
        ]
        
        # Sort by OI descending
        put_strikes.sort(key=lambda x: x[1], reverse=True)
        
        for i, (strike, oi) in enumerate(put_strikes[:3]):
            support.append({
                "level": i + 1,
                "price": strike,
                "oi": oi,
                "distance_pct": round((spot - strike) / spot * 100, 2),
            })
        
        return support
    
    def _get_resistance_levels(self, chain: OptionsChain) -> List[Dict]:
        """Get resistance levels from call walls."""
        # Find strikes with high call OI above spot
        resistance = []
        spot = chain.spot_price
        
        call_strikes = [
            (strike, data.call.open_interest)
            for strike, data in chain.strikes.items()
            if strike > spot and data.call.open_interest > 0
        ]
        
        # Sort by OI descending
        call_strikes.sort(key=lambda x: x[1], reverse=True)
        
        for i, (strike, oi) in enumerate(call_strikes[:3]):
            resistance.append({
                "level": i + 1,
                "price": strike,
                "oi": oi,
                "distance_pct": round((strike - spot) / spot * 100, 2),
            })
        
        return resistance
    
    def _filter_signals(
        self,
        signals: List[TradingSignal],
    ) -> List[TradingSignal]:
        """
        Filter signals by quality criteria.
        
        Args:
            signals: List of signals
            
        Returns:
            Filtered list
        """
        filtered = []
        
        for signal in signals:
            # Check confidence
            if signal.confidence_score < self.pipeline_config.min_signal_confidence:
                continue
            
            # Check direction is not neutral
            if signal.direction == SignalDirection.NEUTRAL:
                continue
            
            filtered.append(signal)
            
            if len(filtered) >= self.pipeline_config.max_signals_per_run:
                break
        
        return filtered
    
    def _create_empty_result(
        self,
        execution_id: str,
        start_time: datetime,
    ) -> ExecutionResult:
        """Create empty result when no assets selected."""
        return ExecutionResult(
            execution_id=execution_id,
            timestamp=start_time,
            execution_duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
            assets_analyzed=0,
            signals_generated=0,
            errors=["No assets selected for analysis"],
        )
    
    async def close(self) -> None:
        """Close all connections."""
        await self.options_fetcher.close()
        await self.futures_fetcher.close()
        logger.info("Pipeline orchestrator closed")
