"""
Unit tests for Whale Detection module.

Tests for whale detection, trade analysis, and volume flow analysis.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from typing import Dict, Any, List

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    OptionData,
    WhaleTrade,
    WhaleAnalysis,
    WhaleDirection,
)
from binance_signal_generator.whale.whale_detector import (
    WhaleDetector,
    WhaleDetectorConfig,
)
from binance_signal_generator.whale.volume_analyzer import (
    VolumeAnalyzer,
    VolumeAnalyzerConfig,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_whale_trades() -> List[Dict[str, Any]]:
    """Create sample whale trades data."""
    return [
        {
            "tradeId": "1001",
            "symbol": "BTC-240115-42000-C",  # Call
            "price": 2.5,
            "qty": 50000,
            "quoteQty": 125000,  # $125k - whale trade
            "time": int(datetime.utcnow().timestamp() * 1000),
            "side": "BUY",
            "buyerOrderType": "MARKET",
        },
        {
            "tradeId": "1002",
            "symbol": "BTC-240115-41000-P",  # Put
            "price": 1.0,
            "qty": 120000,
            "quoteQty": 120000,  # $120k - whale trade
            "time": int(datetime.utcnow().timestamp() * 1000),
            "side": "BUY",
            "buyerOrderType": "MARKET",
        },
        {
            "tradeId": "1003",
            "symbol": "BTC-240115-43000-C",  # Call
            "price": 1.5,
            "qty": 80000,
            "quoteQty": 120000,  # $120k - whale trade
            "time": int(datetime.utcnow().timestamp() * 1000),
            "side": "SELL",
            "buyerOrderType": "LIMIT",
        },
        {
            "tradeId": "1004",
            "symbol": "BTC-240115-40000-P",  # Put
            "price": 0.5,
            "qty": 600000,
            "quoteQty": 300000,  # $300k - block trade
            "time": int(datetime.utcnow().timestamp() * 1000),
            "side": "SELL",
            "buyerOrderType": "MARKET",
        },
        {
            "tradeId": "1005",
            "symbol": "BTC-240115-42000-C",  # Call
            "price": 2.0,
            "qty": 20000,
            "quoteQty": 40000,  # Not a whale trade
            "time": int(datetime.utcnow().timestamp() * 1000),
            "side": "BUY",
            "buyerOrderType": "LIMIT",
        },
    ]


@pytest.fixture
def sample_options_chain():
    """Create sample options chain for testing."""
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
            call=OptionData(open_interest=1000, volume=500),
            put=OptionData(open_interest=3000, volume=1500),
        ),
        41000.0: StrikeData(
            strike=41000.0,
            call=OptionData(open_interest=2000, volume=800),
            put=OptionData(open_interest=2500, volume=1000),
        ),
        42000.0: StrikeData(
            strike=42000.0,
            call=OptionData(open_interest=3000, volume=1200),
            put=OptionData(open_interest=1500, volume=800),
        ),
        43000.0: StrikeData(
            strike=43000.0,
            call=OptionData(open_interest=2500, volume=1000),
            put=OptionData(open_interest=800, volume=400),
        ),
    }

    return chain


@pytest.fixture
def detector():
    """Create WhaleDetector instance."""
    return WhaleDetector(
        WhaleDetectorConfig(
            min_premium=100000,  # $100k
            block_threshold=500000,  # $500k
            lookback_hours=24,
            min_trades_for_analysis=3,
            bullish_threshold=0.3,
            bearish_threshold=-0.3,
        )
    )


@pytest.fixture
def volume_analyzer():
    """Create VolumeAnalyzer instance."""
    return VolumeAnalyzer(VolumeAnalyzerConfig())


# =============================================================================
# Whale Detector Tests
# =============================================================================


class TestWhaleDetector:
    """Tests for WhaleDetector class."""

    def test_init(self, detector):
        """Test WhaleDetector initialization."""
        assert detector is not None
        assert detector.config.min_premium == 100000
        assert detector.config.block_threshold == 500000

    def test_analyze_with_whale_trades(self, detector, sample_whale_trades, sample_options_chain):
        """Test analysis with whale trades."""
        result = detector.analyze(sample_whale_trades, sample_options_chain)

        assert result is not None
        assert isinstance(result, WhaleAnalysis)
        assert result.symbol == "BTCUSDT"
        assert result.large_trades_count == 4  # 4 trades >= $100k

    def test_filter_whale_trades(self, detector, sample_whale_trades):
        """Test filtering of whale trades."""
        whale_trades = detector._filter_whale_trades(sample_whale_trades)

        assert len(whale_trades) == 4  # Only trades >= $100k
        for trade in whale_trades:
            assert trade.premium >= 100000

    def test_parse_trade_call(self, detector):
        """Test parsing call option trade."""
        trade_data = {
            "tradeId": "1001",
            "symbol": "BTC-240115-42000-C",
            "price": 2.5,
            "qty": 50000,
            "quoteQty": 125000,
            "time": datetime.utcnow(),
            "side": "BUY",
        }

        result = detector._parse_trade(trade_data)

        assert result is not None
        assert result.option_type == "CALL"
        assert result.strike == 42000.0
        assert result.direction == "BUY"
        assert result.inferred_sentiment == "BULLISH"  # Buying calls = bullish

    def test_parse_trade_put(self, detector):
        """Test parsing put option trade."""
        trade_data = {
            "tradeId": "1002",
            "symbol": "BTC-240115-41000-P",
            "price": 1.0,
            "qty": 120000,
            "quoteQty": 120000,
            "time": datetime.utcnow(),
            "side": "BUY",
        }

        result = detector._parse_trade(trade_data)

        assert result is not None
        assert result.option_type == "PUT"
        assert result.strike == 41000.0
        assert result.direction == "BUY"
        assert result.inferred_sentiment == "BEARISH"  # Buying puts = bearish

    def test_infer_sentiment_call_buy(self, detector):
        """Test sentiment inference for call buy."""
        sentiment = detector._infer_sentiment("CALL", "BUY")
        assert sentiment == "BULLISH"

    def test_infer_sentiment_call_sell(self, detector):
        """Test sentiment inference for call sell."""
        sentiment = detector._infer_sentiment("CALL", "SELL")
        assert sentiment == "BEARISH"

    def test_infer_sentiment_put_buy(self, detector):
        """Test sentiment inference for put buy."""
        sentiment = detector._infer_sentiment("PUT", "BUY")
        assert sentiment == "BEARISH"

    def test_infer_sentiment_put_sell(self, detector):
        """Test sentiment inference for put sell."""
        sentiment = detector._infer_sentiment("PUT", "SELL")
        assert sentiment == "BULLISH"

    def test_determine_direction_bullish(self, detector):
        """Test direction determination - bullish."""
        direction = detector._determine_direction(
            net_volume=500000, total_volume=1000000  # Net positive
        )

        assert direction == "BULLISH"

    def test_determine_direction_bearish(self, detector):
        """Test direction determination - bearish."""
        direction = detector._determine_direction(
            net_volume=-500000, total_volume=1000000  # Net negative
        )

        assert direction == "BEARISH"

    def test_determine_direction_neutral(self, detector):
        """Test direction determination - neutral."""
        direction = detector._determine_direction(
            net_volume=100000, total_volume=1000000  # Small net
        )

        assert direction == "NEUTRAL"

    def test_calculate_confidence_boost(self, detector):
        """Test confidence boost calculation."""
        boost = detector._calculate_confidence_boost(
            net_volume=1000000, total_volume=2000000, activity_score=0.8
        )

        assert boost > 0
        assert boost <= 0.2  # Max 20% boost

    def test_analyze_volume_aggregation(self, detector, sample_whale_trades, sample_options_chain):
        """Test volume aggregation in analysis."""
        result = detector.analyze(sample_whale_trades, sample_options_chain)

        # Total whale volume: 125k + 120k + 120k + 300k = 665k
        assert result.whale_buy_volume + result.whale_sell_volume > 0

        # Net volume calculation
        assert result.whale_net_volume == result.whale_buy_volume - result.whale_sell_volume

    def test_analyze_block_trade_detection(
        self, detector, sample_whale_trades, sample_options_chain
    ):
        """Test block trade detection."""
        whale_trades = detector._filter_whale_trades(sample_whale_trades)

        # One trade >= $500k (block trade)
        block_trades = [t for t in whale_trades if t.is_block_trade]
        assert len(block_trades) == 1
        assert block_trades[0].premium == 300000

    def test_analyze_empty_trades(self, detector, sample_options_chain):
        """Test analysis with no trades."""
        result = detector.analyze([], sample_options_chain)

        assert result is not None
        assert result.large_trades_count == 0
        assert result.whale_net_direction == "NEUTRAL"

    def test_get_whale_summary(self, detector, sample_whale_trades, sample_options_chain):
        """Test whale summary generation."""
        analysis = detector.analyze(sample_whale_trades, sample_options_chain)
        summary = detector.get_whale_summary(analysis)

        assert summary is not None
        assert "symbol" in summary
        assert "net_direction" in summary
        assert "trade_count" in summary


# =============================================================================
# Volume Analyzer Tests
# =============================================================================


class TestVolumeAnalyzer:
    """Tests for VolumeAnalyzer class."""

    def test_init(self, volume_analyzer):
        """Test VolumeAnalyzer initialization."""
        assert volume_analyzer is not None

    def test_analyze_volume_flow(self, volume_analyzer, sample_whale_trades):
        """Test volume flow analysis."""
        result = volume_analyzer.analyze(sample_whale_trades)

        assert result is not None
        assert "total_volume" in result
        assert "buy_volume" in result
        assert "sell_volume" in result

    def test_calculate_concentration(self, volume_analyzer):
        """Test volume concentration calculation."""
        trades_by_strike = {
            40000.0: {"call": 100000, "put": 200000},
            41000.0: {"call": 150000, "put": 100000},
            42000.0: {"call": 500000, "put": 50000},  # Heavy call activity
        }

        result = volume_analyzer.calculate_concentration(trades_by_strike)

        assert result is not None
        assert result["concentrated_strikes"] is not None

    def test_time_analysis(self, volume_analyzer, sample_whale_trades):
        """Test time-based volume analysis."""
        result = volume_analyzer.analyze_time_distribution(sample_whale_trades)

        assert result is not None
        # Should have time buckets
        assert "hourly_distribution" in result or "time_buckets" in result


# =============================================================================
# Whale Trade Model Tests
# =============================================================================


class TestWhaleTradeModel:
    """Tests for WhaleTrade data model."""

    def test_create_whale_trade(self):
        """Test creating whale trade."""
        trade = WhaleTrade(
            trade_id="1001",
            timestamp=datetime.utcnow(),
            symbol="BTC-240115-42000-C",
            option_type="CALL",
            strike=42000.0,
            expiry=datetime.utcnow() + timedelta(days=7),
            premium=125000.0,
            contracts=50000,
            price_per_contract=2.5,
            direction="BUY",
            aggressor="MARKET",
            is_block_trade=False,
            inferred_sentiment="BULLISH",
        )

        assert trade.trade_id == "1001"
        assert trade.option_type == "CALL"
        assert trade.premium == 125000.0
        assert trade.is_block_trade == False
        assert trade.inferred_sentiment == "BULLISH"


class TestWhaleAnalysisModel:
    """Tests for WhaleAnalysis data model."""

    def test_create_whale_analysis(self):
        """Test creating whale analysis."""
        analysis = WhaleAnalysis(
            symbol="BTCUSDT",
            analysis_timestamp=datetime.utcnow(),
            lookback_hours=24,
            whale_buy_volume=500000.0,
            whale_sell_volume=300000.0,
            whale_net_volume=200000.0,
            whale_net_direction="BULLISH",
            whale_activity_score=0.75,
            large_trades_count=10,
            avg_trade_size=80000.0,
            max_single_trade=200000.0,
            notable_strikes=[{"strike": 42000.0, "volume": 300000}],
            put_heavy_strikes=[40000.0],
            call_heavy_strikes=[43000.0],
            confidence_boost=0.15,
            signal_alignment="BULLISH",
        )

        assert analysis.symbol == "BTCUSDT"
        assert analysis.whale_net_direction == "BULLISH"
        assert analysis.whale_net_volume == 200000.0
        assert analysis.confidence_boost == 0.15


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestWhaleDetectorEdgeCases:
    """Edge case tests for WhaleDetector."""

    @pytest.fixture
    def detector(self):
        return WhaleDetector(WhaleDetectorConfig())

    def test_all_buy_trades(self, detector, sample_options_chain):
        """Test with all buy trades."""
        trades = [
            {
                "tradeId": f"10{i}",
                "symbol": "BTC-240115-42000-C",
                "quoteQty": 150000,
                "time": int(datetime.utcnow().timestamp() * 1000),
                "side": "BUY",
            }
            for i in range(5)
        ]

        result = detector.analyze(trades, sample_options_chain)

        assert result.whale_buy_volume > 0
        assert result.whale_sell_volume == 0
        assert result.whale_net_direction == "BULLISH"

    def test_all_sell_trades(self, detector, sample_options_chain):
        """Test with all sell trades."""
        trades = [
            {
                "tradeId": f"10{i}",
                "symbol": "BTC-240115-42000-C",
                "quoteQty": 150000,
                "time": int(datetime.utcnow().timestamp() * 1000),
                "side": "SELL",
            }
            for i in range(5)
        ]

        result = detector.analyze(trades, sample_options_chain)

        assert result.whale_buy_volume == 0
        assert result.whale_sell_volume > 0
        assert result.whale_net_direction == "BEARISH"

    def test_mixed_small_trades(self, detector, sample_options_chain):
        """Test with trades below whale threshold."""
        trades = [
            {
                "tradeId": f"10{i}",
                "symbol": "BTC-240115-42000-C",
                "quoteQty": 50000,  # Below threshold
                "time": int(datetime.utcnow().timestamp() * 1000),
                "side": "BUY",
            }
            for i in range(10)
        ]

        result = detector.analyze(trades, sample_options_chain)

        assert result.large_trades_count == 0

    def test_unusual_symbol_format(self, detector, sample_options_chain):
        """Test with unusual symbol format."""
        trade = {
            "tradeId": "1001",
            "symbol": "UNKNOWN_FORMAT",
            "quoteQty": 150000,
            "time": int(datetime.utcnow().timestamp() * 1000),
            "side": "BUY",
        }

        result = detector._parse_trade(trade)

        assert result is not None
        assert result.option_type == "UNKNOWN"
        assert result.strike == 0.0


# =============================================================================
# Integration Tests
# =============================================================================


class TestWhaleIntegration:
    """Integration tests for whale detection."""

    def test_full_whale_analysis_flow(self, detector, sample_whale_trades, sample_options_chain):
        """Test complete whale analysis flow."""
        # Analyze trades
        analysis = detector.analyze(sample_whale_trades, sample_options_chain)

        # Verify complete analysis
        assert analysis.symbol == "BTCUSDT"
        assert analysis.large_trades_count > 0
        assert analysis.whale_net_direction in ["BULLISH", "BEARISH", "NEUTRAL"]
        assert 0 <= analysis.whale_activity_score <= 1
        assert 0 <= analysis.confidence_boost <= 0.2

        # Get summary
        summary = detector.get_whale_summary(analysis)

        assert summary["symbol"] == "BTCUSDT"
        assert summary["trade_count"] == analysis.large_trades_count


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
