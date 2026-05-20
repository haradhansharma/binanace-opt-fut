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
                raise MissingConfigError(f"Required environment variable '{var_name}' is not set")

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
class SentimentConfig:
    """Sentiment analysis configuration (L/S Ratios + Funding Rate)."""

    enabled: bool = True
    weight: float = 0.20

    # L/S Ratio thresholds
    ls_ratio_extreme_high: float = 2.0
    ls_ratio_extreme_low: float = 0.5
    ls_ratio_bullish: float = 1.2
    ls_ratio_bearish: float = 0.8

    # Funding rate thresholds (in decimal)
    funding_extreme_high: float = 0.0005
    funding_extreme_low: float = -0.0005
    funding_bullish: float = 0.0001
    funding_bearish: float = -0.0001

    # Lookback periods
    ls_ratio_lookback_periods: int = 5
    funding_rate_lookback_hours: int = 168

    # Weights for combined sentiment
    top_trader_position_weight: float = 0.35
    top_trader_account_weight: float = 0.25
    funding_rate_weight: float = 0.40

    # Contrarian mode
    use_contrarian_signals: bool = True
    contrarian_extreme_threshold: float = 3.0


@dataclass
class IVConfig:
    """IV (Implied Volatility) analysis configuration."""

    # IV percentile thresholds
    iv_high_threshold: float = 0.75  # 75th percentile
    iv_low_threshold: float = 0.25  # 25th percentile

    # IV value thresholds (annualized)
    iv_high_value: float = 0.80  # 80% annualized
    iv_low_value: float = 0.30  # 30% annualized

    # ATM range for IV calculation (percentage from spot)
    atm_range_pct: float = 5.0  # 5% from spot

    # Minimum strikes for valid analysis
    min_strikes: int = 3


@dataclass
class PCRAnalyzerConfig:
    """Configuration for PCR analysis (pcr_analyzer.py)."""

    # PCR thresholds
    pcr_high_threshold: float = 1.2  # Put-heavy
    pcr_low_threshold: float = 0.8  # Call-heavy
    pcr_extreme_high: float = 1.5  # Very put-heavy
    pcr_extreme_low: float = 0.5  # Very call-heavy

    # Weight for notional PCR vs OI PCR
    volume_weight: float = 0.4  # 40% notional PCR, 60% OI PCR

    # Minimum OI for valid analysis
    min_total_oi: int = 100


@dataclass
class OIAnalyzerConfig:
    """Configuration for OI analysis (oi_analyzer.py)."""

    # OI concentration threshold (crypto-optimized)
    high_oi_concentration: float = 0.04  # 4% of total OI at one strike
    significant_oi_change: float = 0.20  # 20% change is significant

    # Strike analysis
    max_strikes_to_analyze: int = 50

    # Minimum total OI
    min_total_oi: int = 100


@dataclass
class MaxPainAnalyzerConfig:
    """Configuration for Max Pain calculation (max_pain.py)."""

    # Distance threshold for signal (percentage)
    distance_threshold: float = 3.0  # 3% from max pain

    # Magnet strength calculation
    expiry_weight_factor: float = 1.0  # Weight by days to expiry

    # Minimum strikes for calculation
    min_strikes: int = 3


@dataclass
class WallDetectorAnalyzerConfig:
    """Configuration for wall detection (wall_detector.py)."""

    # OI concentration threshold (crypto-optimized)
    min_oi_concentration: float = 0.002  # 0.2% of total OI

    # Major wall threshold
    major_wall_concentration: float = 0.01  # 1% of total OI

    # Distance from spot (in %)
    max_wall_distance: float = 15.0  # 15% from spot

    # Minimum absolute OI
    min_absolute_oi: int = 10


@dataclass
class GammaExposureAnalyzerConfig:
    """Configuration for gamma exposure calculation (gamma_exposure.py)."""

    # GEX significance threshold (as % of total absolute GEX)
    significant_level_threshold: float = 0.05  # 5% of total

    # Minimum OI to consider
    min_oi_threshold: int = 10

    # Price range for flip detection (% from spot)
    flip_search_range: float = 0.30  # ±30% from spot

    # Whether to use simplified delta approximation
    use_simplified_delta: bool = True

    # DTE weighting parameters
    dte_reference_days: float = 7.0
    max_dte_weight: float = 3.0
    min_dte_weight: float = 0.3
    enable_dte_weighting: bool = True


