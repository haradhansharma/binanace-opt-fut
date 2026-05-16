"""
Tests for configuration loading and validation.
"""

import pytest
import tempfile
import os
from pathlib import Path

from binance_signal_generator.config.loader import (
    Config,
    load_config,
    substitute_env_variables,
    BinanceConfig,
)
from binance_signal_generator.config.validators import (
    validate_config,
    ensure_valid_config,
    ValidationResult,
)
from binance_signal_generator.utils.exceptions import InvalidConfigError


class TestSubstituteEnvVariables:
    """Tests for environment variable substitution."""

    def test_substitute_simple(self, monkeypatch):
        """Test simple env var substitution."""
        monkeypatch.setenv("TEST_KEY", "test_value")
        result = substitute_env_variables("${TEST_KEY}")
        assert result == "test_value"

    def test_substitute_with_default(self, monkeypatch):
        """Test substitution with default value."""
        result = substitute_env_variables("${UNDEFINED_VAR:default_value}")
        assert result == "default_value"

    def test_substitute_nested_dict(self, monkeypatch):
        """Test substitution in nested dict."""
        monkeypatch.setenv("API_KEY", "my_key")
        result = substitute_env_variables({"binance": {"api_key": "${API_KEY}", "other": "static"}})
        assert result["binance"]["api_key"] == "my_key"
        assert result["binance"]["other"] == "static"


class TestConfigLoader:
    """Tests for configuration loading."""

    def test_load_default_config(self):
        """Test loading with defaults when no file exists."""
        config = Config()
        assert config.binance.api_key == ""
        assert config.ranking.top_assets_count == 5

    def test_load_from_yaml(self, tmp_path, monkeypatch):
        """Test loading from YAML file."""
        config_content = """
binance:
  api_key: test_key
  api_secret: test_secret
ranking:
  top_assets_count: 10
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        config = Config.from_yaml(str(config_file))

        assert config.binance.api_key == "test_key"
        assert config.binance.api_secret == "test_secret"
        assert config.ranking.top_assets_count == 10

    def test_load_with_env_vars(self, tmp_path, monkeypatch):
        """Test loading with environment variable substitution."""
        monkeypatch.setenv("BINANCE_API_KEY", "env_key")
        monkeypatch.setenv("BINANCE_API_SECRET", "env_secret")

        config_content = """
binance:
  api_key: ${BINANCE_API_KEY}
  api_secret: ${BINANCE_API_SECRET}
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        config = Config.from_yaml(str(config_file))

        assert config.binance.api_key == "env_key"
        assert config.binance.api_secret == "env_secret"


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_valid_config(self):
        """Test validation of valid config."""
        config = Config()
        config.binance.api_key = "valid_key_12345"
        config.binance.api_secret = "valid_secret_12345"

        result = validate_config(config)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_ranking_weights(self):
        """Test validation catches invalid weight sum."""
        config = Config()
        config.ranking.weight_oi_change = 0.5
        config.ranking.weight_volume_spike = 0.5
        config.ranking.weight_iv_interest = 0.2  # Sum > 1

        result = validate_config(config)

        assert not result.is_valid
        assert any("sum to 1.0" in e for e in result.errors)

    def test_invalid_confidence_range(self):
        """Test validation catches invalid confidence."""
        config = Config()
        config.output.min_confidence = 1.5  # Invalid: > 1

        result = validate_config(config)

        assert not result.is_valid
        assert any("min_confidence" in e for e in result.errors)

    def test_ensure_valid_raises(self):
        """Test ensure_valid_config raises on invalid."""
        config = Config()
        config.output.min_confidence = 1.5

        with pytest.raises(InvalidConfigError):
            ensure_valid_config(config)


class TestModels:
    """Tests for data models."""

    def test_options_chain_pcr(self):
        """Test PCR calculation."""
        from binance_signal_generator.models import OptionsChain, StrikeData, OptionData
        from datetime import datetime

        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=100,
            total_put_oi=80,
        )

        assert chain.get_pcr() == 0.8

    def test_signal_direction_enum(self):
        """Test SignalDirection enum."""
        from binance_signal_generator.models import SignalDirection

        assert SignalDirection.LONG.value == "LONG"
        assert SignalDirection.SHORT.value == "SHORT"
        assert SignalDirection.NEUTRAL.value == "NEUTRAL"

    def test_trading_signal_to_dict(self):
        """Test TradingSignal serialization."""
        from binance_signal_generator.models import (
            TradingSignal,
            SignalDirection,
            SignalStrength,
            EntryZone,
            StopLoss,
        )
        from datetime import datetime

        signal = TradingSignal(
            signal_id="SIG_20240115_1430_BTCUSDT_LONG",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            symbol="BTCUSDT",
            asset_rank=1,
            activity_score=0.85,
            direction=SignalDirection.LONG,
            confidence_score=0.78,
            signal_strength=SignalStrength.STRONG,
            entry_zone=EntryZone(min=42150.0, max=42200.0, ideal=42175.0),
            stop_loss=StopLoss(price=41850.0, type="WALL_BASED"),
            risk_reward_ratio=2.1,
        )

        data = signal.to_dict()

        assert data["signal_id"] == "SIG_20240115_1430_BTCUSDT_LONG"
        assert data["symbol"] == "BTCUSDT"
        assert data["direction"] == "LONG"
        assert "entry_zone" in data


class TestExceptions:
    """Tests for custom exceptions."""

    def test_signal_generator_error(self):
        """Test base exception."""
        from binance_signal_generator.utils.exceptions import SignalGeneratorError

        error = SignalGeneratorError("Test error", details={"key": "value"})

        assert str(error) == "Test error - Details: {'key': 'value'}"

    def test_rate_limit_error(self):
        """Test rate limit exception."""
        from binance_signal_generator.utils.exceptions import RateLimitError

        error = RateLimitError("Rate limited", retry_after=60.0)

        assert error.retry_after == 60.0
        assert "60.0s" in str(error)


class TestRateLimiter:
    """Tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_acquire(self):
        """Test basic acquire."""
        from binance_signal_generator.utils.rate_limiter import RateLimiter

        limiter = RateLimiter(requests_per_second=10, burst=5)

        # Should succeed immediately
        await limiter.acquire(1)

        stats = limiter.get_stats()
        assert stats["tokens_available"] < 5  # Consumed 1 token

    @pytest.mark.asyncio
    async def test_rate_limiter_burst(self):
        """Test burst capacity."""
        from binance_signal_generator.utils.rate_limiter import RateLimiter

        limiter = RateLimiter(requests_per_second=1, burst=3)

        # Should allow burst
        for _ in range(3):
            await limiter.acquire(1)

        stats = limiter.get_stats()
        assert stats["tokens_available"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
