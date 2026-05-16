"""
Unit tests for analysis modules.

Tests for IV, PCR, OI, Max Pain analyzers and Signal Scorer.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from typing import Dict, Any

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    OptionData,
    SignalDirection,
    IVAnalysis,
    PCRAnalysis,
    OIAnalysis,
    MaxPainAnalysis,
    OptionsSignal,
)
from binance_signal_generator.analysis.iv_analyzer import (
    IVAnalyzer,
    IVAnalyzerConfig,
)
from binance_signal_generator.analysis.pcr_analyzer import (
    PCRAnalyzer,
    PCRAnalyzerConfig,
)
from binance_signal_generator.analysis.oi_analyzer import (
    OIAnalyzer,
    OIAnalyzerConfig,
)
from binance_signal_generator.analysis.max_pain import (
    MaxPainCalculator,
    MaxPainConfig,
)
from binance_signal_generator.analysis.signal_scorer import (
    SignalScorer,
    SignalScorerConfig,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_options_chain():
    """Create sample options chain for testing."""
    chain = OptionsChain(
        underlying="BTCUSDT",
        spot_price=42000.0,
        timestamp=datetime.utcnow(),
        total_call_oi=10000,
        total_put_oi=8000,
        total_call_volume=5000.0,
        total_put_volume=4000.0,
    )

    # Add strikes
    chain.strikes = {
        40000.0: StrikeData(
            strike=40000.0,
            call=OptionData(open_interest=1000, volume=500, iv=0.80),
            put=OptionData(open_interest=3000, volume=1500, iv=0.75),
        ),
        41000.0: StrikeData(
            strike=41000.0,
            call=OptionData(open_interest=2000, volume=800, iv=0.70),
            put=OptionData(open_interest=2500, volume=1000, iv=0.65),
        ),
        42000.0: StrikeData(
            strike=42000.0,
            call=OptionData(open_interest=3000, volume=1200, iv=0.60),
            put=OptionData(open_interest=1500, volume=800, iv=0.55),
        ),
        43000.0: StrikeData(
            strike=43000.0,
            call=OptionData(open_interest=2500, volume=1000, iv=0.55),
            put=OptionData(open_interest=800, volume=400, iv=0.50),
        ),
        44000.0: StrikeData(
            strike=44000.0,
            call=OptionData(open_interest=1500, volume=500, iv=0.50),
            put=OptionData(open_interest=200, volume=100, iv=0.45),
        ),
    }

    return chain


@pytest.fixture
def sample_iv_chain():
    """Create options chain with varied IV for testing."""
    chain = OptionsChain(
        underlying="BTCUSDT",
        spot_price=42000.0,
        timestamp=datetime.utcnow(),
        total_call_oi=10000,
        total_put_oi=8000,
    )

    chain.strikes = {
        41000.0: StrikeData(
            strike=41000.0,
            call=OptionData(open_interest=1000, volume=500, iv=0.85),  # High IV
            put=OptionData(open_interest=2000, volume=1000, iv=0.80),
        ),
        42000.0: StrikeData(
            strike=42000.0,
            call=OptionData(open_interest=2000, volume=1000, iv=0.65),  # Normal IV
            put=OptionData(open_intensity=1500, volume=800, iv=0.60),
        ),
        43000.0: StrikeData(
            strike=43000.0,
            call=OptionData(open_interest=1500, volume=600, iv=0.45),  # Low IV
            put=OptionData(open_interest=500, volume=200, iv=0.40),
        ),
    }

    return chain


# =============================================================================
# IV Analyzer Tests
# =============================================================================


class TestIVAnalyzer:
    """Tests for IV Analyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create IV analyzer instance."""
        return IVAnalyzer(
            IVAnalyzerConfig(
                enabled=True, weight=0.20, lookback_days=30, threshold_high=0.75, threshold_low=0.25
            )
        )

    def test_init(self, analyzer):
        """Test IV analyzer initialization."""
        assert analyzer is not None
        assert analyzer.config.weight == 0.20

    def test_analyze_high_iv(self, analyzer, sample_options_chain):
        """Test IV analysis with high IV."""
        result = analyzer.analyze(sample_options_chain)

        assert result is not None
        assert isinstance(result, IVAnalysis)
        assert result.symbol == "BTCUSDT"
        assert result.current_iv > 0
        assert result.iv_rank >= 0
        assert result.iv_rank <= 1

    def test_analyze_iv_state_classification(self, analyzer, sample_options_chain):
        """Test IV state classification."""
        result = analyzer.analyze(sample_options_chain)

        assert result.iv_state in ["LOW", "NORMAL", "HIGH"]

    def test_analyze_signal_direction(self, analyzer, sample_options_chain):
        """Test signal direction from IV analysis."""
        result = analyzer.analyze(sample_options_chain)

        assert result.signal in [
            SignalDirection.LONG,
            SignalDirection.SHORT,
            SignalDirection.NEUTRAL,
        ]

    def test_analyze_confidence(self, analyzer, sample_options_chain):
        """Test confidence calculation."""
        result = analyzer.analyze(sample_options_chain)

        assert 0 <= result.confidence <= 1

    def test_calculate_atm_iv(self, analyzer, sample_options_chain):
        """Test ATM IV calculation."""
        atm_iv = analyzer._calculate_atm_iv(sample_options_chain)

        assert atm_iv > 0
        # Should be close to IV at spot strike (42000)
        spot_strike_iv = sample_options_chain.strikes[42000.0].call.iv
        assert abs(atm_iv - spot_strike_iv) < 0.1

    def test_empty_chain_handling(self, analyzer):
        """Test handling of empty options chain."""
        empty_chain = OptionsChain(
            underlying="BTCUSDT", spot_price=42000.0, timestamp=datetime.utcnow()
        )

        result = analyzer.analyze(empty_chain)

        assert result is not None
        # Should return default/neutral values


# =============================================================================
# PCR Analyzer Tests
# =============================================================================


class TestPCRAnalyzer:
    """Tests for PCR Analyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create PCR analyzer instance."""
        return PCRAnalyzer(
            PCRAnalyzerConfig(
                enabled=True, weight=0.25, threshold_put_high=1.2, threshold_call_high=0.8
            )
        )

    def test_init(self, analyzer):
        """Test PCR analyzer initialization."""
        assert analyzer is not None
        assert analyzer.config.weight == 0.25

    def test_analyze(self, analyzer, sample_options_chain):
        """Test PCR analysis."""
        result = analyzer.analyze(sample_options_chain)

        assert result is not None
        assert isinstance(result, PCRAnalysis)
        assert result.symbol == "BTCUSDT"
        assert result.pcr_oi == 0.8  # 8000 / 10000
        assert result.pcr_volume == 0.8  # 4000 / 5000

    def test_pcr_state_classification_put_heavy(self, analyzer):
        """Test PCR state classification - put heavy."""
        # Create chain with high put OI
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=5000,
            total_put_oi=10000,  # PCR = 2.0
        )

        result = analyzer.analyze(chain)

        assert result.pcr_state == "PUT_HEAVY"
        # Put heavy = bearish sentiment = contrarian bullish
        assert result.signal == SignalDirection.LONG

    def test_pcr_state_classification_call_heavy(self, analyzer):
        """Test PCR state classification - call heavy."""
        # Create chain with high call OI
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=10000,
            total_put_oi=5000,  # PCR = 0.5
        )

        result = analyzer.analyze(chain)

        assert result.pcr_state == "CALL_HEAVY"
        # Call heavy = bullish sentiment = contrarian bearish
        assert result.signal == SignalDirection.SHORT

    def test_pcr_state_classification_neutral(self, analyzer):
        """Test PCR state classification - neutral."""
        # Create chain with balanced OI
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=8000,
            total_put_oi=8000,  # PCR = 1.0
        )

        result = analyzer.analyze(chain)

        assert result.pcr_state == "NEUTRAL"
        assert result.signal == SignalDirection.NEUTRAL

    def test_pcr_confidence_extreme(self, analyzer):
        """Test PCR confidence with extreme values."""
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=1000,
            total_put_oi=5000,  # PCR = 5.0 (very extreme)
        )

        result = analyzer.analyze(chain)

        assert result.confidence > 0.5  # High confidence for extreme PCR


# =============================================================================
# OI Analyzer Tests
# =============================================================================


class TestOIAnalyzer:
    """Tests for OI Analyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create OI analyzer instance."""
        return OIAnalyzer(OIAnalyzerConfig(enabled=True, weight=0.20, concentration_threshold=0.15))

    def test_init(self, analyzer):
        """Test OI analyzer initialization."""
        assert analyzer is not None
        assert analyzer.config.weight == 0.20

    def test_analyze(self, analyzer, sample_options_chain):
        """Test OI analysis."""
        result = analyzer.analyze(sample_options_chain)

        assert result is not None
        assert isinstance(result, OIAnalysis)
        assert result.symbol == "BTCUSDT"
        assert result.total_oi == 18000  # 10000 + 8000

    def test_oi_concentration(self, analyzer, sample_options_chain):
        """Test OI concentration calculation."""
        result = analyzer.analyze(sample_options_chain)

        assert result.call_oi_concentration >= 0
        assert result.put_oi_concentration >= 0

    def test_oi_signal_direction(self, analyzer, sample_options_chain):
        """Test OI signal direction."""
        result = analyzer.analyze(sample_options_chain)

        assert result.signal in [
            SignalDirection.LONG,
            SignalDirection.SHORT,
            SignalDirection.NEUTRAL,
        ]

    def test_analyze_with_oi_change(self, analyzer, sample_options_chain):
        """Test OI analysis with 24h change."""
        result = analyzer.analyze(sample_options_chain, oi_change_24h=10.0)

        assert result.oi_change_24h == 10.0


# =============================================================================
# Max Pain Calculator Tests
# =============================================================================


class TestMaxPainCalculator:
    """Tests for Max Pain Calculator."""

    @pytest.fixture
    def calculator(self):
        """Create Max Pain calculator instance."""
        return MaxPainCalculator(MaxPainConfig(enabled=True, weight=0.15, distance_threshold=2.0))

    def test_init(self, calculator):
        """Test Max Pain calculator initialization."""
        assert calculator is not None
        assert calculator.config.weight == 0.15

    def test_calculate(self, calculator, sample_options_chain):
        """Test Max Pain calculation."""
        result = calculator.calculate(sample_options_chain)

        assert result is not None
        assert isinstance(result, MaxPainAnalysis)
        assert result.symbol == "BTCUSDT"
        assert result.max_pain_strike > 0
        assert result.current_price == 42000.0

    def test_max_pain_distance(self, calculator, sample_options_chain):
        """Test Max Pain distance calculation."""
        result = calculator.calculate(sample_options_chain)

        # Distance should be calculated
        distance_pct = abs(result.distance_pct)
        assert distance_pct >= 0

    def test_max_pain_signal(self, calculator, sample_options_chain):
        """Test signal from Max Pain analysis."""
        result = calculator.calculate(sample_options_chain)

        assert result.signal in [
            SignalDirection.LONG,
            SignalDirection.SHORT,
            SignalDirection.NEUTRAL,
        ]

    def test_max_pain_below_spot(self, calculator):
        """Test Max Pain when below spot price (bullish)."""
        # Create chain where max pain is below spot
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=43000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=5000,
            total_put_oi=15000,  # More puts = max pain lower
        )

        chain.strikes = {
            40000.0: StrikeData(
                strike=40000.0,
                call=OptionData(open_interest=1000),
                put=OptionData(open_interest=8000),  # Heavy put OI
            ),
            42000.0: StrikeData(
                strike=42000.0,
                call=OptionData(open_interest=2000),
                put=OptionData(open_interest=5000),
            ),
            43000.0: StrikeData(
                strike=43000.0,
                call=OptionData(open_interest=2000),
                put=OptionData(open_interest=2000),
            ),
        }

        result = calculator.calculate(chain)

        # Max pain should be attracted to lower strikes
        assert result.max_pain_strike < chain.spot_price


# =============================================================================
# Signal Scorer Tests
# =============================================================================


class TestSignalScorer:
    """Tests for Signal Scorer."""

    @pytest.fixture
    def scorer(self):
        """Create Signal Scorer instance."""
        return SignalScorer(
            SignalScorerConfig(
                weights={"iv": 0.20, "pcr": 0.25, "oi": 0.20, "max_pain": 0.15, "whale": 0.20},
                min_confidence=0.35,
            )
        )

    def test_init(self, scorer):
        """Test Signal Scorer initialization."""
        assert scorer is not None
        assert scorer.config.weights["iv"] == 0.20

    def test_score(self, scorer, sample_options_chain):
        """Test signal scoring."""
        # Create mock analyses
        iv_analysis = IVAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            current_iv=0.65,
            iv_rank=0.55,
            iv_percentile=0.55,
            signal=SignalDirection.LONG,
            confidence=0.6,
            iv_state="NORMAL",
        )

        pcr_analysis = PCRAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            pcr_oi=1.3,
            pcr_volume=1.2,
            pcr_combined=1.25,
            signal=SignalDirection.LONG,
            confidence=0.7,
            pcr_state="PUT_HEAVY",
        )

        oi_analysis = OIAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            total_oi=18000,
            oi_change_24h=5.0,
            call_oi_concentration=0.55,
            put_oi_concentration=0.45,
            signal=SignalDirection.LONG,
            confidence=0.5,
        )

        max_pain_analysis = MaxPainAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            max_pain_strike=41500,
            current_price=42000,
            distance_pct=-1.2,
            call_pain=500000,
            put_pain=600000,
            signal=SignalDirection.LONG,
            confidence=0.5,
            magnet_strength=0.6,
        )

        result = scorer.score(
            symbol="BTCUSDT",
            iv_analysis=iv_analysis,
            pcr_analysis=pcr_analysis,
            oi_analysis=oi_analysis,
            max_pain_analysis=max_pain_analysis,
        )

        assert result is not None
        assert isinstance(result, OptionsSignal)
        assert result.symbol == "BTCUSDT"
        assert result.direction in [
            SignalDirection.LONG,
            SignalDirection.SHORT,
            SignalDirection.NEUTRAL,
        ]

    def test_score_direction_long(self, scorer):
        """Test scoring results in LONG direction."""
        # All bullish signals
        iv_analysis = IVAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            current_iv=0.65,
            iv_rank=0.80,
            iv_percentile=0.80,
            signal=SignalDirection.LONG,
            confidence=0.8,
            iv_state="HIGH",
        )

        pcr_analysis = PCRAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            pcr_oi=1.5,
            pcr_volume=1.4,
            pcr_combined=1.45,
            signal=SignalDirection.LONG,
            confidence=0.9,
            pcr_state="PUT_HEAVY",
        )

        oi_analysis = OIAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            total_oi=18000,
            oi_change_24h=10.0,
            call_oi_concentration=0.45,
            put_oi_concentration=0.55,
            signal=SignalDirection.LONG,
            confidence=0.7,
        )

        max_pain_analysis = MaxPainAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            max_pain_strike=41000,
            current_price=42000,
            distance_pct=-2.4,
            call_pain=400000,
            put_pain=800000,
            signal=SignalDirection.LONG,
            confidence=0.7,
            magnet_strength=0.8,
        )

        result = scorer.score(
            symbol="BTCUSDT",
            iv_analysis=iv_analysis,
            pcr_analysis=pcr_analysis,
            oi_analysis=oi_analysis,
            max_pain_analysis=max_pain_analysis,
        )

        # With all bullish signals, should be LONG
        assert result.direction == SignalDirection.LONG
        assert result.confidence > 0.5

    def test_score_direction_short(self, scorer):
        """Test scoring results in SHORT direction."""
        # All bearish signals
        iv_analysis = IVAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            current_iv=0.35,
            iv_rank=0.20,
            iv_percentile=0.20,
            signal=SignalDirection.SHORT,
            confidence=0.7,
            iv_state="LOW",
        )

        pcr_analysis = PCRAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            pcr_oi=0.6,
            pcr_volume=0.7,
            pcr_combined=0.65,
            signal=SignalDirection.SHORT,
            confidence=0.8,
            pcr_state="CALL_HEAVY",
        )

        oi_analysis = OIAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            total_oi=18000,
            oi_change_24h=-5.0,
            call_oi_concentration=0.65,
            put_oi_concentration=0.35,
            signal=SignalDirection.SHORT,
            confidence=0.6,
        )

        max_pain_analysis = MaxPainAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            max_pain_strike=43000,
            current_price=42000,
            distance_pct=2.4,
            call_pain=800000,
            put_pain=400000,
            signal=SignalDirection.SHORT,
            confidence=0.6,
            magnet_strength=0.8,
        )

        result = scorer.score(
            symbol="BTCUSDT",
            iv_analysis=iv_analysis,
            pcr_analysis=pcr_analysis,
            oi_analysis=oi_analysis,
            max_pain_analysis=max_pain_analysis,
        )

        # With all bearish signals, should be SHORT
        assert result.direction == SignalDirection.SHORT

    def test_score_neutral(self, scorer):
        """Test scoring with mixed signals results in NEUTRAL."""
        # Mixed signals
        iv_analysis = IVAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            current_iv=0.50,
            iv_rank=0.50,
            iv_percentile=0.50,
            signal=SignalDirection.NEUTRAL,
            confidence=0.3,
            iv_state="NORMAL",
        )

        pcr_analysis = PCRAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            pcr_oi=1.0,
            pcr_volume=1.0,
            pcr_combined=1.0,
            signal=SignalDirection.NEUTRAL,
            confidence=0.2,
            pcr_state="NEUTRAL",
        )

        oi_analysis = OIAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            total_oi=18000,
            oi_change_24h=0,
            call_oi_concentration=0.50,
            put_oi_concentration=0.50,
            signal=SignalDirection.NEUTRAL,
            confidence=0.2,
        )

        max_pain_analysis = MaxPainAnalysis(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            max_pain_strike=42000,
            current_price=42000,
            distance_pct=0,
            call_pain=500000,
            put_pain=500000,
            signal=SignalDirection.NEUTRAL,
            confidence=0.2,
            magnet_strength=0.5,
        )

        result = scorer.score(
            symbol="BTCUSDT",
            iv_analysis=iv_analysis,
            pcr_analysis=pcr_analysis,
            oi_analysis=oi_analysis,
            max_pain_analysis=max_pain_analysis,
        )

        # With neutral signals, should be NEUTRAL
        assert result.direction == SignalDirection.NEUTRAL


# =============================================================================
# Integration Tests
# =============================================================================


class TestAnalysisIntegration:
    """Integration tests for analysis modules."""

    @pytest.fixture
    def analyzers(self):
        """Create all analyzers."""
        return {
            "iv": IVAnalyzer(IVAnalyzerConfig()),
            "pcr": PCRAnalyzer(PCRAnalyzerConfig()),
            "oi": OIAnalyzer(OIAnalyzerConfig()),
            "max_pain": MaxPainCalculator(MaxPainConfig()),
            "scorer": SignalScorer(SignalScorerConfig()),
        }

    def test_full_analysis_flow(self, analyzers, sample_options_chain):
        """Test complete analysis flow."""
        # Run all analyzers
        iv_result = analyzers["iv"].analyze(sample_options_chain)
        pcr_result = analyzers["pcr"].analyze(sample_options_chain)
        oi_result = analyzers["oi"].analyze(sample_options_chain)
        max_pain_result = analyzers["max_pain"].calculate(sample_options_chain)

        # Score results
        signal = analyzers["scorer"].score(
            symbol="BTCUSDT",
            iv_analysis=iv_result,
            pcr_analysis=pcr_result,
            oi_analysis=oi_result,
            max_pain_analysis=max_pain_result,
        )

        assert signal is not None
        assert signal.symbol == "BTCUSDT"
        assert signal.direction in [
            SignalDirection.LONG,
            SignalDirection.SHORT,
            SignalDirection.NEUTRAL,
        ]
        assert 0 <= signal.confidence <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