@dataclass
class SignalScorerAnalyzerConfig:
    """Configuration for signal scoring (signal_scorer.py)."""

    # Core weights for each signal type
    iv_weight: float = 0.15
    pcr_weight: float = 0.18
    oi_weight: float = 0.15
    max_pain_weight: float = 0.10
    sentiment_weight: float = 0.16
    gamma_weight: float = 0.10

    # Advanced metrics weights
    oi_flow_weight: float = 0.12
    wall_concentration_weight: float = 0.04
    pcr_strike_alignment_weight: float = 0.08
    whale_flow_weight: float = 0.05

    # Minimum confidence for valid signal
    min_confidence: float = 0.4

    # Agreement threshold
    agreement_threshold: float = 0.6

    # IV value thresholds for crypto
    iv_high_value: float = 0.80
    iv_low_value: float = 0.40


@dataclass
class OrchestratorConfig:
    """Configuration for pipeline orchestrator (orchestrator.py)."""

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

    # Signal strength thresholds
    signal_strength_very_strong: float = 0.80
    signal_strength_strong: float = 0.65
    signal_strength_moderate: float = 0.50

    # OI flow thresholds
    oi_threshold_daily: float = 2.0  # ±2% for daily mode
    oi_threshold_intraday: float = 1.0  # ±1% for intraday mode

    # Technical analysis defaults
    atr_fallback_pct: float = 0.5  # ATR fallback when no data
    max_level_distance_pct: float = 5.0  # Max distance for S/R levels
    max_tp_distance_pct: float = 5.0  # Max TP distance for intraday

    # Output
    output_to_stdout: bool = True
    save_to_database: bool = False


@dataclass
class AssetSelectorConfig:
    """Configuration for asset selection (asset_selector.py)."""

    top_n: int = 5
    min_activity_score: float = 0.15
    min_options_volume: float = 100_000
    min_active_strikes: int = 5
    excluded_symbols: list = field(default_factory=list)


@dataclass
class WhaleDetectorAnalyzerConfig:
    """Configuration for whale detection (whale_detector.py)."""

    # Default premium thresholds
    min_premium: float = 100_000
    block_threshold: float = 500_000

    # Analysis settings
    lookback_hours: int = 24
    min_trades_for_analysis: int = 3

    # Sentiment thresholds
    bullish_threshold: float = 0.3
    bearish_threshold: float = -0.3


@dataclass
class VolumeAnalyzerConfig:
    """Configuration for volume analyzer (volume_analyzer.py)."""

    # Time buckets for analysis
    time_buckets: int = 4

    # Concentration thresholds
    high_concentration_threshold: float = 0.3


@dataclass
class SRLevelCalculatorConfig:
    """Configuration for S/R level calculation (sr_levels.py)."""

    # Number of levels per side
    max_support_levels: int = 3
    max_resistance_levels: int = 3

    # Minimum distance between levels (%)
    min_level_distance_pct: float = 1.0

    # Weight factors
    wall_weight: float = 0.50
    max_pain_weight: float = 0.30
    volume_weight: float = 0.20

    # Default SL/TP distances
    default_sl_distance_pct: float = 2.0
    default_tp_ratios: list = field(default_factory=lambda: [1.5, 3.0, 5.0])


@dataclass
class ActivityScorerConfig:
    """Configuration for activity scorer (activity_scorer.py)."""

    # Weights for each activity driver
    weight_oi_change: float = 0.25
    weight_volume_spike: float = 0.20
    weight_iv_interest: float = 0.15
    weight_pcr_extreme: float = 0.15
    weight_whale_activity: float = 0.15
    weight_total_volume: float = 0.10

    # Thresholds for normalization
    oi_change_max: float = 20.0
    volume_spike_max: float = 5.0
    total_volume_max: float = 10_000_000


