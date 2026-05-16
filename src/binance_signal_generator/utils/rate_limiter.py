"""
Rate limiter for API calls.

Implements a token bucket algorithm for rate limiting API requests
to respect Binance API limits.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional
from contextlib import asynccontextmanager

from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimiter:
    """
    Token bucket rate limiter for API calls.
    
    Implements a token bucket algorithm where:
    - Tokens are added at a fixed rate (requests_per_second)
    - Each request consumes one token
    - Bucket has a maximum capacity (burst)
    - If no tokens available, request waits
    
    Attributes:
        requests_per_second: Rate at which tokens are replenished
        burst: Maximum number of tokens in bucket
    """
    
    requests_per_second: float = 10.0
    burst: int = 20
    
    _tokens: float = field(default=0.0, init=False, repr=False)
    _last_update: float = field(default=0.0, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    
    def __post_init__(self):
        """Initialize tokens to burst capacity."""
        self._tokens = float(self.burst)
        self._last_update = time.monotonic()
    
    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens, waiting if necessary.
        
        Args:
            tokens: Number of tokens to acquire (default: 1)
            
        Raises:
            ValueError: If tokens > burst capacity
        """
        if tokens > self.burst:
            raise ValueError(f"Cannot acquire {tokens} tokens (max burst: {self.burst})")
        
        async with self._lock:
            await self._wait_for_tokens(tokens)
            self._tokens -= tokens
    
    async def _wait_for_tokens(self, needed: int) -> None:
        """Wait until enough tokens are available."""
        self._replenish()
        
        while self._tokens < needed:
            # Calculate wait time
            deficit = needed - self._tokens
            wait_time = deficit / self.requests_per_second
            
            logger.debug(
                "Rate limit hit, waiting",
                extra={"data": {
                    "wait_seconds": wait_time,
                    "tokens_available": self._tokens,
                    "tokens_needed": needed,
                }}
            )
            
            # Release lock while waiting
            self._lock.release()
            try:
                await asyncio.sleep(wait_time)
            finally:
                await self._lock.acquire()
            
            self._replenish()
    
    def _replenish(self) -> None:
        """Replenish tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        
        # Add tokens based on elapsed time
        self._tokens = min(
            float(self.burst),
            self._tokens + elapsed * self.requests_per_second
        )
        self._last_update = now
    
    @asynccontextmanager
    async def throttle(self, tokens: int = 1):
        """
        Context manager for rate-limited operations.
        
        Usage:
            async with rate_limiter.throttle():
                response = await api_client.get_data()
        """
        await self.acquire(tokens)
        try:
            yield
        finally:
            pass  # Tokens are consumed, no return
    
    def get_stats(self) -> dict:
        """
        Get current rate limiter statistics.
        
        Returns:
            Dictionary with current tokens, capacity, and rate
        """
        self._replenish()
        return {
            "tokens_available": self._tokens,
            "max_burst": self.burst,
            "requests_per_second": self.requests_per_second,
            "utilization": 1 - (self._tokens / self.burst),
        }


@dataclass
class MultiRateLimiter:
    """
    Rate limiter with multiple independent buckets.
    
    Useful when different API endpoints have different rate limits.
    """
    
    default_rate: float = 10.0
    default_burst: int = 20
    
    _limiters: dict = field(default_factory=dict, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    
    def get_limiter(self, name: str, rate: Optional[float] = None, burst: Optional[int] = None) -> RateLimiter:
        """
        Get or create a rate limiter for a named endpoint.
        
        Args:
            name: Name of the endpoint/resource
            rate: Requests per second (uses default if not provided)
            burst: Maximum burst (uses default if not provided)
            
        Returns:
            RateLimiter for the named endpoint
        """
        if name not in self._limiters:
            self._limiters[name] = RateLimiter(
                requests_per_second=rate or self.default_rate,
                burst=burst or self.default_burst,
            )
        return self._limiters[name]
    
    async def acquire(self, name: str = "default", tokens: int = 1) -> None:
        """
        Acquire tokens for a named endpoint.
        
        Args:
            name: Name of the endpoint
            tokens: Number of tokens to acquire
        """
        limiter = self.get_limiter(name)
        await limiter.acquire(tokens)
    
    @asynccontextmanager
    async def throttle(self, name: str = "default", tokens: int = 1):
        """Context manager for rate-limited operations on a named endpoint."""
        await self.acquire(name, tokens)
        try:
            yield
        finally:
            pass
    
    def get_all_stats(self) -> dict:
        """Get statistics for all rate limiters."""
        return {
            name: limiter.get_stats()
            for name, limiter in self._limiters.items()
        }


# Pre-configured rate limiters for Binance API
BINANCE_OPTIONS_RATE_LIMIT = RateLimiter(
    requests_per_second=10.0,  # Conservative for Options API
    burst=20,
)

BINANCE_FUTURES_RATE_LIMIT = RateLimiter(
    requests_per_second=20.0,  # Higher limit for Futures API
    burst=40,
)
