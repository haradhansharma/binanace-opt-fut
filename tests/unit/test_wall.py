"""
Unit tests for Wall Detection module.

Tests for Options wall detection, support/resistance calculation,
and S/R level generation.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from typing import Dict, Any, List

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    OptionData,
    OptionWall,
    WallAnalysis,
    SRLevel,
    SRLevels,
    SignalDirection,
)
from binance_signal_generator.analysis.wall_detector import (
    WallDetector,
    WallDetectorConfig,
)
from binance_signal_generator.output.sr_levels import (
    SRLevelCalculator,
    SRLevelConfig,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_options_chain_with_walls():
    """Create options chain with clear wall formations."""
    chain = OptionsChain(
        underlying="BTCUSDT",
        spot_price=42000.0,
        timestamp=datetime.utcnow(),
        total_call_oi=10000,
        total_put_oi=10000,
    )

    chain.strikes = {
        # Put walls (support) - below spot
        40000.0: StrikeData(
            strike=40000.0,
            call=OptionData(open_interest=500, volume=200),
            put=OptionData(open_interest=2500, volume=1000),  # 12.5% of total OI = wall
        ),
        40500.0: StrikeData(
            strike=40500.0,
            call=OptionData(open_interest=800, volume=300),
            put=OptionData(open_interest=1000, volume=400),
        ),
        41000.0: StrikeData(
            strike=41000.0,
            call=OptionData(open_interest=1000, volume=400),
            put=OptionData(open_interest=3000, volume=1200),  # 15% of total OI = wall
        ),
        41500.0: StrikeData(
            strike=41500.0,
            call=OptionData(open_interest=1200, volume=500),
            put=OptionData(open_interest=800, volume=300),
        ),
        # ATM
        42000.0: StrikeData(
            strike=42000.0,
            call=OptionData(open_interest=1500, volume=600),
            put=OptionData(open_interest=1500, volume=600),
        ),
        # Call walls (resistance) - above spot
        42500.0: StrikeData(
            strike=42500.0,
            call=OptionData(open_interest=1800, volume=700),
            put=OptionData(open_interest=600, volume=200),
        ),
        43000.0: StrikeData(
            strike=43000.0,
            call=OptionData(open_interest=2500, volume=1000),  # 12.5% = wall
            put=OptionData(open_interest=400, volume=150),
        ),
        43500.0: StrikeData(
            strike=43500.0,
            call=OptionData(open_interest=700, volume=300),
            put=OptionData(open_interest=200, volume=80),
        ),
        44000.0: StrikeData(
            strike=44000.0,
            call=OptionData(open_intensity=2000, volume=800),  # 10% = wall
            put=OptionData(open_interest=100, volume=50),
        ),
    }

    return chain


@pytest.fixture
def sample_options_chain_no_walls():
    """Create options chain without clear walls."""
    chain = OptionsChain(
        underlying="BTCUSDT",
        spot_price=42000.0,
        timestamp=datetime.utcnow(),
        total_call_oi=5000,
        total_put_oi=5000,
    )

    # Evenly distributed OI
    chain.strikes = {
        41000.0: StrikeData(
            strike=41000.0,
            call=OptionData(open_interest=1000, volume=400),
            put=OptionData(open_interest=1000, volume=400),
        ),
        41500.0: StrikeData(
            strike=41500.0,
            call=OptionData(open_interest=1000, volume=400),
            put=OptionData(open_interest=1000, volume=400),
        ),
        42000.0: StrikeData(
            strike=42000.0,
            call=OptionData(open_interest=1000, volume=400),
            put=OptionData(open_interest=1000, volume=400),
        ),
        42500.0: StrikeData(
            strike=42500.0,
            call=OptionData(open_interest=1000, volume=400),
            put=OptionData(open_interest=1000, volume=400),
        ),
        43000.0: StrikeData(
            strike=43000.0,
            call=OptionData(open_interest=1000, volume=400),
            put=OptionData(open_interest=1000, volume=400),
        ),
    }

    return chain


@pytest.fixture
def wall_detector():
    """Create WallDetector instance."""
    return WallDetector(
        WallDetectorConfig(
            min_oi_concentration=0.10,  # 10%
            major_wall_concentration=0.20,  # 20%
            max_wall_distance=15.0,
            min_absolute_oi=100,
        )
    )


@pytest.fixture
def sr_calculator():
    """Create SRLevelCalculator instance."""
    return SRLevelCalculator(
        SRLevelConfig(
            max_support_levels=3,
            max_resistance_levels=3,
            min_level_distance_pct=1.0,
            wall_weight=0.50,
            max_pain_weight=0.30,
            volume_weight=0.20,
            default_sl_distance_pct=2.0,
        )
    )


# =============================================================================
# Wall Detector Tests
# =============================================================================


class TestWallDetector:
    """Tests for WallDetector class."""

    def test_init(self, wall_detector):
        """Test WallDetector initialization."""
        assert wall_detector is not None
        assert wall_detector.config.min_oi_concentration == 0.10

    def test_detect_walls(self, wall_detector, sample_options_chain_with_walls):
        """Test wall detection."""
        result = wall_detector.detect(sample_options_chain_with_walls)

        assert result is not None
        assert isinstance(result, WallAnalysis)
        assert result.symbol == "BTCUSDT"
        assert result.spot_price == 42000.0

    def test_detect_put_walls(self, wall_detector, sample_options_chain_with_walls):
        """Test put wall (support) detection."""
        result = wall_detector.detect(sample_options_chain_with_walls)

        assert len(result.put_walls) > 0

        # All put walls should be below spot
        for wall in result.put_walls:
            assert wall.strike < sample_options_chain_with_walls.spot_price
            assert wall.wall_type == "PUT_WALL"

    def test_detect_call_walls(self, wall_detector, sample_options_chain_with_walls):
        """Test call wall (resistance) detection."""
        result = wall_detector.detect(sample_options_chain_with_walls)

        assert len(result.call_walls) > 0

        # All call walls should be above spot
        for wall in result.call_walls:
            assert wall.strike > sample_options_chain_with_walls.spot_price
            assert wall.wall_type == "CALL_WALL"

    def test_detect_no_walls(self, wall_detector, sample_options_chain_no_walls):
        """Test detection with no clear walls."""
        result = wall_detector.detect(sample_options_chain_no_walls)

        # With 10% threshold and evenly distributed OI, no walls should be detected
        assert result.total_walls == 0
        assert len(result.put_walls) == 0
        assert len(result.call_walls) == 0

    def test_wall_strength_calculation(self, wall_detector, sample_options_chain_with_walls):
        """Test wall strength score calculation."""
        result = wall_detector.detect(sample_options_chain_with_walls)

        for wall in result.put_walls + result.call_walls:
            assert 0 <= wall.strength_score <= 1

    def test_strongest_wall(self, wall_detector, sample_options_chain_with_walls):
        """Test strongest wall identification."""
        result = wall_detector.detect(sample_options_chain_with_walls)

        if result.put_walls:
            assert result.strongest_put_wall is not None
            max_strength = max(w.strength_score for w in result.put_walls)
            assert result.strongest_put_wall.strength_score == max_strength

        if result.call_walls:
            assert result.strongest_call_wall is not None
            max_strength = max(w.strength_score for w in result.call_walls)
            assert result.strongest_call_wall.strength_score == max_strength

    def test_nearest_wall(self, wall_detector, sample_options_chain_with_walls):
        """Test nearest wall identification."""
        result = wall_detector.detect(sample_options_chain_with_walls)
        spot = sample_options_chain_with_walls.spot_price

        if result.put_walls:
            assert result.nearest_put_wall is not None
            # Nearest should be closest to spot
            min_distance = min(abs(spot - w.strike) for w in result.put_walls)
            assert abs(spot - result.nearest_put_wall.strike) == min_distance

    def test_wall_intensity(self, wall_detector, sample_options_chain_with_walls):
        """Test wall intensity calculation."""
        result = wall_detector.detect(sample_options_chain_with_walls)

        assert 0 <= result.wall_intensity <= 1

        # More walls = higher intensity
        if result.total_walls > 0:
            assert result.wall_intensity > 0

    def test_wall_imbalance(self, wall_detector, sample_options_chain_with_walls):
        """Test wall imbalance calculation."""
        result = wall_detector.detect(sample_options_chain_with_walls)

        assert -1 <= result.wall_imbalance <= 1

        # Positive = more put walls (bullish)
        # Negative = more call walls (bearish)

    def test_support_resistance_levels(self, wall_detector, sample_options_chain_with_walls):
        """Test support and resistance level generation."""
        result = wall_detector.detect(sample_options_chain_with_walls)

        # Support from put walls
        assert len(result.support_levels) <= 3
        for level in result.support_levels:
            assert level < sample_options_chain_with_walls.spot_price

        # Resistance from call walls
        assert len(result.resistance_levels) <= 3
        for level in result.resistance_levels:
            assert level > sample_options_chain_with_walls.spot_price

    def test_get_wall_summary(self, wall_detector, sample_options_chain_with_walls):
        """Test wall summary generation."""
        analysis = wall_detector.detect(sample_options_chain_with_walls)
        summary = wall_detector.get_wall_summary(analysis)

        assert summary is not None
        assert "symbol" in summary
        assert "total_walls" in summary
        assert "wall_intensity" in summary


# =============================================================================
# S/R Level Calculator Tests
# =============================================================================


class TestSRLevelCalculator:
    """Tests for SRLevelCalculator class."""

    def test_init(self, sr_calculator):
        """Test SRLevelCalculator initialization."""
        assert sr_calculator is not None
        assert sr_calculator.config.max_support_levels == 3

    def test_calculate_sr_levels(self, sr_calculator, sample_options_chain_with_walls):
        """Test S/R level calculation."""
        result = sr_calculator.calculate(sample_options_chain_with_walls)

        assert result is not None
        assert isinstance(result, SRLevels)

    def test_support_levels_calculation(self, sr_calculator, sample_options_chain_with_walls):
        """Test support level calculation."""
        result = sr_calculator.calculate(sample_options_chain_with_walls)

        assert len(result.support) <= 3

        for level in result.support:
            assert isinstance(level, SRLevel)
            assert level.price < sample_options_chain_with_walls.spot_price
            assert level.type in ["PUT_WALL", "MAX_PAIN"]

    def test_resistance_levels_calculation(self, sr_calculator, sample_options_chain_with_walls):
        """Test resistance level calculation."""
        result = sr_calculator.calculate(sample_options_chain_with_walls)

        assert len(result.resistance) <= 3

        for level in result.resistance:
            assert isinstance(level, SRLevel)
            assert level.price > sample_options_chain_with_walls.spot_price
            assert level.type in ["CALL_WALL", "MAX_PAIN"]


# =============================================================================
# Wall Model Tests
# =============================================================================


class TestOptionWallModel:
    """Tests for OptionWall data model."""

    def test_create_option_wall(self):
        """Test creating option wall."""
        wall = OptionWall(
            strike=42000.0,
            wall_type="CALL_WALL",
            open_interest=5000,
            oi_percentage=0.25,
            oi_change_24h=5.0,
            volume=2000,
            volume_vs_avg=1.5,
            distance_from_spot=0.024,
            side="ABOVE",
            strength_score=0.8,
            is_major_wall=True,
        )

        assert wall.strike == 42000.0
        assert wall.wall_type == "CALL_WALL"
        assert wall.is_major_wall == True
        assert wall.oi_percentage == 0.25


class TestWallAnalysisModel:
    """Tests for WallAnalysis data model."""

    def test_create_wall_analysis(self):
        """Test creating wall analysis."""
        analysis = WallAnalysis(
            symbol="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            put_walls=[
                OptionWall(
                    strike=41000.0,
                    wall_type="PUT_WALL",
                    open_interest=3000,
                    oi_percentage=0.15,
                    distance_from_spot=0.024,
                    side="BELOW",
                    strength_score=0.7,
                )
            ],
            call_walls=[
                OptionWall(
                    strike=43000.0,
                    wall_type="CALL_WALL",
                    open_interest=2500,
                    oi_percentage=0.125,
                    distance_from_spot=0.024,
                    side="ABOVE",
                    strength_score=0.6,
                )
            ],
            total_walls=2,
            wall_intensity=0.65,
            wall_imbalance=0.1,
        )

        assert analysis.symbol == "BTCUSDT"
        assert analysis.total_walls == 2
        assert len(analysis.put_walls) == 1
        assert len(analysis.call_walls) == 1


class TestSRLevelModel:
    """Tests for SRLevel data model."""

    def test_create_sr_level(self):
        """Test creating S/R level."""
        level = SRLevel(
            level=1,
            price=41000.0,
            type="PUT_WALL",
            strength=0.8,
            confidence=0.7,
            source="wall_detector",
        )

        assert level.level == 1
        assert level.price == 41000.0
        assert level.type == "PUT_WALL"
        assert level.strength == 0.8


class TestSRLevelsModel:
    """Tests for SRLevels data model."""

    def test_create_sr_levels(self):
        """Test creating S/R levels."""
        sr = SRLevels(
            support=[
                SRLevel(
                    level=1,
                    price=41000.0,
                    type="PUT_WALL",
                    strength=0.8,
                    confidence=0.7,
                    source="wall",
                ),
                SRLevel(
                    level=2,
                    price=40000.0,
                    type="PUT_WALL",
                    strength=0.6,
                    confidence=0.5,
                    source="wall",
                ),
            ],
            resistance=[
                SRLevel(
                    level=1,
                    price=43000.0,
                    type="CALL_WALL",
                    strength=0.7,
                    confidence=0.6,
                    source="wall",
                )
            ],
            stop_loss=SRLevel(
                level=1,
                price=41000.0,
                type="PUT_WALL_SL",
                strength=0.8,
                confidence=0.7,
                source="wall",
            ),
            risk_reward_ratio=2.5,
        )

        assert len(sr.support) == 2
        assert len(sr.resistance) == 1
        assert sr.stop_loss is not None
        assert sr.risk_reward_ratio == 2.5


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestWallDetectorEdgeCases:
    """Edge case tests for wall detection."""

    @pytest.fixture
    def detector(self):
        return WallDetector(WallDetectorConfig())

    def test_empty_chain(self, detector):
        """Test with empty options chain."""
        chain = OptionsChain(underlying="BTCUSDT", spot_price=42000.0, timestamp=datetime.utcnow())

        result = detector.detect(chain)

        assert result is not None
        assert result.total_walls == 0

    def test_single_strike(self, detector):
        """Test with single strike."""
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=5000,
            total_put_oi=5000,
        )

        chain.strikes = {
            42000.0: StrikeData(
                strike=42000.0,
                call=OptionData(open_interest=5000, volume=2000),
                put=OptionData(open_interest=5000, volume=2000),
            )
        }

        result = detector.detect(chain)

        # Strike at spot is neither above nor below
        assert result is not None

    def test_extreme_concentration(self, detector):
        """Test with extreme OI concentration."""
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=10000,
            total_put_oi=10000,
        )

        chain.strikes = {
            40000.0: StrikeData(
                strike=40000.0,
                call=OptionData(open_interest=100),
                put=OptionData(open_interest=8000),  # 40% concentration - major wall
            ),
            42000.0: StrikeData(
                strike=42000.0,
                call=OptionData(open_interest=1000),
                put=OptionData(open_interest=1000),
            ),
        }

        result = detector.detect(chain)

        # Should detect major wall
        assert len(result.put_walls) > 0
        assert result.put_walls[0].is_major_wall == True


# =============================================================================
# Integration Tests
# =============================================================================


class TestWallIntegration:
    """Integration tests for wall detection and S/R levels."""

    def test_full_wall_to_sr_flow(
        self, wall_detector, sr_calculator, sample_options_chain_with_walls
    ):
        """Test complete flow from wall detection to S/R generation."""
        # Detect walls
        wall_analysis = wall_detector.detect(sample_options_chain_with_walls)

        # Calculate S/R levels
        sr_levels = sr_calculator.calculate(sample_options_chain_with_walls)

        # Verify complete flow
        assert wall_analysis.total_walls >= 0
        # S/R levels should be calculated (may be empty if no walls)
        assert sr_levels is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
