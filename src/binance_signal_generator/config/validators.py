"""
Configuration validators for the Binance Signal Generator.

Validates configuration values to ensure they are within acceptable ranges
and properly formatted.
"""

from typing import List, Tuple
from dataclasses import dataclass

from binance_signal_generator.config.loader import Config
from binance_signal_generator.utils.exceptions import (
    InvalidConfigError,
    MissingAPIKeyError,
)


@dataclass
class ValidationResult:
    """Result of configuration validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    def add_error(self, error: str):
        """Add an error and mark as invalid."""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str):
        """Add a warning."""
        self.warnings.append(warning)


def validate_config(config: Config) -> ValidationResult:
    """
    Validate the entire configuration.
    
    Args:
        config: Configuration object to validate
        
    Returns:
        ValidationResult with any errors or warnings
    """
    result = ValidationResult(is_valid=True, errors=[], warnings=[])
    
    # Validate each section
    _validate_binance(config, result)
    _validate_ranking(config, result)
    _validate_pipeline(config, result)
    _validate_whale(config, result)
    _validate_walls(config, result)
    _validate_analysis(config, result)
    _validate_output(config, result)
    _validate_logging(config, result)
    
    return result


def _validate_binance(config: Config, result: ValidationResult):
    """Validate Binance configuration."""
    binance = config.binance
    
    # API credentials
    if not binance.api_key:
        result.add_error("Binance API key is not set (set BINANCE_API_KEY environment variable)")
    
    if not binance.api_secret:
        result.add_error("Binance API secret is not set (set BINANCE_API_SECRET environment variable)")
    
    # Rate limits
    if binance.rate_limit_requests_per_second <= 0:
        result.add_error("rate_limit.requests_per_second must be positive")
    
    if binance.rate_limit_burst <= 0:
        result.add_error("rate_limit.burst must be positive")
    
    # Timeouts
    if binance.timeout_connect_seconds <= 0:
        result.add_error("timeout.connect_seconds must be positive")
    
    if binance.timeout_read_seconds <= 0:
        result.add_error("timeout.read_seconds must be positive")


def _validate_ranking(config: Config, result: ValidationResult):
    """Validate ranking configuration."""
    ranking = config.ranking
    
    # Top assets count
    if ranking.top_assets_count < 1:
        result.add_error("ranking.top_assets_count must be at least 1")
    
    if ranking.top_assets_count > 20:
        result.add_warning("ranking.top_assets_count > 20 may cause slow execution")
    
    # Min activity score
    if not 0 <= ranking.min_activity_score <= 1:
        result.add_error("ranking.min_activity_score must be between 0 and 1")
    
    # Weights must sum to 1.0
    weight_sum = (
        ranking.weight_oi_change +
        ranking.weight_volume_spike +
        ranking.weight_iv_interest +
        ranking.weight_pcr_extreme +
        ranking.weight_whale_activity +
        ranking.weight_total_volume
    )
    
    if abs(weight_sum - 1.0) > 0.01:
        result.add_error(
            f"ranking.scoring_weights must sum to 1.0 (got {weight_sum:.2f})"
        )
    
    # Individual weights
    for name, weight in [
        ("oi_change", ranking.weight_oi_change),
        ("volume_spike", ranking.weight_volume_spike),
        ("iv_interest", ranking.weight_iv_interest),
        ("pcr_extreme", ranking.weight_pcr_extreme),
        ("whale_activity", ranking.weight_whale_activity),
        ("total_volume", ranking.weight_total_volume),
    ]:
        if not 0 <= weight <= 1:
            result.add_error(f"ranking.scoring_weights.{name} must be between 0 and 1")


def _validate_pipeline(config: Config, result: ValidationResult):
    """Validate pipeline configuration."""
    pipeline = config.pipeline
    
    # Total timeout
    if pipeline.timeout_total_seconds <= 0:
        result.add_error("pipeline.timeout.total_seconds must be positive")
    
    # Stage timeouts should sum to less than total
    stage_sum = (
        pipeline.timeout_activity_scan_seconds +
        pipeline.timeout_asset_selection_seconds +
        pipeline.timeout_data_fetch_seconds +
        pipeline.timeout_analysis_seconds +
        pipeline.timeout_whale_wall_seconds +
        pipeline.timeout_signal_output_seconds
    )
    
    if stage_sum > pipeline.timeout_total_seconds:
        result.add_warning(
            f"Pipeline stage timeouts ({stage_sum}s) exceed total timeout ({pipeline.timeout_total_seconds}s)"
        )


def _validate_whale(config: Config, result: ValidationResult):
    """Validate whale configuration."""
    whale = config.whale
    
    # Thresholds
    if whale.min_premium <= 0:
        result.add_error("whale.min_premium must be positive")
    
    if whale.block_threshold <= 0:
        result.add_error("whale.block_threshold must be positive")
    
    if whale.block_threshold < whale.min_premium:
        result.add_warning(
            "whale.block_threshold is less than min_premium - block trades won't be detected"
        )
    
    # Lookback
    if whale.lookback_hours <= 0:
        result.add_error("whale.lookback_hours must be positive")
    
    if whale.lookback_hours > 72:
        result.add_warning(
            f"whale.lookback_hours ({whale.lookback_hours}h) is large and may slow execution"
        )
    
    # Confidence boost
    if not 0 <= whale.confidence_boost_max <= 0.5:
        result.add_error("whale.confidence_boost.max_boost must be between 0 and 0.5")


def _validate_walls(config: Config, result: ValidationResult):
    """Validate walls configuration."""
    walls = config.walls
    
    # Thresholds
    if not 0 < walls.min_oi_percentage <= 1:
        result.add_error("walls.min_oi_percentage must be between 0 and 1")
    
    if not 0 < walls.major_threshold <= 1:
        result.add_error("walls.major_threshold must be between 0 and 1")
    
    if walls.major_threshold < walls.min_oi_percentage:
        result.add_warning("walls.major_threshold is less than min_oi_percentage")
    
    # Max levels
    if walls.max_levels < 1:
        result.add_error("walls.max_levels must be at least 1")
    
    if walls.max_levels > 5:
        result.add_warning("walls.max_levels > 5 may clutter signals")
    
    # Strength factors
    strength_sum = walls.strength_distance_factor + walls.strength_oi_factor
    if abs(strength_sum - 1.0) > 0.01:
        result.add_error(
            f"walls.strength factors must sum to 1.0 (got {strength_sum:.2f})"
        )


def _validate_analysis(config: Config, result: ValidationResult):
    """Validate analysis configuration."""
    analysis = config.analysis
    
    # Signal weights must sum to 1.0 (including whale)
    signal_weights = [
        ("iv", analysis.iv_weight if analysis.iv_enabled else 0),
        ("pcr", analysis.pcr_weight if analysis.pcr_enabled else 0),
        ("oi", analysis.oi_weight if analysis.oi_enabled else 0),
        ("max_pain", analysis.max_pain_weight if analysis.max_pain_enabled else 0),
    ]
    
    weight_sum = sum(w for _, w in signal_weights)
    
    # Note: Whale weight is separate in config.whale
    
    # IV thresholds
    if not 0 <= analysis.iv_threshold_high <= 1:
        result.add_error("analysis.iv.thresholds.high must be between 0 and 1")
    
    if not 0 <= analysis.iv_threshold_low <= 1:
        result.add_error("analysis.iv.thresholds.low must be between 0 and 1")
    
    if analysis.iv_threshold_low >= analysis.iv_threshold_high:
        result.add_error("analysis.iv.thresholds.low must be less than high")
    
    # PCR thresholds
    if analysis.pcr_threshold_put_high <= 0:
        result.add_error("analysis.pcr.thresholds.put_high must be positive")
    
    if analysis.pcr_threshold_call_high <= 0:
        result.add_error("analysis.pcr.thresholds.call_high must be positive")


def _validate_output(config: Config, result: ValidationResult):
    """Validate output configuration."""
    output = config.output
    
    # Confidence
    if not 0 <= output.min_confidence <= 1:
        result.add_error("output.signals.min_confidence must be between 0 and 1")
    
    # Risk reward
    if output.min_risk_reward <= 0:
        result.add_error("output.signals.min_risk_reward must be positive")
    
    # Stop loss distances
    if output.stop_loss_min_distance_pct >= output.stop_loss_max_distance_pct:
        result.add_error(
            "output.stop_loss.min_distance_pct must be less than max_distance_pct"
        )
    
    # Take profit ratios must sum to 1.0
    tp_sum = output.take_profit_ratio_1 + output.take_profit_ratio_2 + output.take_profit_ratio_3
    if abs(tp_sum - 1.0) > 0.01:
        result.add_error(
            f"output.take_profit.ratios must sum to 1.0 (got {tp_sum:.2f})"
        )
    
    # Database
    if output.database_enabled and not output.database_path:
        result.add_error("output.database.path is required when database is enabled")


def _validate_logging(config: Config, result: ValidationResult):
    """Validate logging configuration."""
    logging = config.logging
    
    # Log level
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if logging.level.upper() not in valid_levels:
        result.add_error(
            f"logging.level must be one of {valid_levels} (got {logging.level})"
        )
    
    # File settings
    if logging.file_enabled:
        if not logging.file_path:
            result.add_error("logging.file.path is required when file logging is enabled")
        
        if logging.file_max_size_mb <= 0:
            result.add_error("logging.file.max_size_mb must be positive")
        
        if logging.file_backup_count < 0:
            result.add_error("logging.file.backup_count must be non-negative")


def validate_api_credentials(config: Config) -> Tuple[bool, str]:
    """
    Validate that API credentials are present and properly formatted.
    
    Args:
        config: Configuration object
        
    Returns:
        Tuple of (is_valid, message)
    """
    if not config.binance.api_key:
        return False, "API key not set"
    
    if not config.binance.api_secret:
        return False, "API secret not set"
    
    # Basic format check
    if len(config.binance.api_key) < 10:
        return False, "API key appears to be too short"
    
    if len(config.binance.api_secret) < 10:
        return False, "API secret appears to be too short"
    
    return True, "Credentials valid"


def ensure_valid_config(config: Config) -> None:
    """
    Ensure configuration is valid, raising an error if not.
    
    Args:
        config: Configuration to validate
        
    Raises:
        InvalidConfigError: If configuration has errors
    """
    result = validate_config(config)
    
    if not result.is_valid:
        error_msg = "Configuration validation failed:\n" + "\n".join(
            f"  - {e}" for e in result.errors
        )
        raise InvalidConfigError(error_msg)
    
    # Log warnings
    from binance_signal_generator.utils.logging import logger
    for warning in result.warnings:
        logger.warning(warning)