@dataclass
class AnalysisConfig:
    """Options analysis configuration."""

    # IV
    iv_enabled: bool = True
    iv_weight: float = 0.20
    iv_lookback_days: int = 30
    iv_threshold_high: float = 0.75
    iv_threshold_low: float = 0.25

    # Detailed IV Config (for IVAnalyzer)
    iv_config: IVConfig = field(default_factory=IVConfig)

    # PCR
    pcr_enabled: bool = True
    pcr_weight: float = 0.25
    pcr_threshold_put_high: float = 1.2
    pcr_threshold_call_high: float = 0.8
    pcr_volume_weight: float = 0.6
    pcr_oi_weight: float = 0.4

    # Detailed PCR Config (for PCRAnalyzer)
    pcr_analyzer_config: PCRAnalyzerConfig = field(default_factory=PCRAnalyzerConfig)

    # OI
    oi_enabled: bool = True
    oi_weight: float = 0.20
    oi_concentration_threshold: float = 0.15

    # Detailed OI Config (for OIAnalyzer)
    oi_analyzer_config: OIAnalyzerConfig = field(default_factory=OIAnalyzerConfig)

    # Max Pain
    max_pain_enabled: bool = True
    max_pain_weight: float = 0.15
    max_pain_distance_threshold: float = 2.0

    # Detailed Max Pain Config (for MaxPainCalculator)
    max_pain_analyzer_config: MaxPainAnalyzerConfig = field(default_factory=MaxPainAnalyzerConfig)

    # Sentiment
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)

    # Wall Detector Config (for WallDetector)
    wall_detector_config: WallDetectorAnalyzerConfig = field(
        default_factory=WallDetectorAnalyzerConfig
    )

    # Gamma Exposure Config (for GammaExposureCalculator)
    gamma_exposure_config: GammaExposureAnalyzerConfig = field(
        default_factory=GammaExposureAnalyzerConfig
    )

    # Signal Scorer Config (for SignalScorer)
    signal_scorer_config: SignalScorerAnalyzerConfig = field(
        default_factory=SignalScorerAnalyzerConfig
    )


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
class StopLossWallBasedConfig:
    """Wall-based stop loss configuration."""

    use_nearest_wall: bool = True
    buffer_pct: float = 0.2


