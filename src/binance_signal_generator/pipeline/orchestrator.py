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
from typing import Dict, List, Optional, Any, Tuple

from binance_signal_generator.config.loader import Config
from binance_signal_generator.data.options_fetcher import OptionsFetcher
from binance_signal_generator.data.futures_fetcher import FuturesFetcher
from binance_signal_generator.ranking.activity_scorer import ActivityScorer
from binance_signal_generator.ranking.asset_selector import AssetSelector, SelectionConfig
from binance_signal_generator.analysis.signal_scorer import SignalScorer
from binance_signal_generator.whale.whale_detector import WhaleDetector, WhaleDetectorConfig
from binance_signal_generator.whale.volume_analyzer import WhaleVolumeAnalyzer, VolumeAnalyzerConfig
from binance_signal_generator.analysis.wall_detector import WallDetector, WallDetectorConfig
from binance_signal_generator.analysis.gamma_exposure import GammaExposureCalculator, GammaExposureConfig
from binance_signal_generator.analysis.sentiment import SentimentAnalyzer, SentimentConfig
from binance_signal_generator.analysis.iv_analyzer import IVAnalyzer, IVConfig
from binance_signal_generator.analysis.pcr_analyzer import PCRAnalyzer, PCRConfig
from binance_signal_generator.analysis.oi_analyzer import OIAnalyzer, OIConfig
from binance_signal_generator.analysis.max_pain import MaxPainCalculator, MaxPainConfig
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
        
        # Initialize whale volume analyzer for advanced analysis
        self.whale_volume_analyzer = WhaleVolumeAnalyzer(VolumeAnalyzerConfig())
        
        # Initialize wall detector
        self.wall_detector = WallDetector(WallDetectorConfig())
        self.sr_calculator = SRLevelCalculator(SRLevelConfig())
        
        # Initialize gamma exposure calculator
        self.gamma_calculator = GammaExposureCalculator(GammaExposureConfig())
        
        # Initialize sentiment analyzer for L/S ratios and funding rates
        self.sentiment_analyzer = SentimentAnalyzer(SentimentConfig())
        
        # Initialize advanced analysis modules for detailed metrics
        self.iv_analyzer = IVAnalyzer(IVConfig())
        self.pcr_analyzer = PCRAnalyzer(PCRConfig())
        self.oi_analyzer = OIAnalyzer(OIConfig())
        self.max_pain_calculator = MaxPainCalculator(MaxPainConfig())
        
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
            
            # Parse block trades into WhaleTrade objects for advanced volume analysis
            whale_trades = self.whale_detector.parse_block_trades_to_whale_trades(
                block_trades, symbol
            )
            
            # Run advanced whale volume analysis
            whale_volume_analysis = self.whale_volume_analyzer.analyze(
                whale_trades, whale_analysis
            )
            
            logger.debug(
                f"Whale volume analysis for {symbol}: "
                f"pattern={whale_volume_analysis.get('time_pattern', {}).get('pattern', 'N/A')}, "
                f"sentiment={whale_volume_analysis.get('summary', {}).get('overall_sentiment', 'N/A')}, "
                f"trades={len(whale_trades)}"
            )
            
            # Run wall detection
            wall_analysis = self.wall_detector.detect(options_chain)
            
            # Run gamma exposure analysis for dealer hedging levels
            gamma_analysis = self.gamma_calculator.calculate(options_chain)
            
            # Fetch sentiment data (L/S ratios + funding rate history)
            # Weight: 0 (L/S ratios) + 5 (funding rate) = 5 total
            sentiment_data = await self.futures_fetcher.get_sentiment_data(symbol)
            self._api_calls_made += 5  # Approximate: 0 + 0 + 5
            
            # Run sentiment analysis
            # BUG FIX (Bug #5): Pass price_change_pct so sentiment can use
            # trend-aware logic instead of always generating LONG in moderate conditions
            sentiment_analysis = self.sentiment_analyzer.analyze(
                symbol=symbol,
                top_trader_position_data=sentiment_data.get("top_trader_position", []),
                top_trader_account_data=sentiment_data.get("top_trader_account", []),
                funding_rate_data=sentiment_data.get("funding_rate_history", []),
                price_change_pct=futures_data.price_change_pct,
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
            
            # Run advanced analysis methods for detailed metrics FIRST
            # These are now used in signal scoring (Section 6.5 implementation)
            
            # IMPROVED: IV-003 - IV Term Structure analysis
            # Analyze IV term structure from the chain data
            # For proper multi-expiry analysis, would need to fetch chains by individual expiry
            iv_term_structure = self.iv_analyzer.analyze_term_structure_from_chain(options_chain)
            iv_term_signal, iv_term_confidence, iv_term_details = self.iv_analyzer.generate_term_structure_signal(iv_term_structure)
            
            logger.debug(
                f"IV Term Structure for {symbol}: shape={iv_term_structure.get('shape', 'N/A')}, "
                f"signal={iv_term_signal.value}, confidence={iv_term_confidence}"
            )
            
            # 2. PCR by Strike Analysis
            pcr_by_strike = self.pcr_analyzer.analyze_pcr_by_strike(options_chain)
            
            # 3. OI Distribution Analysis
            oi_distribution = self.oi_analyzer.get_oi_distribution(options_chain)
            
            # 4. Max Pain Distribution
            pain_distribution = self.max_pain_calculator.get_pain_distribution(options_chain)
            
            # 5. Wall to S/R Conversion (already done via wall_analysis.support_levels/resistance_levels)
            wall_sr_levels = self.wall_detector.get_sr_from_walls(wall_analysis) if wall_analysis else ([], [])
            
            # 6. OI Flow Analysis (requires historical data - use futures data)
            oi_flow = None
            if futures_data and futures_data.open_interest > 0:
                # BUG FIX (Bug #2): FuturesData now has open_interest_change_pct field.
                # Previously used hasattr() which always returned False, making OI flow
                # always NEUTRAL and wasting 12% signal weight.
                oi_change_pct = futures_data.open_interest_change_pct
                price_change_pct = futures_data.price_change_pct

                # Determine detailed flow type using both OI change and price change
                # BUG FIX: Previously only used OI direction (BUILDING/UNWINDING) and
                # hardcoded LONG for BUILDING. Now correctly classifies:
                #   OI UP + Price UP   = LONG_BUILDUP   (new longs being created)
                #   OI UP + Price DOWN = SHORT_BUILDUP  (new shorts being created)
                #   OI DOWN + Price UP = SHORT_COVERING (shorts closing out)
                #   OI DOWN + Price DOWN = LONG_UNWINDING (longs liquidating)
                #
                # BUG FIX (Bug #11): Lowered OI change threshold from ±5% to ±2%.
                # The previous ±5% threshold was too high — daily BTC OI changes under
                # 5% are very common (e.g., OI going from 20,000 to 20,800 = +4% was
                # classified as NEUTRAL). This meant the OI flow signal (12% weight)
                # frequently returned NEUTRAL, wasting its weight allocation.
                # ±2% captures meaningful OI flow changes while filtering noise.
                # For intraday mode, the threshold is further halved to ±1% since
                # OI changes over hours are smaller than daily.
                oi_threshold = 2.0  # Default: ±2% for daily
                intraday_config = getattr(self.config, 'intraday', None)
                if intraday_config and intraday_config.enabled:
                    oi_threshold = 1.0  # ±1% for intraday (smaller OI changes over hours)
                
                oi_building = oi_change_pct > oi_threshold
                oi_unwinding = oi_change_pct < -oi_threshold
                price_up = price_change_pct > 0
                price_down = price_change_pct < 0

                if oi_building and price_up:
                    flow_type = "LONG_BUILDUP"
                    flow_direction = "BUILDING"
                elif oi_building and price_down:
                    flow_type = "SHORT_BUILDUP"
                    flow_direction = "BUILDING"
                elif oi_unwinding and price_up:
                    flow_type = "SHORT_COVERING"
                    flow_direction = "UNWINDING"
                elif oi_unwinding and price_down:
                    flow_type = "LONG_UNWINDING"
                    flow_direction = "UNWINDING"
                else:
                    flow_type = "NEUTRAL"
                    flow_direction = "STABLE"

                oi_flow = {
                    "current_oi": futures_data.open_interest,
                    "oi_change_estimated": oi_change_pct,
                    "price_change_pct": price_change_pct,
                    "flow_direction": flow_direction,
                    "flow_type": flow_type,
                }
            
            # Create advanced_metrics dict for signal scoring
            # IMPROVED: IV-003 - Added IV term structure to advanced metrics
            advanced_metrics = {
                "pcr_by_strike": pcr_by_strike,
                "oi_distribution": oi_distribution,
                "pain_distribution": pain_distribution,
                "oi_flow": oi_flow,
                "iv_term_structure": iv_term_structure,
            }
            
            # Run Options analysis with sentiment, gamma exposure, and advanced metrics
            options_signal = self.signal_scorer.analyze(
                options_chain, 
                sentiment_analysis,
                gamma_analysis,
                advanced_metrics=advanced_metrics,
                whale_volume_analysis=whale_volume_analysis,
                wall_analysis=wall_analysis,
            )
            
            # Debug: Log advanced analysis results
            logger.debug(
                f"Advanced analysis for {symbol}: "
                f"pcr_strikes={pcr_by_strike.get('put_heavy_count', 0)} put-heavy, "
                f"{pcr_by_strike.get('call_heavy_count', 0)} call-heavy, "
                f"oi_total={oi_distribution.get('total_oi', 0)}, "
                f"pain_max={pain_distribution.get('max_pain_strike', 0):.0f}"
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
                    whale_volume_analysis=whale_volume_analysis,
                    wall_analysis=wall_analysis,
                    gamma_analysis=gamma_analysis,
                    sentiment_analysis=sentiment_analysis,
                    pcr_by_strike=pcr_by_strike,
                    oi_distribution=oi_distribution,
                    pain_distribution=pain_distribution,
                    oi_flow=oi_flow,
                    wall_sr_levels=wall_sr_levels,
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
        whale_volume_analysis: Optional[Dict[str, Any]] = None,
        wall_analysis: Optional[Any] = None,
        gamma_analysis: Optional[Any] = None,
        sentiment_analysis: Optional[Any] = None,
        pcr_by_strike: Optional[Dict[str, Any]] = None,
        oi_distribution: Optional[Dict[str, Any]] = None,
        pain_distribution: Optional[Dict[str, Any]] = None,
        oi_flow: Optional[Dict[str, Any]] = None,
        wall_sr_levels: Optional[Tuple[List[float], List[float]]] = None,
    ) -> TradingSignal:
        """
        Create a complete trading signal.
        
        Args:
            asset: Ranked asset
            options_signal: Options analysis signal
            options_chain: Options chain data
            futures_data: Futures data
            whale_analysis: Whale activity analysis
            whale_volume_analysis: Advanced whale volume analysis
            wall_analysis: Wall detection analysis
            gamma_analysis: Gamma exposure analysis for dealer hedging levels
            sentiment_analysis: Sentiment analysis from L/S ratios and funding rates
            pcr_by_strike: PCR analysis by strike (from advanced analysis)
            oi_distribution: OI distribution across strikes (from advanced analysis)
            pain_distribution: Max pain distribution (from advanced analysis)
            oi_flow: OI flow analysis (from advanced analysis)
            wall_sr_levels: Support/resistance levels from walls (from advanced analysis)
            
        Returns:
            Complete TradingSignal
        """
        signal_id = f"SIG_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{asset.symbol}"
        
        # Determine signal strength
        # BUG FIX (Bug #7): Make whale confidence_boost directional.
        # Previously, confidence_boost was always positive and always added to
        # confidence, regardless of whether whale direction aligned with the
        # signal direction. This meant even if whales were selling (BEARISH) and
        # the signal was LONG, the confidence was boosted, reinforcing the wrong
        # direction.
        #
        # New logic:
        # - Whale BULLISH + Signal LONG → boost confidence (alignment)
        # - Whale BEARISH + Signal SHORT → boost confidence (alignment)
        # - Whale BULLISH + Signal SHORT → reduce confidence (opposition)
        # - Whale BEARISH + Signal LONG → reduce confidence (opposition)
        # - Whale NEUTRAL → no change
        confidence = options_signal.confidence
        if whale_analysis and whale_analysis.confidence_boost > 0:
            whale_dir = whale_analysis.whale_net_direction  # "BULLISH", "BEARISH", "NEUTRAL"
            signal_dir = options_signal.direction
            
            if whale_dir == "BULLISH" and signal_dir == SignalDirection.LONG:
                # Whales buying + LONG signal → aligned, boost confidence
                confidence = min(confidence + whale_analysis.confidence_boost, 1.0)
                logger.debug(
                    f"Whale boost: BULLISH whales align with LONG signal → "
                    f"+{whale_analysis.confidence_boost:.3f} confidence"
                )
            elif whale_dir == "BEARISH" and signal_dir == SignalDirection.SHORT:
                # Whales selling + SHORT signal → aligned, boost confidence
                confidence = min(confidence + whale_analysis.confidence_boost, 1.0)
                logger.debug(
                    f"Whale boost: BEARISH whales align with SHORT signal → "
                    f"+{whale_analysis.confidence_boost:.3f} confidence"
                )
            elif whale_dir == "BULLISH" and signal_dir == SignalDirection.SHORT:
                # Whales buying + SHORT signal → opposed, reduce confidence
                penalty = whale_analysis.confidence_boost * 0.6
                confidence = max(confidence - penalty, 0.0)
                logger.debug(
                    f"Whale penalty: BULLISH whales oppose SHORT signal → "
                    f"-{penalty:.3f} confidence"
                )
            elif whale_dir == "BEARISH" and signal_dir == SignalDirection.LONG:
                # Whales selling + LONG signal → opposed, reduce confidence
                penalty = whale_analysis.confidence_boost * 0.6
                confidence = max(confidence - penalty, 0.0)
                logger.debug(
                    f"Whale penalty: BEARISH whales oppose LONG signal → "
                    f"-{penalty:.3f} confidence"
                )
            # else: whale_dir == "NEUTRAL" → no adjustment
        
        if confidence >= 0.8:
            strength = SignalStrength.VERY_STRONG
        elif confidence >= 0.65:
            strength = SignalStrength.STRONG
        elif confidence >= 0.50:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK
        
        # Calculate entry zone (around current price)
        # FIX: Use ATR-based entry width instead of fixed 0.5%
        # Crypto volatility varies widely — 0.5% is too tight for volatile moves
        current_price = futures_data.price
        # Estimate ATR_pct from futures data if available
        atr_pct = 0.5  # Conservative fallback
        if hasattr(futures_data, 'klines') and futures_data.klines:
            # Use recent candle range as ATR proxy
            recent_candles = futures_data.klines[-14:] if len(futures_data.klines) >= 14 else futures_data.klines
            if recent_candles:
                atr_values = [(c.high - c.low) / c.close * 100 for c in recent_candles if c.close > 0]
                if atr_values:
                    atr_pct = sum(atr_values) / len(atr_values)
        entry_half_width = max(atr_pct * 0.5, 0.2) / 100  # Half ATR, min 0.2%
        entry_zone = EntryZone(
            min=current_price * (1 - entry_half_width),
            max=current_price * (1 + entry_half_width),
            ideal=current_price,
        )

        # =====================================================================
        # SMART SL/TP AND SUPPORT/RESISTANCE CALCULATION
        # Priority: Wall → PCR → Gamma → Percentage Fallback
        # =====================================================================

        # Max distances for intraday
        max_sl_distance_pct = self.config.output.stop_loss_max_distance_pct  # Default 3.0%
        max_level_distance_pct = 5.0  # For support/resistance levels

        # Build support levels with types (Priority: Wall → PCR → Gamma)
        support_levels = self._build_support_levels_with_type(
            wall_analysis=wall_analysis,
            pcr_by_strike=pcr_by_strike,
            gamma_analysis=gamma_analysis,
            spot_price=current_price,
            max_distance_pct=max_level_distance_pct,
        )

        # Build resistance levels with types (Priority: Wall → PCR → Gamma)
        resistance_levels = self._build_resistance_levels_with_type(
            wall_analysis=wall_analysis,
            pcr_by_strike=pcr_by_strike,
            gamma_analysis=gamma_analysis,
            spot_price=current_price,
            max_distance_pct=max_level_distance_pct,
        )

        # Calculate SMART Stop Loss with priority-based selection
        # Uses pre-built support/resistance levels (no double calculation)
        stop_loss = self._calculate_smart_stop_loss(
            current_price=current_price,
            direction=options_signal.direction,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            max_distance_pct=max_sl_distance_pct,
        )

        # Calculate SMART Take Profit levels with types
        take_profit_levels = self._calculate_smart_take_profit(
            current_price=current_price,
            direction=options_signal.direction,
            wall_analysis=wall_analysis,
            pcr_by_strike=pcr_by_strike,
            gamma_analysis=gamma_analysis,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            stop_loss=stop_loss,
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
        
        # Add advanced whale volume analysis
        if whale_volume_analysis:
            summary = whale_volume_analysis.get("summary", {})
            flow = whale_volume_analysis.get("flow", {})
            concentration = whale_volume_analysis.get("concentration", {})
            time_pattern = whale_volume_analysis.get("time_pattern", {})
            block_trades = whale_volume_analysis.get("block_trades", {})
            
            whale_metrics.update({
                # Summary
                "whale_volume_sentiment": summary.get("overall_sentiment", "NEUTRAL"),
                "whale_time_pattern": summary.get("time_pattern", "UNKNOWN"),
                "whale_aggressive_side": summary.get("aggressive_side", "UNKNOWN"),
                "whale_is_concentrated": summary.get("is_concentrated", False),
                "whale_block_count": summary.get("block_count", 0),
                "whale_block_sentiment": summary.get("block_sentiment", "NEUTRAL"),
                
                # Flow analysis
                "whale_call_flow_net": flow.get("call_flow", {}).get("net", 0),
                "whale_put_flow_net": flow.get("put_flow", {}).get("net", 0),
                "whale_call_put_ratio": round(flow.get("call_put_ratio", 1.0), 2),
                
                # Concentration
                "whale_top_strike": concentration.get("top_strike"),
                "whale_top_strike_concentration": round(concentration.get("top_strike_concentration", 0), 3),
                
                # Block trades
                "whale_block_total_volume": block_trades.get("total_volume", 0),
                "whale_block_avg_size": round(block_trades.get("avg_size", 0), 2),
            })
        
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
        
        # Add advanced analysis metrics
        advanced_metrics = {}
        
        # PCR by Strike Analysis
        if pcr_by_strike:
            advanced_metrics["pcr_by_strike"] = {
                "put_heavy_count": pcr_by_strike.get("put_heavy_count", 0),
                "call_heavy_count": pcr_by_strike.get("call_heavy_count", 0),
                "avg_pcr": round(pcr_by_strike.get("avg_pcr", 1.0), 3),
                # Include top 5 strike PCRs for reference
                "top_strikes": [
                    {"strike": s["strike"], "pcr": round(s["pcr"], 3), "distance_pct": s["distance_from_spot"]}
                    for s in pcr_by_strike.get("strike_pcrs", [])[:5]
                ],
            }
        
        # OI Distribution Analysis
        if oi_distribution:
            advanced_metrics["oi_distribution"] = {
                "total_oi": oi_distribution.get("total_oi", 0),
                "total_call_oi": oi_distribution.get("total_call_oi", 0),
                "total_put_oi": oi_distribution.get("total_put_oi", 0),
                # Include top 5 strikes by total OI
                "top_oi_strikes": [
                    {"strike": s["strike"], "call_oi": s["call_oi"], "put_oi": s["put_oi"], "total_oi": s["total_oi"]}
                    for s in sorted(oi_distribution.get("strikes", []), key=lambda x: x.get("total_oi", 0), reverse=True)[:5]
                ],
            }
        
        # Max Pain Distribution
        if pain_distribution:
            advanced_metrics["pain_distribution"] = {
                "max_pain_strike": round(pain_distribution.get("max_pain_strike", 0), 2),
                "max_pain_value": round(pain_distribution.get("max_pain_value", 0), 2),
                "spot_price": round(pain_distribution.get("spot_price", 0), 2),
                # Include top 5 strikes by pain value for context
                "pain_gradient": [
                    {"strike": p["strike"], "pain": round(p["pain"], 2)}
                    for p in pain_distribution.get("distribution", [])[:5]
                ],
            }
        
        # OI Flow Analysis
        if oi_flow:
            advanced_metrics["oi_flow"] = oi_flow
        
        # Wall to S/R Conversion
        if wall_sr_levels:
            support_from_walls, resistance_from_walls = wall_sr_levels
            advanced_metrics["wall_sr_conversion"] = {
                "support_levels": support_from_walls[:5],
                "resistance_levels": resistance_from_walls[:5],
            }
        
        # Merge advanced metrics into options_metrics
        options_metrics.update(advanced_metrics)
        
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

    def _build_support_levels_with_type(
        self,
        wall_analysis: Optional[Any],
        pcr_by_strike: Optional[Dict[str, Any]],
        gamma_analysis: Optional[Any],
        spot_price: float,
        max_distance_pct: float = 5.0,
    ) -> List[Dict]:
        """
        Build support levels with type information.
        
        Priority: PUT_WALL → PCR_SUPPORT → GAMMA_SUPPORT
        
        Args:
            wall_analysis: Wall detection analysis
            pcr_by_strike: PCR analysis by strike
            gamma_analysis: Gamma exposure analysis
            spot_price: Current spot price
            max_distance_pct: Maximum distance for levels
            
        Returns:
            List of support level dicts with type field
        """
        all_levels = []  # List of (price, distance, type, strength, extra_data)
        
        # 1. Add PUT_WALLS (highest priority for support)
        if wall_analysis and wall_analysis.put_walls:
            for wall in wall_analysis.put_walls:
                distance_pct = (spot_price - wall.strike) / spot_price * 100
                if 0 < distance_pct <= max_distance_pct * 2:  # Allow farther walls in levels
                    all_levels.append((
                        wall.strike,
                        round(distance_pct, 2),
                        "PUT_WALL",
                        wall.strength_score,
                        {"oi": wall.open_interest, "oi_concentration": round(wall.oi_percentage * 100, 2)}
                    ))
        
        # 2. Add PCR_SUPPORT (put-heavy strikes)
        if pcr_by_strike:
            strike_pcrs = pcr_by_strike.get("strike_pcrs", [])
            for strike_info in strike_pcrs:
                strike = strike_info.get("strike", 0)
                pcr = strike_info.get("pcr", 1.0)
                
                # Put-heavy strikes (PCR >= 2.0) below spot = support
                if strike < spot_price and pcr >= 2.0:
                    distance_pct = (spot_price - strike) / spot_price * 100
                    if 0 < distance_pct <= max_distance_pct:
                        strength = min(pcr / 10.0, 1.0)  # Higher PCR = stronger support
                        all_levels.append((
                            strike,
                            round(distance_pct, 2),
                            "PCR_SUPPORT",
                            strength,
                            {"pcr": round(pcr, 2)}
                        ))
        
        # 3. Add GAMMA_SUPPORT (dealer hedging support)
        if gamma_analysis and gamma_analysis.gex_support_levels:
            for gamma_level in gamma_analysis.gex_support_levels:
                distance_pct = (spot_price - gamma_level.strike) / spot_price * 100
                if 0 < distance_pct <= max_distance_pct:
                    all_levels.append((
                        gamma_level.strike,
                        round(distance_pct, 2),
                        "GAMMA_SUPPORT",
                        gamma_level.strength,
                        {"gex": round(gamma_level.gex_value, 2)}
                    ))
        
        # Sort by distance (closest first)
        all_levels.sort(key=lambda x: x[1])
        
        # Remove duplicates (keep the one with highest priority/strength)
        seen_prices = {}
        for level in all_levels:
            price_key = round(level[0], 0)
            if price_key not in seen_prices:
                seen_prices[price_key] = level
            else:
                # Keep the one with higher strength
                if level[3] > seen_prices[price_key][3]:
                    seen_prices[price_key] = level
        
        # Build final list with level numbers
        unique_levels = list(seen_prices.values())
        unique_levels.sort(key=lambda x: x[1])  # Sort by distance
        
        result = []
        for i, (price, distance, level_type, strength, extra) in enumerate(unique_levels[:5]):
            level_dict = {
                "level": i + 1,
                "price": price,
                "distance_pct": distance,
                "type": level_type,
                "strength": round(strength, 2),
            }
            level_dict.update(extra)
            result.append(level_dict)
        
        return result

    def _build_resistance_levels_with_type(
        self,
        wall_analysis: Optional[Any],
        pcr_by_strike: Optional[Dict[str, Any]],
        gamma_analysis: Optional[Any],
        spot_price: float,
        max_distance_pct: float = 5.0,
    ) -> List[Dict]:
        """
        Build resistance levels with type information.
        
        Priority: CALL_WALL → PCR_RESISTANCE → GAMMA_RESISTANCE
        
        Args:
            wall_analysis: Wall detection analysis
            pcr_by_strike: PCR analysis by strike
            gamma_analysis: Gamma exposure analysis
            spot_price: Current spot price
            max_distance_pct: Maximum distance for levels
            
        Returns:
            List of resistance level dicts with type field
        """
        all_levels = []  # List of (price, distance, type, strength, extra_data)
        
        # 1. Add CALL_WALLS (highest priority for resistance)
        if wall_analysis and wall_analysis.call_walls:
            for wall in wall_analysis.call_walls:
                distance_pct = (wall.strike - spot_price) / spot_price * 100
                if 0 < distance_pct <= max_distance_pct * 2:  # Allow farther walls in levels
                    all_levels.append((
                        wall.strike,
                        round(distance_pct, 2),
                        "CALL_WALL",
                        wall.strength_score,
                        {"oi": wall.open_interest, "oi_concentration": round(wall.oi_percentage * 100, 2)}
                    ))
        
        # 2. Add PCR_RESISTANCE (call-heavy strikes)
        if pcr_by_strike:
            strike_pcrs = pcr_by_strike.get("strike_pcrs", [])
            for strike_info in strike_pcrs:
                strike = strike_info.get("strike", 0)
                pcr = strike_info.get("pcr", 1.0)
                
                # Call-heavy strikes (PCR <= 0.5) above spot = resistance
                if strike > spot_price and pcr <= 0.5:
                    distance_pct = (strike - spot_price) / spot_price * 100
                    if 0 < distance_pct <= max_distance_pct:
                        strength = min((1.0 - pcr) * 2, 1.0)  # Lower PCR = stronger resistance
                        all_levels.append((
                            strike,
                            round(distance_pct, 2),
                            "PCR_RESISTANCE",
                            strength,
                            {"pcr": round(pcr, 2)}
                        ))
        
        # 3. Add GAMMA_RESISTANCE (dealer hedging resistance)
        if gamma_analysis and gamma_analysis.gex_resistance_levels:
            for gamma_level in gamma_analysis.gex_resistance_levels:
                distance_pct = (gamma_level.strike - spot_price) / spot_price * 100
                if 0 < distance_pct <= max_distance_pct * 2:  # Allow farther gamma levels
                    all_levels.append((
                        gamma_level.strike,
                        round(distance_pct, 2),
                        "GAMMA_RESISTANCE",
                        gamma_level.strength,
                        {"gex": round(gamma_level.gex_value, 2)}
                    ))
        
        # Sort by distance (closest first)
        all_levels.sort(key=lambda x: x[1])
        
        # Remove duplicates (keep the one with highest priority/strength)
        seen_prices = {}
        for level in all_levels:
            price_key = round(level[0], 0)
            if price_key not in seen_prices:
                seen_prices[price_key] = level
            else:
                # Keep the one with higher strength
                if level[3] > seen_prices[price_key][3]:
                    seen_prices[price_key] = level
        
        # Build final list with level numbers
        unique_levels = list(seen_prices.values())
        unique_levels.sort(key=lambda x: x[1])  # Sort by distance
        
        result = []
        for i, (price, distance, level_type, strength, extra) in enumerate(unique_levels[:5]):
            level_dict = {
                "level": i + 1,
                "price": price,
                "distance_pct": distance,
                "type": level_type,
                "strength": round(strength, 2),
            }
            level_dict.update(extra)
            result.append(level_dict)
        
        return result

    def _calculate_smart_stop_loss(
        self,
        current_price: float,
        direction: SignalDirection,
        support_levels: List[Dict],
        resistance_levels: List[Dict],
        max_distance_pct: float = 3.0,
    ) -> StopLoss:
        """
        Calculate smart stop loss using pre-built support/resistance levels.
        
        No double calculation - reuses levels already built by:
        - _build_support_levels_with_type()
        - _build_resistance_levels_with_type()
        
        Priority:
        1. PUT_WALL / CALL_WALL (strongest)
        2. PCR_SUPPORT / PCR_RESISTANCE
        3. GAMMA_SUPPORT / GAMMA_RESISTANCE
        4. PERCENTAGE fallback (2%)
        
        Args:
            current_price: Current asset price
            direction: Signal direction (LONG/SHORT)
            support_levels: Pre-built support levels with type and strength
            resistance_levels: Pre-built resistance levels with type and strength
            max_distance_pct: Maximum acceptable SL distance
            
        Returns:
            StopLoss with smart price selection
        """
        sl_candidates = []  # List of (price, distance_pct, type, confidence)
        
        if direction == SignalDirection.LONG:
            # For LONG: SL below price (use support levels)
            for level in support_levels:
                distance_pct = level.get("distance_pct", 0)
                if 0 < distance_pct <= max_distance_pct:
                    level_type = level.get("type", "SUPPORT")
                    strength = level.get("strength", 0.5)
                    sl_candidates.append((
                        level["price"],
                        distance_pct,
                        level_type,
                        strength,
                    ))
        
        else:  # SHORT
            # For SHORT: SL above price (use resistance levels)
            for level in resistance_levels:
                distance_pct = level.get("distance_pct", 0)
                if 0 < distance_pct <= max_distance_pct:
                    level_type = level.get("type", "RESISTANCE")
                    strength = level.get("strength", 0.5)
                    sl_candidates.append((
                        level["price"],
                        distance_pct,
                        level_type,
                        strength,
                    ))
        
        # Select best SL candidate (highest confidence/strength within max distance)
        if sl_candidates:
            # Sort by confidence/strength (highest first)
            sl_candidates.sort(key=lambda x: x[3], reverse=True)
            best_sl = sl_candidates[0]
            
            logger.debug(
                f"Smart SL selected: price={best_sl[0]:.2f}, distance={best_sl[1]:.2f}%, "
                f"type={best_sl[2]}, confidence={best_sl[3]:.2f} "
                f"(had {len(sl_candidates)} candidates)"
            )
            
            return StopLoss(
                price=best_sl[0],
                type=best_sl[2],
                distance_pct=round(best_sl[1], 2),
                source_strike=best_sl[0],
                confidence=round(best_sl[3], 2),
            )
        
        # FALLBACK: Percentage-based (2% for intraday)
        logger.debug(f"No smart SL found within {max_distance_pct}%, using 2% fallback")
        if direction == SignalDirection.LONG:
            sl_price = current_price * 0.98
        else:
            sl_price = current_price * 1.02
        
        return StopLoss(
            price=sl_price,
            type="PERCENTAGE",
            distance_pct=2.0,
            source_strike=None,
            confidence=0.5,
        )

    def _calculate_smart_take_profit(
        self,
        current_price: float,
        direction: SignalDirection,
        wall_analysis: Optional[Any],
        pcr_by_strike: Optional[Dict[str, Any]],
        gamma_analysis: Optional[Any],
        support_levels: List[Dict],
        resistance_levels: List[Dict],
        stop_loss: Optional[StopLoss] = None,
    ) -> List[TakeProfitLevel]:
        """
        Calculate smart take profit levels with type information.
        
        For LONG: TP at resistance levels (CALL_WALL, PCR_RESISTANCE, GAMMA_RESISTANCE)
        For SHORT: TP at support levels (PUT_WALL, PCR_SUPPORT, GAMMA_SUPPORT)
        
        Args:
            current_price: Current asset price
            direction: Signal direction (LONG/SHORT)
            wall_analysis: Wall detection analysis
            pcr_by_strike: PCR analysis by strike
            gamma_analysis: Gamma exposure analysis
            support_levels: Pre-built support levels
            resistance_levels: Pre-built resistance levels
            stop_loss: Computed stop loss (used for risk-reward ratio calculation)
            
        Returns:
            List of TakeProfitLevel with smart targets
        """
        levels = []
        max_tp_distance_pct = 5.0  # Max TP distance for intraday
        tp_candidates = []  # List of (price, distance_pct, type, strength)
        
        if direction == SignalDirection.LONG:
            # For LONG: TP at resistance levels above price
            
            # Use pre-built resistance levels
            for res in resistance_levels:
                tp_distance = res.get("distance_pct", 0)
                if 0 < tp_distance <= max_tp_distance_pct:
                    tp_candidates.append((
                        res["price"],
                        tp_distance,
                        res.get("type", "RESISTANCE"),
                        res.get("gex", res.get("oi", 0)) / 10000 if res.get("gex") else res.get("oi", 0) / 100
                    ))
        
        else:  # SHORT
            # For SHORT: TP at support levels below price
            
            # Use pre-built support levels
            for sup in support_levels:
                tp_distance = sup.get("distance_pct", 0)
                if 0 < tp_distance <= max_tp_distance_pct:
                    tp_candidates.append((
                        sup["price"],
                        tp_distance,
                        sup.get("type", "SUPPORT"),
                        sup.get("gex", sup.get("oi", 0)) / 10000 if sup.get("gex") else sup.get("oi", 0) / 100
                    ))
        
        # Sort by distance (closest first for TP1)
        tp_candidates.sort(key=lambda x: x[1])
        
        # Remove duplicates
        seen_prices = set()
        unique_candidates = []
        for candidate in tp_candidates:
            price_key = round(candidate[0], 0)
            if price_key not in seen_prices:
                seen_prices.add(price_key)
                unique_candidates.append(candidate)
        
        # Create TP levels (up to 3)
        for i, candidate in enumerate(unique_candidates[:3]):
            tp_price = candidate[0]
            tp_distance = candidate[1]
            tp_type = candidate[2]
            
            # FIX: RR ratio based on actual SL distance, not hardcoded 2%
            # The stop_loss is passed from the caller where it's already computed
            sl_distance = stop_loss.distance_pct if stop_loss and stop_loss.distance_pct > 0 else 2.0
            rr_ratio = round(tp_distance / sl_distance, 1)
            
            levels.append(TakeProfitLevel(
                level=i + 1,
                price=tp_price,
                ratio=rr_ratio,
                distance_pct=round(tp_distance, 2),
                type=tp_type,
                source=f"{tp_type.lower()}_levels",
            ))
        
        # Fallback to percentage-based if no wall-based levels found
        if not levels:
            logger.debug("No wall-based TP found, using percentage fallback")
            if direction == SignalDirection.LONG:
                tp_configs = [
                    (1, 1.5, 0.015),
                    (2, 3.0, 0.030),
                    (3, 5.0, 0.050),
                ]
                for level, ratio, distance in tp_configs:
                    levels.append(TakeProfitLevel(
                        level=level,
                        price=current_price * (1 + distance),
                        ratio=ratio,
                        distance_pct=distance * 100,
                        type="PERCENTAGE",
                        source="percentage_fallback",
                    ))
            else:
                tp_configs = [
                    (1, 1.5, 0.015),
                    (2, 3.0, 0.030),
                    (3, 5.0, 0.050),
                ]
                for level, ratio, distance in tp_configs:
                    levels.append(TakeProfitLevel(
                        level=level,
                        price=current_price * (1 - distance),
                        ratio=ratio,
                        distance_pct=distance * 100,
                        type="PERCENTAGE",
                        source="percentage_fallback",
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
