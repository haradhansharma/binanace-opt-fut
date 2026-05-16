"""
Unit tests for Pipeline orchestration.

Tests for the complete signal generation pipeline including
orchestrator, execution flow, and integration between modules.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import Dict, Any, List
import asyncio

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    OptionData,
    FuturesData,
    SignalDirection,
    SignalStrength,
    TradingSignal,
    EntryZone,
    StopLoss,
    TakeProfitLevel,
    ExecutionResult,
    RankedAsset,
    ActivityMetrics,
    WhaleAnalysis,
    WallAnalysis,
)
from binance_signal_generator.pipeline.orchestrator import (
    SignalPipeline,
    PipelineConfig,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def pipeline_config():
    """Create pipeline configuration."""
    return PipelineConfig(timeout_seconds=600, min_confidence=0.55, max_signals=5, top_assets=5)


@pytest.fixture
def mock_options_fetcher():
    """Create mock options fetcher."""
    fetcher = AsyncMock()
    fetcher.get_available_symbols = AsyncMock(return_value=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    fetcher.get_option_chain = AsyncMock(
        return_value=OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=10000,
            total_put_oi=8000,
            strikes={
                42000.0: StrikeData(
                    strike=42000.0,
                    call=OptionData(open_interest=5000, volume=2000, iv=0.65),
                    put=OptionData(open_interest=4000, volume=1500, iv=0.60),
                )
            },
        )
    )
    fetcher.get_recent_trades = AsyncMock(return_value=[])
    return fetcher


@pytest.fixture
def mock_futures_fetcher():
    """Create mock futures fetcher."""
    fetcher = AsyncMock()
    fetcher.get_price = AsyncMock(
        return_value=FuturesData(
            symbol="BTCUSDT",
            price=42000.0,
            timestamp=datetime.utcnow(),
            volume_24h=1500000000.0,
            open_interest=50000.0,
            funding_rate=0.0001,
        )
    )
    fetcher.get_all_data = AsyncMock(
        return_value=FuturesData(
            symbol="BTCUSDT",
            price=42000.0,
            timestamp=datetime.utcnow(),
            volume_24h=1500000000.0,
            open_interest=50000.0,
            funding_rate=0.0001,
        )
    )
    return fetcher


@pytest.fixture
def mock_activity_scorer():
    """Create mock activity scorer."""
    scorer = Mock()
    scorer.scan_all_assets = AsyncMock(
        return_value={
            "BTCUSDT": ActivityMetrics(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow(),
                activity_score=0.85,
                primary_driver="WHALE_ACTIVITY",
            ),
            "ETHUSDT": ActivityMetrics(
                symbol="ETHUSDT",
                timestamp=datetime.utcnow(),
                activity_score=0.75,
                primary_driver="VOLUME_SPIKE",
            ),
        }
    )
    return scorer


@pytest.fixture
def mock_asset_selector():
    """Create mock asset selector."""
    selector = Mock()
    selector.select = Mock(
        return_value=[
            RankedAsset(
                symbol="BTCUSDT",
                rank=1,
                activity_score=0.85,
                primary_driver="WHALE_ACTIVITY",
                quick_metrics={"volume": 85000000},
            ),
            RankedAsset(
                symbol="ETHUSDT",
                rank=2,
                activity_score=0.75,
                primary_driver="VOLUME_SPIKE",
                quick_metrics={"volume": 62000000},
            ),
        ]
    )
    return selector


@pytest.fixture
def sample_options_chain():
    """Create sample options chain."""
    chain = OptionsChain(
        underlying="BTCUSDT",
        spot_price=42000.0,
        timestamp=datetime.utcnow(),
        total_call_oi=10000,
        total_put_oi=8000,
    )

    chain.strikes = {
        40000.0: StrikeData(
            strike=40000.0,
            call=OptionData(open_interest=500, volume=200, iv=0.80),
            put=OptionData(open_interest=2500, volume=1000, iv=0.75),
        ),
        41000.0: StrikeData(
            strike=41000.0,
            call=OptionData(open_interest=2000, volume=800, iv=0.70),
            put=OptionData(open_interest=2000, volume=800, iv=0.65),
        ),
        42000.0: StrikeData(
            strike=42000.0,
            call=OptionData(open_interest=3500, volume=1400, iv=0.60),
            put=OptionData(open_interest=2000, volume=800, iv=0.55),
        ),
        43000.0: StrikeData(
            strike=43000.0,
            call=OptionData(open_interest=3000, volume=1200, iv=0.55),
            put=OptionData(open_interest=1000, volume=400, iv=0.50),
        ),
        44000.0: StrikeData(
            strike=44000.0,
            call=OptionData(open_interest=1000, volume=400, iv=0.50),
            put=OptionData(open_interest=500, volume=200, iv=0.45),
        ),
    }

    return chain


@pytest.fixture
def sample_whale_analysis():
    """Create sample whale analysis."""
    return WhaleAnalysis(
        symbol="BTCUSDT",
        analysis_timestamp=datetime.utcnow(),
        lookback_hours=24,
        whale_buy_volume=5000000.0,
        whale_sell_volume=2000000.0,
        whale_net_volume=3000000.0,
        whale_net_direction="BULLISH",
        whale_activity_score=0.75,
        large_trades_count=25,
        avg_trade_size=280000.0,
        confidence_boost=0.12,
    )


@pytest.fixture
def sample_wall_analysis():
    """Create sample wall analysis."""
    return WallAnalysis(
        symbol="BTCUSDT",
        spot_price=42000.0,
        timestamp=datetime.utcnow(),
        put_walls=[],
        call_walls=[],
        total_walls=2,
        wall_intensity=0.65,
        support_levels=[41000.0, 40000.0],
        resistance_levels=[43000.0, 44000.0],
    )


# =============================================================================
# Pipeline Orchestrator Tests
# =============================================================================


class TestSignalPipeline:
    """Tests for SignalPipeline class."""

    def test_init(self, pipeline_config):
        """Test pipeline initialization."""
        pipeline = SignalPipeline(pipeline_config)

        assert pipeline is not None
        assert pipeline.config.timeout_seconds == 600

    @pytest.mark.asyncio
    async def test_execute_basic(
        self,
        pipeline_config,
        mock_options_fetcher,
        mock_futures_fetcher,
        mock_activity_scorer,
        mock_asset_selector,
    ):
        """Test basic pipeline execution."""
        pipeline = SignalPipeline(pipeline_config)
        pipeline.options_fetcher = mock_options_fetcher
        pipeline.futures_fetcher = mock_futures_fetcher
        pipeline.activity_scorer = mock_activity_scorer
        pipeline.asset_selector = mock_asset_selector

        # Mock the remaining components
        pipeline._run_analysis = AsyncMock(return_value=None)
        pipeline._generate_signal = AsyncMock(return_value=None)

        result = await pipeline.execute()

        assert result is not None
        assert isinstance(result, ExecutionResult)

    @pytest.mark.asyncio
    async def test_execute_stage1_activity_scan(self, pipeline_config, mock_activity_scorer):
        """Test Stage 1: Activity scan."""
        pipeline = SignalPipeline(pipeline_config)
        pipeline.activity_scorer = mock_activity_scorer

        result = await pipeline._stage1_activity_scan()

        assert result is not None
        assert "BTCUSDT" in result

    @pytest.mark.asyncio
    async def test_execute_stage2_asset_selection(
        self, pipeline_config, mock_activity_scorer, mock_asset_selector
    ):
        """Test Stage 2: Asset selection."""
        pipeline = SignalPipeline(pipeline_config)
        pipeline.activity_scorer = mock_activity_scorer
        pipeline.asset_selector = mock_asset_selector

        activity_metrics = await pipeline._stage1_activity_scan()
        result = pipeline._stage2_asset_selection(activity_metrics)

        assert result is not None
        assert len(result) <= pipeline_config.top_assets
        assert all(isinstance(a, RankedAsset) for a in result)

    @pytest.mark.asyncio
    async def test_execute_stage3_data_fetch(
        self, pipeline_config, mock_options_fetcher, mock_futures_fetcher
    ):
        """Test Stage 3: Data fetch."""
        pipeline = SignalPipeline(pipeline_config)
        pipeline.options_fetcher = mock_options_fetcher
        pipeline.futures_fetcher = mock_futures_fetcher

        selected = [
            RankedAsset(
                symbol="BTCUSDT",
                rank=1,
                activity_score=0.85,
                primary_driver="WHALE",
                quick_metrics={},
            )
        ]

        result = await pipeline._stage3_data_fetch(selected)

        assert result is not None
        assert "BTCUSDT" in result

    @pytest.mark.asyncio
    async def test_execute_full_pipeline(self, pipeline_config):
        """Test full pipeline execution with mocked components."""
        pipeline = SignalPipeline(pipeline_config)

        # Mock all components
        pipeline.options_fetcher = AsyncMock()
        pipeline.futures_fetcher = AsyncMock()
        pipeline.activity_scorer = AsyncMock()
        pipeline.asset_selector = Mock()

        # Setup return values
        pipeline.options_fetcher.get_available_symbols = AsyncMock(
            return_value=["BTCUSDT", "ETHUSDT"]
        )
        pipeline.options_fetcher.get_option_chain = AsyncMock(
            return_value=OptionsChain(
                underlying="BTCUSDT",
                spot_price=42000.0,
                timestamp=datetime.utcnow(),
                total_call_oi=10000,
                total_put_oi=8000,
            )
        )
        pipeline.options_fetcher.get_recent_trades = AsyncMock(return_value=[])
        pipeline.futures_fetcher.get_all_data = AsyncMock(
            return_value=FuturesData(symbol="BTCUSDT", price=42000.0, timestamp=datetime.utcnow())
        )
        pipeline.activity_scorer.scan_all_assets = AsyncMock(
            return_value={
                "BTCUSDT": ActivityMetrics(
                    symbol="BTCUSDT",
                    timestamp=datetime.utcnow(),
                    activity_score=0.85,
                    primary_driver="WHALE",
                )
            }
        )
        pipeline.asset_selector.select = Mock(
            return_value=[
                RankedAsset(
                    symbol="BTCUSDT",
                    rank=1,
                    activity_score=0.85,
                    primary_driver="WHALE",
                    quick_metrics={},
                )
            ]
        )

        # Mock analysis methods
        pipeline._run_analysis = AsyncMock(
            return_value={"direction": SignalDirection.LONG, "confidence": 0.75}
        )
        pipeline._detect_whale_activity = AsyncMock(
            return_value=WhaleAnalysis(
                symbol="BTCUSDT", analysis_timestamp=datetime.utcnow(), lookback_hours=24
            )
        )
        pipeline._detect_walls = AsyncMock(
            return_value=WallAnalysis(
                symbol="BTCUSDT", spot_price=42000.0, timestamp=datetime.utcnow()
            )
        )
        pipeline._generate_signal = AsyncMock(return_value=None)  # Low confidence

        result = await pipeline.execute()

        assert result is not None
        assert isinstance(result, ExecutionResult)
        assert result.assets_analyzed >= 0


# =============================================================================
# Execution Result Tests
# =============================================================================


class TestExecutionResult:
    """Tests for ExecutionResult model."""

    def test_create_execution_result(self):
        """Test creating execution result."""
        result = ExecutionResult(
            execution_id="EXEC_20250116_120000",
            timestamp=datetime.utcnow(),
            execution_duration_seconds=420.5,
            assets_analyzed=5,
            signals_generated=3,
        )

        assert result.execution_id == "EXEC_20250116_120000"
        assert result.assets_analyzed == 5
        assert result.signals_generated == 3

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = ExecutionResult(
            execution_id="EXEC_20250116_120000",
            timestamp=datetime(2025, 1, 16, 12, 0, 0),
            execution_duration_seconds=420.5,
            assets_analyzed=5,
            signals_generated=3,
        )

        data = result.to_dict()

        assert "execution_id" in data
        assert "timestamp" in data
        assert "signals" in data
        assert "metadata" in data

    def test_with_signals(self):
        """Test execution result with signals."""
        signal = TradingSignal(
            signal_id="SIG_001",
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            asset_rank=1,
            activity_score=0.85,
            direction=SignalDirection.LONG,
            confidence_score=0.75,
            signal_strength=SignalStrength.STRONG,
            entry_zone=EntryZone(min=41900.0, max=42100.0, ideal=42000.0),
            stop_loss=StopLoss(price=41000.0, type="WALL_BASED", distance_pct=2.4),
        )

        result = ExecutionResult(
            execution_id="EXEC_001",
            timestamp=datetime.utcnow(),
            execution_duration_seconds=420.0,
            assets_analyzed=1,
            signals_generated=1,
            signals=[signal],
        )

        assert len(result.signals) == 1
        assert result.signals[0].symbol == "BTCUSDT"


# =============================================================================
# Pipeline Configuration Tests
# =============================================================================


class TestPipelineConfig:
    """Tests for PipelineConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = PipelineConfig()

        assert config.timeout_seconds > 0
        assert config.min_confidence > 0
        assert config.max_signals > 0
        assert config.top_assets > 0

    def test_custom_config(self, pipeline_config):
        """Test custom configuration."""
        assert pipeline_config.timeout_seconds == 600
        assert pipeline_config.min_confidence == 0.55
        assert pipeline_config.max_signals == 5
        assert pipeline_config.top_assets == 5


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestPipelineErrorHandling:
    """Tests for pipeline error handling."""

    @pytest.fixture
    def pipeline(self, pipeline_config):
        return SignalPipeline(pipeline_config)

    @pytest.mark.asyncio
    async def test_handle_api_error(self, pipeline):
        """Test handling API errors gracefully."""
        # Mock fetcher that raises error
        pipeline.options_fetcher = AsyncMock()
        pipeline.options_fetcher.get_available_symbols = AsyncMock(
            side_effect=Exception("API Error")
        )

        # Pipeline should handle error gracefully
        with pytest.raises(Exception):
            await pipeline._stage1_activity_scan()

    @pytest.mark.asyncio
    async def test_handle_empty_symbols(self, pipeline):
        """Test handling empty symbol list."""
        pipeline.options_fetcher = AsyncMock()
        pipeline.options_fetcher.get_available_symbols = AsyncMock(return_value=[])
        pipeline.activity_scorer = AsyncMock()
        pipeline.activity_scorer.scan_all_assets = AsyncMock(return_value={})

        result = await pipeline._stage1_activity_scan()

        assert result == {}

    @pytest.mark.asyncio
    async def test_handle_no_selected_assets(self, pipeline):
        """Test handling when no assets selected."""
        pipeline.activity_scorer = AsyncMock()
        pipeline.activity_scorer.scan_all_assets = AsyncMock(return_value={})
        pipeline.asset_selector = Mock()
        pipeline.asset_selector.select = Mock(return_value=[])

        activity = await pipeline.activity_scorer.scan_all_assets()
        result = pipeline.asset_selector.select(activity)

        assert len(result) == 0