@dataclass
class TakeProfitWallBasedConfig:
    """Wall-based take profit configuration."""

    tp1: str = "nearest_wall"
    tp2: str = "second_wall"
    tp3: str = "third_wall"


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
    stop_loss_wall_based: StopLossWallBasedConfig = field(default_factory=StopLossWallBasedConfig)
    stop_loss_buffer_pct: float = 0.2
    stop_loss_min_distance_pct: float = 0.5
    stop_loss_max_distance_pct: float = 3.0

    # Take profit
    take_profit_levels: int = 3
    take_profit_ratio_1: float = 0.5
    take_profit_ratio_2: float = 0.3
    take_profit_ratio_3: float = 0.2
    take_profit_wall_based: TakeProfitWallBasedConfig = field(
        default_factory=TakeProfitWallBasedConfig
    )

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

    # New config sections for analyzer modules
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    asset_selector: AssetSelectorConfig = field(default_factory=AssetSelectorConfig)
    whale_detector: WhaleDetectorAnalyzerConfig = field(default_factory=WhaleDetectorAnalyzerConfig)
    volume_analyzer: VolumeAnalyzerConfig = field(default_factory=VolumeAnalyzerConfig)
    sr_levels: SRLevelCalculatorConfig = field(default_factory=SRLevelCalculatorConfig)
    activity_scorer: ActivityScorerConfig = field(default_factory=ActivityScorerConfig)

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

        # Parse new config sections
        if "orchestrator" in data:
            config.orchestrator = cls._parse_orchestrator(data["orchestrator"])

        if "asset_selector" in data:
            config.asset_selector = cls._parse_asset_selector(data["asset_selector"])

        if "whale_detector" in data:
            config.whale_detector = cls._parse_whale_detector(data["whale_detector"])

        if "volume_analyzer" in data:
            config.volume_analyzer = cls._parse_volume_analyzer(data["volume_analyzer"])

        if "sr_levels" in data:
            config.sr_levels = cls._parse_sr_levels(data["sr_levels"])

        if "activity_scorer" in data:
            config.activity_scorer = cls._parse_activity_scorer(data["activity_scorer"])

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
            min_options_volume=data.get(
                "min_options_volume", 100_000
            ),  # BUG FIX (Bug #15): Lowered default from $5M
            min_active_strikes=data.get(
                "min_active_strikes", 5
            ),  # BUG FIX (Bug #15): Lowered default from 10
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
        sentiment = data.get("sentiment", {})

        # Parse IV config for IVAnalyzer
        iv_config = IVConfig(
            iv_high_threshold=iv.get("thresholds", {}).get("high", 0.75),
            iv_low_threshold=iv.get("thresholds", {}).get("low", 0.25),
            iv_high_value=iv.get("value_thresholds", {}).get("high", 0.80),
            iv_low_value=iv.get("value_thresholds", {}).get("low", 0.30),
            atm_range_pct=iv.get("atm_range_pct", 5.0),
            min_strikes=iv.get("min_strikes", 3),
        )

        sentiment_config = SentimentConfig(
            enabled=sentiment.get("enabled", True),
            weight=sentiment.get("weight", 0.20),
            ls_ratio_extreme_high=sentiment.get("ls_ratio_extreme_high", 2.0),
            ls_ratio_extreme_low=sentiment.get("ls_ratio_extreme_low", 0.5),
            ls_ratio_bullish=sentiment.get("ls_ratio_bullish", 1.2),
            ls_ratio_bearish=sentiment.get("ls_ratio_bearish", 0.8),
            funding_extreme_high=sentiment.get("funding_extreme_high", 0.0005),
            funding_extreme_low=sentiment.get("funding_extreme_low", -0.0005),
            funding_bullish=sentiment.get("funding_bullish", 0.0001),
            funding_bearish=sentiment.get("funding_bearish", -0.0001),
            ls_ratio_lookback_periods=sentiment.get("ls_ratio_lookback_periods", 5),
            funding_rate_lookback_hours=sentiment.get("funding_rate_lookback_hours", 168),
            top_trader_position_weight=sentiment.get("top_trader_position_weight", 0.35),
            top_trader_account_weight=sentiment.get("top_trader_account_weight", 0.25),
            funding_rate_weight=sentiment.get("funding_rate_weight", 0.40),
            use_contrarian_signals=sentiment.get("use_contrarian_signals", True),
            contrarian_extreme_threshold=sentiment.get("contrarian_extreme_threshold", 3.0),
        )

        # Parse PCR analyzer config
        pcr_analyzer = pcr.get("analyzer", {})
        pcr_analyzer_config = PCRAnalyzerConfig(
            pcr_high_threshold=pcr_analyzer.get("pcr_high_threshold", 1.2),
            pcr_low_threshold=pcr_analyzer.get("pcr_low_threshold", 0.8),
            pcr_extreme_high=pcr_analyzer.get("pcr_extreme_high", 1.5),
            pcr_extreme_low=pcr_analyzer.get("pcr_extreme_low", 0.5),
            volume_weight=pcr_analyzer.get("volume_weight", 0.4),
            min_total_oi=pcr_analyzer.get("min_total_oi", 100),
        )

        # Parse OI analyzer config
        oi_analyzer = oi.get("analyzer", {})
        oi_analyzer_config = OIAnalyzerConfig(
            high_oi_concentration=oi_analyzer.get("high_oi_concentration", 0.04),
            significant_oi_change=oi_analyzer.get("significant_oi_change", 0.20),
            max_strikes_to_analyze=oi_analyzer.get("max_strikes_to_analyze", 50),
            min_total_oi=oi_analyzer.get("min_total_oi", 100),
        )

        # Parse Max Pain analyzer config
        max_pain_analyzer = max_pain.get("analyzer", {})
        max_pain_analyzer_config = MaxPainAnalyzerConfig(
            distance_threshold=max_pain_analyzer.get("distance_threshold", 3.0),
            expiry_weight_factor=max_pain_analyzer.get("expiry_weight_factor", 1.0),
            min_strikes=max_pain_analyzer.get("min_strikes", 3),
        )

        # Parse Wall Detector config
        wall_detector = data.get("wall_detector", {})
        wall_detector_config = WallDetectorAnalyzerConfig(
            min_oi_concentration=wall_detector.get("min_oi_concentration", 0.002),
            major_wall_concentration=wall_detector.get("major_wall_concentration", 0.01),
            max_wall_distance=wall_detector.get("max_wall_distance", 15.0),
            min_absolute_oi=wall_detector.get("min_absolute_oi", 10),
        )

        # Parse Gamma Exposure config
        gamma_exposure = data.get("gamma_exposure", {})
        gamma_exposure_config = GammaExposureAnalyzerConfig(
            significant_level_threshold=gamma_exposure.get("significant_level_threshold", 0.05),
            min_oi_threshold=gamma_exposure.get("min_oi_threshold", 10),
            flip_search_range=gamma_exposure.get("flip_search_range", 0.30),
            use_simplified_delta=gamma_exposure.get("use_simplified_delta", True),
            dte_reference_days=gamma_exposure.get("dte_reference_days", 7.0),
            max_dte_weight=gamma_exposure.get("max_dte_weight", 3.0),
            min_dte_weight=gamma_exposure.get("min_dte_weight", 0.3),
            enable_dte_weighting=gamma_exposure.get("enable_dte_weighting", True),
        )

        # Parse Signal Scorer config
        signal_scorer = data.get("signal_scorer", {})
        signal_scorer_config = SignalScorerAnalyzerConfig(
            iv_weight=signal_scorer.get("iv_weight", 0.15),
            pcr_weight=signal_scorer.get("pcr_weight", 0.18),
            oi_weight=signal_scorer.get("oi_weight", 0.15),
            max_pain_weight=signal_scorer.get("max_pain_weight", 0.10),
            sentiment_weight=signal_scorer.get("sentiment_weight", 0.16),
            gamma_weight=signal_scorer.get("gamma_weight", 0.10),
            oi_flow_weight=signal_scorer.get("oi_flow_weight", 0.12),
            wall_concentration_weight=signal_scorer.get("wall_concentration_weight", 0.04),
            pcr_strike_alignment_weight=signal_scorer.get("pcr_strike_alignment_weight", 0.08),
            whale_flow_weight=signal_scorer.get("whale_flow_weight", 0.05),
            min_confidence=signal_scorer.get("min_confidence", 0.4),
            agreement_threshold=signal_scorer.get("agreement_threshold", 0.6),
            iv_high_value=signal_scorer.get("iv_high_value", 0.80),
            iv_low_value=signal_scorer.get("iv_low_value", 0.40),
        )

        return AnalysisConfig(
            iv_enabled=iv.get("enabled", True),
            iv_weight=iv.get("weight", 0.20),
            iv_lookback_days=iv.get("lookback_days", 30),
            iv_threshold_high=iv.get("thresholds", {}).get("high", 0.75),
            iv_threshold_low=iv.get("thresholds", {}).get("low", 0.25),
            iv_config=iv_config,
            pcr_enabled=pcr.get("enabled", True),
            pcr_weight=pcr.get("weight", 0.25),
            pcr_threshold_put_high=pcr.get("thresholds", {}).get("put_high", 1.2),
            pcr_threshold_call_high=pcr.get("thresholds", {}).get("call_high", 0.8),
            pcr_volume_weight=pcr.get("weighting", {}).get("volume_weight", 0.6),
            pcr_oi_weight=pcr.get("weighting", {}).get("oi_weight", 0.4),
            pcr_analyzer_config=pcr_analyzer_config,
            oi_enabled=oi.get("enabled", True),
            oi_weight=oi.get("weight", 0.20),
            oi_concentration_threshold=oi.get("concentration_threshold", 0.15),
            oi_analyzer_config=oi_analyzer_config,
            max_pain_enabled=max_pain.get("enabled", True),
            max_pain_weight=max_pain.get("weight", 0.15),
            max_pain_distance_threshold=max_pain.get("distance_threshold", 2.0),
            max_pain_analyzer_config=max_pain_analyzer_config,
            sentiment=sentiment_config,
            wall_detector_config=wall_detector_config,
            gamma_exposure_config=gamma_exposure_config,
            signal_scorer_config=signal_scorer_config,
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
        sl_wall = sl.get("wall_based", {})
        tp_wall = tp.get("wall_based", {})

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
            stop_loss_wall_based=StopLossWallBasedConfig(
                use_nearest_wall=sl_wall.get("use_nearest_wall", True),
                buffer_pct=sl_wall.get("buffer_pct", 0.2),
            ),
            stop_loss_buffer_pct=sl.get("wall_based", {}).get("buffer_pct", 0.2),
            stop_loss_min_distance_pct=sl.get("min_distance_pct", 0.5),
            stop_loss_max_distance_pct=sl.get("max_distance_pct", 3.0),
            take_profit_levels=tp.get("levels", 3),
            take_profit_ratio_1=ratios.get("level_1", 0.5),
            take_profit_ratio_2=ratios.get("level_2", 0.3),
            take_profit_ratio_3=ratios.get("level_3", 0.2),
            take_profit_wall_based=TakeProfitWallBasedConfig(
                tp1=tp_wall.get("tp1", "nearest_wall"),
                tp2=tp_wall.get("tp2", "second_wall"),
                tp3=tp_wall.get("tp3", "third_wall"),
            ),
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

    @staticmethod
    def _parse_orchestrator(data: Dict) -> OrchestratorConfig:
        """Parse orchestrator section."""
        return OrchestratorConfig(
            timeout_seconds=data.get("timeout_seconds", 600),
            activity_scan_timeout=data.get("activity_scan_timeout", 60),
            data_fetch_timeout=data.get("data_fetch_timeout", 180),
            analysis_timeout=data.get("analysis_timeout", 180),
            top_n_assets=data.get("top_n_assets", 5),
            min_activity_score=data.get("min_activity_score", 0.30),
            min_signal_confidence=data.get("min_signal_confidence", 0.50),
            max_signals_per_run=data.get("max_signals_per_run", 5),
            # Signal strength thresholds
            signal_strength_very_strong=data.get("signal_strength_very_strong", 0.80),
            signal_strength_strong=data.get("signal_strength_strong", 0.65),
            signal_strength_moderate=data.get("signal_strength_moderate", 0.50),
            # OI flow thresholds
            oi_threshold_daily=data.get("oi_threshold_daily", 2.0),
            oi_threshold_intraday=data.get("oi_threshold_intraday", 1.0),
            # Technical analysis defaults
            atr_fallback_pct=data.get("atr_fallback_pct", 0.5),
            max_level_distance_pct=data.get("max_level_distance_pct", 5.0),
            max_tp_distance_pct=data.get("max_tp_distance_pct", 5.0),
            # Output
            output_to_stdout=data.get("output_to_stdout", True),
            save_to_database=data.get("save_to_database", False),
        )

    @staticmethod
    def _parse_asset_selector(data: Dict) -> AssetSelectorConfig:
        """Parse asset_selector section."""
        return AssetSelectorConfig(
            top_n=data.get("top_n", 5),
            min_activity_score=data.get("min_activity_score", 0.15),
            min_options_volume=data.get("min_options_volume", 100_000),
            min_active_strikes=data.get("min_active_strikes", 5),
            excluded_symbols=data.get("excluded_symbols", []),
        )

    @staticmethod
    def _parse_whale_detector(data: Dict) -> WhaleDetectorAnalyzerConfig:
        """Parse whale_detector section."""
        return WhaleDetectorAnalyzerConfig(
            min_premium=data.get("min_premium", 100_000),
            block_threshold=data.get("block_threshold", 500_000),
            lookback_hours=data.get("lookback_hours", 24),
            min_trades_for_analysis=data.get("min_trades_for_analysis", 3),
            bullish_threshold=data.get("bullish_threshold", 0.3),
            bearish_threshold=data.get("bearish_threshold", -0.3),
        )

    @staticmethod
    def _parse_volume_analyzer(data: Dict) -> VolumeAnalyzerConfig:
        """Parse volume_analyzer section."""
        return VolumeAnalyzerConfig(
            time_buckets=data.get("time_buckets", 4),
            high_concentration_threshold=data.get("high_concentration_threshold", 0.3),
        )

    @staticmethod
    def _parse_sr_levels(data: Dict) -> SRLevelCalculatorConfig:
        """Parse sr_levels section."""
        return SRLevelCalculatorConfig(
            max_support_levels=data.get("max_support_levels", 3),
            max_resistance_levels=data.get("max_resistance_levels", 3),
            min_level_distance_pct=data.get("min_level_distance_pct", 1.0),
            wall_weight=data.get("wall_weight", 0.50),
            max_pain_weight=data.get("max_pain_weight", 0.30),
            volume_weight=data.get("volume_weight", 0.20),
            default_sl_distance_pct=data.get("default_sl_distance_pct", 2.0),
            default_tp_ratios=data.get("default_tp_ratios", [1.5, 3.0, 5.0]),
        )

    @staticmethod
    def _parse_activity_scorer(data: Dict) -> ActivityScorerConfig:
        """Parse activity_scorer section."""
        weights = data.get("weights", {})
        thresholds = data.get("thresholds", {})

        return ActivityScorerConfig(
            weight_oi_change=weights.get("oi_change", 0.25),
            weight_volume_spike=weights.get("volume_spike", 0.20),
            weight_iv_interest=weights.get("iv_interest", 0.15),
            weight_pcr_extreme=weights.get("pcr_extreme", 0.15),
            weight_whale_activity=weights.get("whale_activity", 0.15),
            weight_total_volume=weights.get("total_volume", 0.10),
            oi_change_max=thresholds.get("oi_change_max", 20.0),
            volume_spike_max=thresholds.get("volume_spike_max", 5.0),
            total_volume_max=thresholds.get("total_volume_max", 10_000_000),
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

    search_paths.extend(
        [
            "./config.yaml",
            "./config/config.yaml",
            "~/binance-signal-generator/config.yaml",
        ]
    )

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
