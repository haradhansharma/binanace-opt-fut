"""
Custom exceptions for the Binance Signal Generator.

This module defines a hierarchy of exceptions for handling errors
throughout the signal generation pipeline.
"""

from typing import Optional, Dict, Any


class SignalGeneratorError(Exception):
    """
    Base exception for all signal generator errors.
    
    All custom exceptions in this package inherit from this class,
    allowing for easy catching of all package-specific errors.
    """
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


# =============================================================================
# Configuration Errors
# =============================================================================

class ConfigurationError(SignalGeneratorError):
    """Raised when there is an error in configuration."""
    pass


class MissingConfigError(ConfigurationError):
    """Raised when required configuration is missing."""
    pass


class InvalidConfigError(ConfigurationError):
    """Raised when configuration values are invalid."""
    pass


class MissingAPIKeyError(ConfigurationError):
    """Raised when API credentials are not provided."""
    pass


# =============================================================================
# Data Fetching Errors
# =============================================================================

class DataFetchError(SignalGeneratorError):
    """Base exception for data fetching errors."""
    pass


class OptionsAPIError(DataFetchError):
    """Raised when Options API request fails."""
    pass


class FuturesAPIError(DataFetchError):
    """Raised when Futures API request fails."""
    pass


class RateLimitError(DataFetchError):
    """
    Raised when API rate limit is exceeded.
    
    Attributes:
        retry_after: Seconds to wait before retrying
    """
    
    def __init__(
        self, 
        message: str, 
        retry_after: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details)
        self.retry_after = retry_after
    
    def __str__(self) -> str:
        base = super().__str__()
        if self.retry_after:
            return f"{base} - Retry after: {self.retry_after}s"
        return base


class APIConnectionError(DataFetchError):
    """Raised when connection to API fails."""
    pass


class APITimeoutError(DataFetchError):
    """Raised when API request times out."""
    pass


# =============================================================================
# Analysis Errors
# =============================================================================

class AnalysisError(SignalGeneratorError):
    """Base exception for analysis errors."""
    pass


class IVAnalysisError(AnalysisError):
    """Raised when IV analysis fails."""
    pass


class PCRAnalysisError(AnalysisError):
    """Raised when PCR analysis fails."""
    pass


class OIAnalysisError(AnalysisError):
    """Raised when OI analysis fails."""
    pass


class MaxPainError(AnalysisError):
    """Raised when Max Pain calculation fails."""
    pass


class WallDetectionError(AnalysisError):
    """Raised when wall detection fails."""
    pass


class WhaleDetectionError(AnalysisError):
    """Raised when whale detection fails."""
    pass


# =============================================================================
# Validation Errors
# =============================================================================

class ValidationError(SignalGeneratorError):
    """Base exception for validation errors."""
    pass


class FuturesValidationError(ValidationError):
    """Raised when futures validation fails."""
    
    def __init__(
        self, 
        message: str, 
        reasons: Optional[list] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details)
        self.reasons = reasons or []
    
    def __str__(self) -> str:
        base = super().__str__()
        if self.reasons:
            return f"{base} - Reasons: {self.reasons}"
        return base


class InsufficientLiquidityError(FuturesValidationError):
    """Raised when asset has insufficient liquidity."""
    pass


class TrendMismatchError(FuturesValidationError):
    """Raised when trend doesn't align with signal direction."""
    pass


# =============================================================================
# Pipeline Errors
# =============================================================================

class PipelineError(SignalGeneratorError):
    """Base exception for pipeline errors."""
    pass


class PipelineTimeoutError(PipelineError):
    """Raised when pipeline execution exceeds timeout."""
    
    def __init__(
        self, 
        message: str, 
        stage: Optional[str] = None,
        elapsed_seconds: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details)
        self.stage = stage
        self.elapsed_seconds = elapsed_seconds
    
    def __str__(self) -> str:
        base = super().__str__()
        parts = []
        if self.stage:
            parts.append(f"stage={self.stage}")
        if self.elapsed_seconds:
            parts.append(f"elapsed={self.elapsed_seconds}s")
        if parts:
            return f"{base} - {', '.join(parts)}"
        return base


class PipelineStageError(PipelineError):
    """Raised when a pipeline stage fails."""
    
    def __init__(
        self, 
        message: str, 
        stage: str,
        original_error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details)
        self.stage = stage
        self.original_error = original_error
    
    def __str__(self) -> str:
        base = super().__str__()
        if self.original_error:
            return f"{base} - Stage: {self.stage}, Error: {self.original_error}"
        return f"{base} - Stage: {self.stage}"


class NoAssetsSelectedError(PipelineError):
    """Raised when no assets meet the activity threshold."""
    pass


class NoSignalsGeneratedError(PipelineError):
    """Raised when no signals pass validation."""
    pass


# =============================================================================
# Output Errors
# =============================================================================

class OutputError(SignalGeneratorError):
    """Base exception for output errors."""
    pass


class DatabaseError(OutputError):
    """Raised when database operation fails."""
    pass


class JSONOutputError(OutputError):
    """Raised when JSON output fails."""
    pass
