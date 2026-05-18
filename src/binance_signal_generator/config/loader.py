"""
Configuration loader for the Binance Signal Generator.

Loads configuration from YAML files with support for:
- Environment variable substitution
- Configuration validation
- Default values
- .env file loading
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv

from binance_signal_generator.utils.exceptions import (
    ConfigurationError,
    MissingConfigError,
    InvalidConfigError,
    MissingAPIKeyError,
)
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


def load_env_file(env_path: Optional[str] = None) -> None:
    """
    Load environment variables from .env file.
    
    Searches for .env file in the following order:
    1. Specified env_path
    2. ./env (current directory)
    3. ./.env (current directory)
    4. Parent directories (walking up)
    
    Args:
        env_path: Optional path to .env file
    """
    if env_path:
        # Use specified path
        load_dotenv(env_path, override=True)
        logger.debug(f"Loaded environment from: {env_path}")
        return
    
    # Search for .env file
    search_paths = [
        Path.cwd() / ".env",
        Path.cwd() / "env",
        Path.cwd().parent / ".env",
    ]
    
    for path in search_paths:
        if path.exists():
            load_dotenv(path, override=True)
            logger.debug(f"Loaded environment from: {path}")
            return
    
    # Try default dotenv behavior (searches current and parent directories)
    load_dotenv(override=True)


# Environment variable pattern: ${VAR_NAME} or ${VAR_NAME:default}
ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def substitute_env_variables(value: Any) -> Any:
    """
    Recursively substitute environment variables in configuration values.
    
    Supports:
    - ${VAR_NAME} - Required, raises error if not set
    - ${VAR_NAME:default} - Optional, uses default if not set
    
    Args:
        value: Configuration value (can be str, dict, list, etc.)
        
    Returns:
        Value with environment variables substituted
        
    Raises:
        MissingConfigError: If required environment variable is not set
    """
    if isinstance(value, str):
        def replace_env(match):
            var_name = match.group(1)
            default = match.group(2)
            
            env_value = os.environ.get(var_name)
            
            if env_value is not None:
                return env_value
            elif default is not None:
                return default
            else:
                raise MissingConfigError(
                    f"Required environment variable '{var_name}' is not set"
                )
        
        return ENV_PATTERN.sub(replace_env, value)
    
    elif isinstance(value, dict):
        return {k: substitute_env_variables(v) for k, v in value.items()}
    
    elif isinstance(value, list):
        return [substitute_env_variables(item) for item in value]
    
    else:
        return value


@dataclass
class BinanceConfig:
    """Binance API configuration."""
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = False
    rate_limit_requests_per_second: int = 10
    rate_limit_burst: int = 20
    timeout_connect_seconds: int = 10
    timeout_read_seconds: int = 30


@dataclass
class RankingConfig:
    """Asset ranking configuration."""
    top_assets_count: int = 5
    min_activity_score: float = 0.30
    
    # Scoring weights
    weight_oi_change: float = 0.25
    weight_volume_spike: float = 0.20
    weight_iv_interest: float = 0.15
    weight_pcr_extreme: float = 0.15
    weight_whale_activity: float = 0.15
    weight_total_volume: float = 0.10
    
    # Thresholds
    oi_change_max_pct: float = 20.0
    volume_spike_max: float = 5.0
    total_volume_max: float = 100_000_000
    
    # Liquidity requirements
    # BUG FIX (Bug #15): Lowered defaults to match config.yaml recommendations.
    # Previously, defaults were $5M / 10 strikes, which rejected most Binance
    # Options assets. Most crypto options have volume well below $5M and fewer
    # than 10 active strikes. The $100K / 5 strike threshold allows more assets
    # through while still filtering out completely illiquid ones.
    min_options_volume: float = 100_000  # $100K minimum (lowered from $5M)
    min_active_strikes: int = 5  # Lowered from 10
    
    # Exclusions
    excluded_symbols: list = field(default_factory=list)


@dataclass
class PipelineConfig:
    """Pipeline execution configuration."""
    timeout_total_seconds: int = 600
    timeout_activity_scan_seconds: int = 30
    timeout_asset_selection_seconds: int = 10
    timeout_data_fetch_seconds: int = 120
    timeout_analysis_seconds: int = 180
    timeout_whale_wall_seconds: int = 60
    timeout_signal_output_seconds: int = 60


@dataclass
class IntradayConfig:
    """Intraday data configuration for 15-min trading system."""
    # Enable intraday mode
    enabled: bool = True
    
    # Intraday OI settings
    oi_period: str = "15m"  # For intraday OI momentum
    oi_limit: int = 96  # 24 hours of 15-min data
    
    # Intraday volume settings
    volume_interval: str = "15m"  # For volume spike detection
    volume_limit: int = 48  # 12 hours for avg comparison
    
    # Price action settings
    kline_interval: str = "15m"
    kline_limit: int = 48  # 12 hours of candles
    
    # Scoring mode: "intraday" uses shorter timeframes, "daily" uses daily data
    scoring_mode: str = "intraday"
    
    # Execution interval in minutes
    execution_interval_minutes: int = 15


@dataclass
class AssetWhaleThreshold:
    """Asset-specific whale detection thresholds."""
    min_premium: float = 100_000
    block_threshold: float = 500_000


@dataclass
class WhaleConfig:
    """Whale detection configuration."""
    min_premium: float = 100_000  # Default threshold
    block_threshold: float = 500_000  # Default block threshold
    lookback_hours: int = 24
    confidence_boost_enabled: bool = True
    confidence_boost_max: float = 0.15
    confidence_boost_net_volume_threshold: float = 20_000_000
    # Asset-specific thresholds (symbol -> thresholds)
    asset_thresholds: Dict[str, AssetWhaleThreshold] = field(default_factory=dict)


@dataclass
class WallsConfig:
    """Wall detection configuration."""
    min_oi_percentage: float = 0.15
    major_threshold: float = 0.25
    max_levels: int = 3
    strength_distance_factor: float = 0.30
    strength_oi_factor: float = 0.70


@dataclass
class AnalysisConfig:
    """Options analysis configuration."""
    # IV
    iv_enabled: bool = True
    iv_weight: float = 0.20
    iv_lookback_days: int = 30
    iv_threshold_high: float = 0.75
    iv_threshold_low: float = 0.25
    
    # PCR
    pcr_enabled: bool = True
    pcr_weight: float = 0.25
    pcr_threshold_put_high: float = 1.2
    pcr_threshold_call_high: float = 0.8
    pcr_volume_weight: float = 0.6
    pcr_oi_weight: float = 0.4
    
    # OI
    oi_enabled: bool = True
    oi_weight: float = 0.20
    oi_concentration_threshold: float = 0.15
    
    # Max Pain
    max_pain_enabled: bool = True
    max_pain_weight: float = 0.15
    max_pain_distance_threshold: float = 2.0


@dataclass
class ValidationConfig:
    """Futures validation configuration."""
    liquidity_enabled: bool = True
    liquidity_min_24h_volume: float = 1_000_000
    
    trend_enabled: bool = True
    trend_ema_fast: int = 9
    trend_ema_slow: int = 21
    trend_require_alignment: bool = True
    
    volatility_enabled: bool = True
    volatility_atr_period: int = 14
    volatility_extreme_multiplier: float = 3.0
    
    funding_enabled: bool = True
    funding_max_absolute_rate: float = 0.001


@dataclass
class OutputConfig:
    """Signal output configuration."""
    # JSON output
    json_enabled: bool = True
    json_pretty_print: bool = False
    json_include_metadata: bool = True
    json_include_selected_assets: bool = True
    
    # Signal filtering
    min_confidence: float = 0.55
    max_per_asset: int = 1
    max_per_execution: int = 5
    min_risk_reward: float = 1.5
    
    # S/R levels
    sr_max_levels: int = 3
    sr_include_max_pain: bool = True
    sr_min_wall_strength: float = 0.50
    
    # Stop loss
    stop_loss_method: str = "wall"
    stop_loss_buffer_pct: float = 0.2
    stop_loss_min_distance_pct: float = 0.5
    stop_loss_max_distance_pct: float = 3.0
    
    # Take profit
    take_profit_levels: int = 3
    take_profit_ratio_1: float = 0.5
    take_profit_ratio_2: float = 0.3
    take_profit_ratio_3: float = 0.2
    
    # Database
    database_enabled: bool = True
    database_path: str = "./data/signals.db"
    database_rotation: str = "weekly"
    database_retention_weeks: int = 4


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "json"
    file_enabled: bool = True
    file_path: str = "./logs/signal_generator.log"
    file_max_size_mb: int = 10
    file_backup_count: int = 5
    console_enabled: bool = False
    console_colorize: bool = False
    mask_sensitive: bool = True


@dataclass
class Config:
    """
    Main configuration class containing all settings.
    
    This class holds all configuration for the signal generator,
    organized into logical sections.
    """
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    ranking: RankingConfig = field(default_factory=RankingConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    intraday: IntradayConfig = field(default_factory=IntradayConfig)
    whale: WhaleConfig = field(default_factory=WhaleConfig)
    walls: WallsConfig = field(default_factory=WallsConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    # Path to the config file that was loaded
    config_path: Optional[str] = None
    
    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """
        Load configuration from a YAML file.
        
        Args:
            path: Path to the YAML configuration file
            
        Returns:
            Config object with loaded settings
            
        Raises:
            ConfigurationError: If configuration is invalid
            FileNotFoundError: If config file doesn't exist
        """
        config_path = Path(path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        logger.info(f"Loading configuration from {path}")
        
        try:
            with open(config_path, "r") as f:
                raw_config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Failed to parse YAML: {e}")
        
        if not raw_config:
            raise ConfigurationError("Empty configuration file")
        
        # Substitute environment variables
        config_data = substitute_env_variables(raw_config)
        
        # Build config object
        return cls._build_config(config_data, str(config_path))
    
    @classmethod
    def _build_config(cls, data: Dict[str, Any], config_path: str) -> "Config":
        """Build Config object from parsed YAML data."""
        config = cls()
        config.config_path = config_path
        
        # Parse each section
        if "binance" in data:
            config.binance = cls._parse_binance(data["binance"])
        
        if "ranking" in data:
            config.ranking = cls._parse_ranking(data["ranking"])
        
        if "pipeline" in data:
            config.pipeline = cls._parse_pipeline(data["pipeline"])
        
        if "intraday" in data:
            config.intraday = cls._parse_intraday(data["intraday"])
        
        if "whale" in data:
            config.whale = cls._parse_whale(data["whale"])
        
        if "walls" in data:
            config.walls = cls._parse_walls(data["walls"])
        
        if "analysis" in data:
            config.analysis = cls._parse_analysis(data["analysis"])
        
        if "validation" in data:
            config.validation = cls._parse_validation(data["validation"])
        
        if "output" in data:
            config.output = cls._parse_output(data["output"])
        
        if "logging" in data:
            config.logging = cls._parse_logging(data["logging"])
        
        return config
    
    @staticmethod
    def _parse_binance(data: Dict) -> BinanceConfig:
        """Parse binance section."""
        rate_limit = data.get("rate_limit", {})
        timeout = data.get("timeout", {})
        
        return BinanceConfig(
            api_key=data.get("api_key", ""),
            api_secret=data.get("api_secret", ""),
            testnet=data.get("testnet", False),
            rate_limit_requests_per_second=rate_limit.get("requests_per_second", 10),
            rate_limit_burst=rate_limit.get("burst", 20),
            timeout_connect_seconds=timeout.get("connect_seconds", 10),
            timeout_read_seconds=timeout.get("read_seconds", 30),
        )
    
    @staticmethod
    def _parse_ranking(data: Dict) -> RankingConfig:
        """Parse ranking section."""
        weights = data.get("scoring_weights", {})
        thresholds = data.get("thresholds", {})
        
        return RankingConfig(
            top_assets_count=data.get("top_assets_count", 5),
            min_activity_score=data.get("min_activity_score", 0.30),
            weight_oi_change=weights.get("oi_change", 0.25),
            weight_volume_spike=weights.get("volume_spike", 0.20),
            weight_iv_interest=weights.get("iv_interest", 0.15),
            weight_pcr_extreme=weights.get("pcr_extreme", 0.15),
            weight_whale_activity=weights.get("whale_activity", 0.15),
            weight_total_volume=weights.get("total_volume", 0.10),
            oi_change_max_pct=thresholds.get("oi_change_max_pct", 20.0),
            volume_spike_max=thresholds.get("volume_spike_max", 5.0),
            total_volume_max=thresholds.get("total_volume_max", 100_000_000),
            min_options_volume=data.get("min_options_volume", 100_000),  # BUG FIX (Bug #15): Lowered default from $5M
            min_active_strikes=data.get("min_active_strikes", 5),  # BUG FIX (Bug #15): Lowered default from 10
            excluded_symbols=data.get("excluded_symbols", []),
        )
    
    @staticmethod
    def _parse_pipeline(data: Dict) -> PipelineConfig:
        """Parse pipeline section."""
        timeout = data.get("timeout", {})
        
        return PipelineConfig(
            timeout_total_seconds=timeout.get("total_seconds", 600),
            timeout_activity_scan_seconds=timeout.get("activity_scan_seconds", 30),
            timeout_asset_selection_seconds=timeout.get("asset_selection_seconds", 10),
            timeout_data_fetch_seconds=timeout.get("data_fetch_seconds", 120),
            timeout_analysis_seconds=timeout.get("analysis_seconds", 180),
            timeout_whale_wall_seconds=timeout.get("whale_wall_seconds", 60),
            timeout_signal_output_seconds=timeout.get("signal_output_seconds", 60),
        )
    
    @staticmethod
    def _parse_intraday(data: Dict) -> IntradayConfig:
        """Parse intraday section."""
        return IntradayConfig(
            enabled=data.get("enabled", True),
            oi_period=data.get("oi_period", "15m"),
            oi_limit=data.get("oi_limit", 96),
            volume_interval=data.get("volume_interval", "15m"),
            volume_limit=data.get("volume_limit", 48),
            kline_interval=data.get("kline_interval", "15m"),
            kline_limit=data.get("kline_limit", 48),
            scoring_mode=data.get("scoring_mode", "intraday"),
            execution_interval_minutes=data.get("execution_interval_minutes", 15),
        )
    
    @staticmethod
    def _parse_whale(data: Dict) -> WhaleConfig:
        """Parse whale section."""
        boost = data.get("confidence_boost", {})
        
        # Parse asset-specific thresholds
        asset_thresholds = {}
        for asset, thresholds in data.get("asset_thresholds", {}).items():
            asset_thresholds[asset] = AssetWhaleThreshold(
                min_premium=thresholds.get("min_premium", 100_000),
                block_threshold=thresholds.get("block_threshold", 500_000),
            )
        
        return WhaleConfig(
            min_premium=data.get("min_premium", 100_000),
            block_threshold=data.get("block_threshold", 500_000),
            lookback_hours=data.get("lookback_hours", 24),
            confidence_boost_enabled=boost.get("enabled", True),
            confidence_boost_max=boost.get("max_boost", 0.15),
            confidence_boost_net_volume_threshold=boost.get("net_volume_threshold", 20_000_000),
            asset_thresholds=asset_thresholds,
        )
    
    @staticmethod
    def _parse_walls(data: Dict) -> WallsConfig:
        """Parse walls section."""
        strength = data.get("strength", {})
        
        return WallsConfig(
            min_oi_percentage=data.get("min_oi_percentage", 0.15),
            major_threshold=data.get("major_threshold", 0.25),
            max_levels=data.get("max_levels", 3),
            strength_distance_factor=strength.get("distance_factor", 0.30),
            strength_oi_factor=strength.get("oi_factor", 0.70),
        )
    
    @staticmethod
    def _parse_analysis(data: Dict) -> AnalysisConfig:
        """Parse analysis section."""
        iv = data.get("iv", {})
        pcr = data.get("pcr", {})
        oi = data.get("oi", {})
        max_pain = data.get("max_pain", {})
        
        return AnalysisConfig(
            iv_enabled=iv.get("enabled", True),
            iv_weight=iv.get("weight", 0.20),
            iv_lookback_days=iv.get("lookback_days", 30),
            iv_threshold_high=iv.get("thresholds", {}).get("high", 0.75),
            iv_threshold_low=iv.get("thresholds", {}).get("low", 0.25),
            pcr_enabled=pcr.get("enabled", True),
            pcr_weight=pcr.get("weight", 0.25),
            pcr_threshold_put_high=pcr.get("thresholds", {}).get("put_high", 1.2),
            pcr_threshold_call_high=pcr.get("thresholds", {}).get("call_high", 0.8),
            pcr_volume_weight=pcr.get("weighting", {}).get("volume_weight", 0.6),
            pcr_oi_weight=pcr.get("weighting", {}).get("oi_weight", 0.4),
            oi_enabled=oi.get("enabled", True),
            oi_weight=oi.get("weight", 0.20),
            oi_concentration_threshold=oi.get("concentration_threshold", 0.15),
            max_pain_enabled=max_pain.get("enabled", True),
            max_pain_weight=max_pain.get("weight", 0.15),
            max_pain_distance_threshold=max_pain.get("distance_threshold", 2.0),
        )
    
    @staticmethod
    def _parse_validation(data: Dict) -> ValidationConfig:
        """Parse validation section."""
        liquidity = data.get("liquidity", {})
        trend = data.get("trend", {})
        volatility = data.get("volatility", {})
        funding = data.get("funding", {})
        
        return ValidationConfig(
            liquidity_enabled=liquidity.get("enabled", True),
            liquidity_min_24h_volume=liquidity.get("min_24h_volume", 1_000_000),
            trend_enabled=trend.get("enabled", True),
            trend_ema_fast=trend.get("ema_fast", 9),
            trend_ema_slow=trend.get("ema_slow", 21),
            trend_require_alignment=trend.get("require_alignment", True),
            volatility_enabled=volatility.get("enabled", True),
            volatility_atr_period=volatility.get("atr_period", 14),
            volatility_extreme_multiplier=volatility.get("extreme_multiplier", 3.0),
            funding_enabled=funding.get("enabled", True),
            funding_max_absolute_rate=funding.get("max_absolute_rate", 0.001),
        )
    
    @staticmethod
    def _parse_output(data: Dict) -> OutputConfig:
        """Parse output section."""
        json_cfg = data.get("json", {})
        signals = data.get("signals", {})
        sr = data.get("sr_levels", {})
        sl = data.get("stop_loss", {})
        tp = data.get("take_profit", {})
        db = data.get("database", {})
        ratios = tp.get("ratios", {})
        
        return OutputConfig(
            json_enabled=json_cfg.get("enabled", True),
            json_pretty_print=json_cfg.get("pretty_print", False),
            json_include_metadata=json_cfg.get("include_metadata", True),
            json_include_selected_assets=json_cfg.get("include_selected_assets", True),
            min_confidence=signals.get("min_confidence", 0.55),
            max_per_asset=signals.get("max_per_asset", 1),
            max_per_execution=signals.get("max_per_execution", 5),
            min_risk_reward=signals.get("min_risk_reward", 1.5),
            sr_max_levels=sr.get("max_levels", 3),
            sr_include_max_pain=sr.get("include_max_pain", True),
            sr_min_wall_strength=sr.get("min_wall_strength", 0.50),
            stop_loss_method=sl.get("method", "wall"),
            stop_loss_buffer_pct=sl.get("wall_based", {}).get("buffer_pct", 0.2),
            stop_loss_min_distance_pct=sl.get("min_distance_pct", 0.5),
            stop_loss_max_distance_pct=sl.get("max_distance_pct", 3.0),
            take_profit_levels=tp.get("levels", 3),
            take_profit_ratio_1=ratios.get("level_1", 0.5),
            take_profit_ratio_2=ratios.get("level_2", 0.3),
            take_profit_ratio_3=ratios.get("level_3", 0.2),
            database_enabled=db.get("enabled", True),
            database_path=db.get("path", "./data/signals.db"),
            database_rotation=db.get("rotation", "weekly"),
            database_retention_weeks=db.get("retention_weeks", 4),
        )
    
    @staticmethod
    def _parse_logging(data: Dict) -> LoggingConfig:
        """Parse logging section."""
        file = data.get("file", {})
        console = data.get("console", {})
        
        return LoggingConfig(
            level=data.get("level", "INFO"),
            format=data.get("format", "json"),
            file_enabled=file.get("enabled", True),
            file_path=file.get("path", "./logs/signal_generator.log"),
            file_max_size_mb=file.get("max_size_mb", 10),
            file_backup_count=file.get("backup_count", 5),
            console_enabled=console.get("enabled", False),
            console_colorize=console.get("colorize", False),
            mask_sensitive=data.get("mask_sensitive", True),
        )


def load_config(config_path: Optional[str] = None, env_path: Optional[str] = None) -> Config:
    """
    Load configuration with fallbacks.
    
    Automatically loads environment variables from .env file before processing.
    
    Priority for config file:
    1. Specified path
    2. ./config.yaml
    3. ./config/config.yaml
    4. Environment variable BINANCE_SIGNAL_CONFIG
    
    Priority for .env file:
    1. Specified env_path
    2. ./.env in current directory
    3. Parent directories
    
    Args:
        config_path: Optional path to configuration file
        env_path: Optional path to .env file
        
    Returns:
        Config object
        
    Raises:
        ConfigurationError: If no config file found
    """
    # Load environment variables from .env file first
    load_env_file(env_path)
    
    search_paths = []
    
    if config_path:
        search_paths.append(config_path)
    
    search_paths.extend([
        "./config.yaml",
        "./config/config.yaml",
        "~/binance-signal-generator/config.yaml",
    ])
    
    # Check environment variable
    env_config_path = os.environ.get("BINANCE_SIGNAL_CONFIG")
    if env_config_path:
        search_paths.insert(0, env_config_path)
    
    for path in search_paths:
        expanded_path = Path(path).expanduser()
        if expanded_path.exists():
            return Config.from_yaml(str(expanded_path))
    
    # Return default config with environment variables if no file found
    logger.warning("No configuration file found, using defaults")
    config = Config()
    
    # Read API credentials from environment variables
    config.binance.api_key = os.environ.get("BINANCE_API_KEY", "")
    config.binance.api_secret = os.environ.get("BINANCE_API_SECRET", "")
    
    return config