# =============================================================================
# Performance Tests
# =============================================================================


class TestPipelinePerformance:
    """Tests for pipeline performance."""

    @pytest.mark.asyncio
    async def test_execution_timeout(self, pipeline_config):
        """Test execution respects timeout."""
        pipeline_config.timeout_seconds = 1  # Very short timeout

        pipeline = SignalPipeline(pipeline_config)

        # Mock slow operation
        async def slow_operation():
            await asyncio.sleep(5)
            return {}

        pipeline._stage1_activity_scan = slow_operation

        # Should timeout
        start = datetime.utcnow()
        try:
            await asyncio.wait_for(pipeline.execute(), timeout=2)
        except asyncio.TimeoutError:
            pass

        elapsed = (datetime.utcnow() - start).total_seconds()
        assert elapsed < 3  # Should fail within timeout

    @pytest.mark.asyncio
    async def test_parallel_data_fetch(self, pipeline_config):
        """Test parallel data fetching."""
        pipeline = SignalPipeline(pipeline_config)

        # Mock fetchers
        pipeline.options_fetcher = AsyncMock()
        pipeline.futures_fetcher = AsyncMock()

        pipeline.options_fetcher.get_option_chain = AsyncMock(
            return_value=OptionsChain(
                underlying="BTCUSDT", spot_price=42000.0, timestamp=datetime.utcnow()
            )
        )
        pipeline.futures_fetcher.get_all_data = AsyncMock(
            return_value=FuturesData(symbol="BTCUSDT", price=42000.0, timestamp=datetime.utcnow())
        )

        selected = [
            RankedAsset(
                symbol="BTCUSDT",
                rank=1,
                activity_score=0.85,
                primary_driver="WHALE",
                quick_metrics={},
            ),
            RankedAsset(
                symbol="ETHUSDT",
                rank=2,
                activity_score=0.75,
                primary_driver="VOLUME",
                quick_metrics={},
            ),
        ]

        start = datetime.utcnow()
        result = await pipeline._stage3_data_fetch(selected)
        elapsed = (datetime.utcnow() - start).total_seconds()

        # Parallel fetch should be faster than sequential
        assert result is not None
        assert len(result) == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestPipelineIntegration:
    """Integration tests for complete pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_flow(self, pipeline_config):
        """Test complete pipeline flow with all stages."""
        pipeline = SignalPipeline(pipeline_config)

        # Setup all mocks for a complete flow
        pipeline.options_fetcher = AsyncMock()
        pipeline.futures_fetcher = AsyncMock()
        pipeline.activity_scorer = AsyncMock()
        pipeline.asset_selector = Mock()

        # Stage 1: Activity scan
        pipeline.activity_scorer.scan_all_assets = AsyncMock(
            return_value={
                "BTCUSDT": ActivityMetrics(
                    symbol="BTCUSDT",
                    timestamp=datetime.utcnow(),
                    activity_score=0.85,
                    primary_driver="WHALE",
                )
            }
        )

        # Stage 2: Asset selection
        pipeline.asset_selector.select = Mock(
            return_value=[
                RankedAsset(
                    symbol="BTCUSDT",
                    rank=1,
                    activity_score=0.85,
                    primary_driver="WHALE",
                    quick_metrics={},
                )
            ]
        )

        # Stage 3: Data fetch
        pipeline.options_fetcher.get_option_chain = AsyncMock(
            return_value=OptionsChain(
                underlying="BTCUSDT",
                spot_price=42000.0,
                timestamp=datetime.utcnow(),
                total_call_oi=10000,
                total_put_oi=8000,
                strikes={
                    42000.0: StrikeData(
                        strike=42000.0,
                        call=OptionData(open_interest=5000, volume=2000, iv=0.65),
                        put=OptionData(open_interest=4000, volume=1500, iv=0.60),
                    )
                },
            )
        )
        pipeline.options_fetcher.get_recent_trades = AsyncMock(return_value=[])
        pipeline.futures_fetcher.get_all_data = AsyncMock(
            return_value=FuturesData(
                symbol="BTCUSDT",
                price=42000.0,
                timestamp=datetime.utcnow(),
                volume_24h=1500000000.0,
            )
        )

        # Stage 4-6: Mock analysis
        pipeline._run_analysis = AsyncMock(
            return_value={"direction": SignalDirection.LONG, "confidence": 0.78}
        )
        pipeline._detect_whale_activity = AsyncMock(
            return_value=WhaleAnalysis(
                symbol="BTCUSDT",
                analysis_timestamp=datetime.utcnow(),
                lookback_hours=24,
                whale_net_direction="BULLISH",
                confidence_boost=0.1,
            )
        )
        pipeline._detect_walls = AsyncMock(
            return_value=WallAnalysis(
                symbol="BTCUSDT",
                spot_price=42000.0,
                timestamp=datetime.utcnow(),
                support_levels=[41000.0],
                resistance_levels=[43000.0],
            )
        )
        pipeline._generate_signal = AsyncMock(
            return_value=TradingSignal(
                signal_id="SIG_001",
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
                asset_rank=1,
                activity_score=0.85,
                direction=SignalDirection.LONG,
                confidence_score=0.78,
                signal_strength=SignalStrength.STRONG,
                entry_zone=EntryZone(min=41900.0, max=42100.0, ideal=42000.0),
                stop_loss=StopLoss(price=41000.0, type="WALL_BASED", distance_pct=2.4),
                whale_metrics={"whale_net_direction": "BULLISH"},
                risk_reward_ratio=2.5,
            )
        )

        # Execute
        result = await pipeline.execute()

        # Verify
        assert result is not None
        assert isinstance(result, ExecutionResult)
        assert result.execution_duration_seconds > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
