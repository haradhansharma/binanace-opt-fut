"""
Futures data fetcher using Binance USDS-M Futures SDK.

This module fetches Futures market data from Binance using the official
binance-sdk-derivatives-trading-usds-futures SDK. It handles:
- Price and ticker data
- Open interest
- Funding rates
- Klines for trend analysis

SDK Reference:
- https://github.com/binance/binance-connector-python/tree/master/clients/derivatives_trading_usds_futures
- https://binance-docs.github.io/apidocs/futures/en/

USDS-M Futures (USDT-Margined):
- Margin in USDT
- Uses /fapi/* endpoints
- Symbols like BTCUSDT, ETHUSDT (perpetual)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
import asyncio

from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import (
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL,
)
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
)

from binance_signal_generator.models import (
    FuturesData,
    Kline,
    LSRatioData,
    FundingRateData,
)
from binance_signal_generator.utils.rate_limiter import RateLimiter
from binance_signal_generator.utils.logging import get_logger
from binance_signal_generator.utils.exceptions import DataFetchError

logger = get_logger(__name__)


class FuturesFetcher:
    """
    Fetches USDS-M Futures data using official Binance Futures SDK.

    The Futures API provides data about:
    - Current prices and 24hr tickers
    - Open interest
    - Funding rates
    - Klines/candlesticks
    - Mark and index prices

    Attributes:
        client: Binance USDS-M Futures SDK client
        rate_limiter: Rate limiter for API calls
    """

    # Binance USDS-M Futures API base URLs
    MAINNET_URL = DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL  # https://fapi.binance.com
    TESTNET_URL = (
        DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL  # https://testnet.binancefuture.com
    )

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """
        Initialize Futures fetcher.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet environment
            rate_limiter: Optional custom rate limiter
        """
        base_url = self.TESTNET_URL if testnet else self.MAINNET_URL

        configuration = ConfigurationRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            base_path=base_url,
        )

        self.client = DerivativesTradingUsdsFutures(config_rest_api=configuration)

        # Use provided rate limiter or create default
        # Higher rate limit for Futures API
        self.rate_limiter = rate_limiter or RateLimiter(
            requests_per_second=20.0,
            burst=40,
        )

        logger.info(
            "Futures fetcher initialized",
            extra={"data": {"testnet": testnet, "base_url": base_url}},
        )

    def _response_to_dict(self, data: Any) -> Dict[str, Any]:
        """Convert SDK response object to dictionary."""
        if hasattr(data, "__dict__"):
            return {k: v for k, v in data.__dict__.items() if not k.startswith("_")}
        return data if isinstance(data, dict) else {}

    def _convert_symbol_to_futures(self, symbol: str) -> str:
        """
        Convert Options symbol format to USDS-M Futures format.

        Options uses: BTCUSDT, ETHUSDT, etc.
        USDS-M Futures uses: BTCUSDT (same for perpetual)

        Args:
            symbol: Options-style symbol (e.g., "BTCUSDT")

        Returns:
            USDS-M Futures symbol (e.g., "BTCUSDT" for perpetual)
        """
        # For USDS-M, the symbol format is the same for perpetual
        # Just return as-is since we're trading the perpetual
        return symbol

    async def get_price(self, symbol: str) -> FuturesData:
        """
        Get current price and 24hr ticker data.

        API: GET /fapi/v1/ticker/24hr

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")

        Returns:
            FuturesData with price information
        """
        await self.rate_limiter.acquire()

        try:
            response = self.client.rest_api.ticker24hr_price_change_statistics(symbol=symbol)
            data = response.data()

            # CRITICAL FIX: Handle SDK actual_instance wrapper
            # The SDK wraps the actual data in an 'actual_instance' attribute
            # Debug showed: actual_instance: symbol='BTCUSDT' last_price='78235.90'
            if hasattr(data, "actual_instance"):
                data = data.actual_instance
                logger.debug(f"Unwrapped actual_instance for {symbol}")

            # Debug: Log raw response type and structure
            logger.debug(f"Futures API response type for {symbol}: {type(data)}")

            # Handle list response (API returns list with single item)
            if isinstance(data, list) and len(data) > 0:
                data = data[0]

            # Direct attribute access (SDK returns snake_case attributes)
            # After unwrapping actual_instance, fields are directly accessible
            price = float(getattr(data, "last_price", 0) or 0)
            volume = float(getattr(data, "volume", 0) or 0)
            high = float(getattr(data, "high_price", 0) or 0)
            low = float(getattr(data, "low_price", 0) or 0)
            price_change_pct = float(getattr(data, "price_change_percent", 0) or 0)

            # Debug log the actual values
            logger.info(
                f"Futures ticker for {symbol}: price={price}, volume={volume}, "
                f"high={high}, low={low}, change={price_change_pct}%"
            )

            return FuturesData(
                symbol=symbol,
                price=price,
                timestamp=datetime.utcnow(),
                volume_24h=volume,
                open_interest=0.0,  # Fetched separately
                funding_rate=0.0,  # Fetched separately
                mark_price=price,
                index_price=price,
                high_24h=high,
                low_24h=low,
                price_change_pct=price_change_pct,
            )

        except Exception as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
            raise DataFetchError(f"Price fetch failed for {symbol}: {e}")

    async def get_all_data(self, symbol: str) -> FuturesData:
        """
        Get complete futures data for a symbol.

        Combines price, open interest, funding rate, and mark price
        in parallel for efficiency.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")

        Returns:
            FuturesData with all information
        """
        # For USDS-M, symbol format is the same
        futures_symbol = self._convert_symbol_to_futures(symbol)
        logger.debug(f"Fetching all data for {symbol} (using {futures_symbol})")

        # Run all fetches in parallel
        price_task = self.get_price(futures_symbol)
        oi_task = self.get_open_interest(futures_symbol)
        funding_task = self.get_funding_rate(futures_symbol)
        mark_task = self.get_mark_price(futures_symbol)

        price_data, oi_data, funding_data, mark_data = await asyncio.gather(
            price_task,
            oi_task,
            funding_task,
            mark_task,
            return_exceptions=True,
        )

        # Handle potential exceptions
        if isinstance(price_data, Exception):
            logger.error(f"Price fetch failed: {price_data}")
            raise price_data

        # Use price_data as base
        result = price_data
        result.symbol = symbol  # Use original symbol

        if not isinstance(oi_data, Exception):
            result.open_interest = oi_data.get("open_interest", 0)

        if not isinstance(funding_data, Exception):
            result.funding_rate = funding_data.get("funding_rate", 0)

        if not isinstance(mark_data, Exception):
            result.mark_price = mark_data.get("mark_price", 0)
            result.index_price = mark_data.get("index_price", 0)

        # BUG FIX (Bug #2): Fetch OI change percentage to populate the new field.
        # Previously, FuturesData.open_interest_change_pct didn't exist, causing
        # orchestrator.py's hasattr() to always return False → OI flow signal (12% weight) was dead.
        try:
            oi_stats = await self.get_oi_statistics(symbol, period="1d", limit=2)
            if len(oi_stats) >= 2:
                latest_oi = float(oi_stats[-1].get("sum_open_interest", 0))
                prev_oi = float(oi_stats[0].get("sum_open_interest", 0))
                if prev_oi > 0:
                    result.open_interest_change_pct = (latest_oi - prev_oi) / prev_oi * 100
        except Exception as e:
            logger.debug(f"Failed to fetch OI change for {symbol}: {e}")
            # open_interest_change_pct stays at default 0.0

        return result

    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        """
        Get open interest for futures.

        API: GET /fapi/v1/openInterest

        Args:
            symbol: Trading pair

        Returns:
            Dictionary with open interest data
        """
        await self.rate_limiter.acquire()

        try:
            response = self.client.rest_api.open_interest(symbol=symbol)
            data = response.data()

            if hasattr(data, "__dict__"):
                return {
                    "symbol": symbol,
                    "open_interest": float(
                        getattr(data, "open_interest", 0) or getattr(data, "openInterest", 0) or 0
                    ),
                    "time": datetime.utcnow(),
                }

            return {
                "symbol": symbol,
                "open_interest": float(data.get("openInterest", 0) or 0),
                "time": datetime.utcnow(),
            }

        except Exception as e:
            logger.error(f"Failed to fetch open interest for {symbol}: {e}")
            raise DataFetchError(f"Open interest fetch failed: {e}")

    async def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """
        Get current funding rate.

        API: GET /fapi/v1/fundingRate

        Args:
            symbol: Trading pair

        Returns:
            Dictionary with funding rate data
        """
        await self.rate_limiter.acquire()

        try:
            response = self.client.rest_api.get_funding_rate_history(symbol=symbol, limit=1)
            data = response.data()

            # Handle response
            if hasattr(data, "__iter__") and not isinstance(data, dict):
                items = list(data)
                if items:
                    item = items[0]
                    if hasattr(item, "__dict__"):
                        return {
                            "symbol": symbol,
                            "funding_rate": float(
                                getattr(item, "funding_rate", 0)
                                or getattr(item, "fundingRate", 0)
                                or 0
                            ),
                            "time": datetime.utcnow(),
                        }
                    return {
                        "symbol": symbol,
                        "funding_rate": float(item.get("fundingRate", 0) or 0),
                        "time": datetime.fromtimestamp(item.get("fundingTime", 0) / 1000),
                    }

            if isinstance(data, list) and len(data) > 0:
                return {
                    "symbol": symbol,
                    "funding_rate": float(data[0].get("fundingRate", 0) or 0),
                    "time": datetime.fromtimestamp(data[0].get("fundingTime", 0) / 1000),
                }

            return {
                "symbol": symbol,
                "funding_rate": 0.0,
                "time": datetime.utcnow(),
            }

        except Exception as e:
            logger.error(f"Failed to fetch funding rate for {symbol}: {e}")
            return {"symbol": symbol, "funding_rate": 0.0, "time": datetime.utcnow()}

    async def get_mark_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get mark price and index price.

        API: GET /fapi/v1/premiumIndex

        Args:
            symbol: Trading pair

        Returns:
            Dictionary with mark/index price data
        """
        await self.rate_limiter.acquire()

        try:
            response = self.client.rest_api.mark_price(symbol=symbol)
            data = response.data()

            # CRITICAL FIX: Handle SDK actual_instance wrapper
            if hasattr(data, "actual_instance"):
                data = data.actual_instance

            # Handle list response (API returns list with single item)
            if isinstance(data, list) and len(data) > 0:
                data = data[0]

            # Direct attribute access (SDK returns snake_case after unwrapping)
            return {
                "symbol": symbol,
                "mark_price": float(getattr(data, "mark_price", 0) or 0),
                "index_price": float(getattr(data, "index_price", 0) or 0),
                "last_funding_rate": float(getattr(data, "last_funding_rate", 0) or 0),
                "time": datetime.utcnow(),
            }

        except Exception as e:
            logger.error(f"Failed to fetch mark price for {symbol}: {e}")
            return {
                "symbol": symbol,
                "mark_price": 0.0,
                "index_price": 0.0,
                "time": datetime.utcnow(),
            }

    async def get_klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 100,
    ) -> List[Kline]:
        """
        Get klines/candlesticks for trend analysis.

        API: GET /fapi/v1/klines

        Args:
            symbol: Trading pair
            interval: Kline interval (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Number of klines (max 1500)

        Returns:
            List of Kline objects
        """
        await self.rate_limiter.acquire()

        try:
            response = self.client.rest_api.kline_candlestick_data(
                symbol=symbol,
                interval=interval,
                limit=min(limit, 1500),
            )
            data = response.data()

            # Handle response
            if hasattr(data, "__iter__") and not isinstance(data, dict):
                klines_list = list(data)
            else:
                klines_list = data if isinstance(data, list) else []

            klines = []
            for k in klines_list:
                # Klines are typically returned as arrays
                if isinstance(k, (list, tuple)) and len(k) >= 7:
                    klines.append(
                        Kline(
                            open_time=datetime.fromtimestamp(k[0] / 1000),
                            open=float(k[1]),
                            high=float(k[2]),
                            low=float(k[3]),
                            close=float(k[4]),
                            volume=float(k[5]),
                            close_time=datetime.fromtimestamp(k[6] / 1000),
                        )
                    )

            logger.debug(
                f"Fetched {len(klines)} klines for {symbol}", extra={"data": {"interval": interval}}
            )

            return klines

        except Exception as e:
            logger.error(f"Failed to fetch klines for {symbol}: {e}")
            raise DataFetchError(f"Klines fetch failed: {e}")

    async def get_ticker_24hr(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get 24hr ticker data.

        API: GET /fapi/v1/ticker/24hr

        Args:
            symbol: Optional specific symbol, or None for all

        Returns:
            List of ticker dictionaries
        """
        await self.rate_limiter.acquire()

        try:
            if symbol:
                response = self.client.rest_api.ticker24hr_price_change_statistics(symbol=symbol)
            else:
                response = self.client.rest_api.ticker24hr_price_change_statistics()

            data = response.data()

            # Handle single vs multiple response
            if hasattr(data, "__iter__") and not isinstance(data, dict):
                ticker_list = list(data)
            else:
                ticker_list = [data] if data else []

            tickers = []
            for t in ticker_list:
                if hasattr(t, "__dict__"):
                    tickers.append(
                        {
                            "symbol": getattr(t, "symbol", ""),
                            "price": float(
                                getattr(t, "last_price", 0) or getattr(t, "lastPrice", 0) or 0
                            ),
                            "price_change": float(
                                getattr(t, "price_change", 0) or getattr(t, "priceChange", 0) or 0
                            ),
                            "price_change_pct": float(
                                getattr(t, "price_change_percent", 0)
                                or getattr(t, "priceChangePercent", 0)
                                or 0
                            ),
                            "high": float(
                                getattr(t, "high_price", 0) or getattr(t, "highPrice", 0) or 0
                            ),
                            "low": float(
                                getattr(t, "low_price", 0) or getattr(t, "lowPrice", 0) or 0
                            ),
                            "volume": float(getattr(t, "volume", 0) or 0),
                            "quote_volume": float(
                                getattr(t, "quote_volume", 0)
                                or getattr(t, "quoteAssetVolume", 0)
                                or 0
                            ),
                            "trades": int(getattr(t, "count", 0) or getattr(t, "count", 0) or 0),
                        }
                    )
                elif isinstance(t, dict):
                    tickers.append(
                        {
                            "symbol": t.get("symbol", ""),
                            "price": float(t.get("lastPrice", 0) or 0),
                            "price_change": float(t.get("priceChange", 0) or 0),
                            "price_change_pct": float(t.get("priceChangePercent", 0) or 0),
                            "high": float(t.get("highPrice", 0) or 0),
                            "low": float(t.get("lowPrice", 0) or 0),
                            "volume": float(t.get("volume", 0) or 0),
                            "quote_volume": float(t.get("quoteAssetVolume", 0) or 0),
                            "trades": int(t.get("count", 0) or 0),
                        }
                    )

            return tickers

        except Exception as e:
            logger.error(f"Failed to fetch 24hr ticker: {e}")
            raise DataFetchError(f"24hr ticker fetch failed: {e}")

    async def check_liquidity(
        self,
        symbol: str,
        min_volume: float = 1_000_000,
    ) -> bool:
        """
        Check if symbol has sufficient liquidity.

        Args:
            symbol: Trading pair
            min_volume: Minimum 24h volume in USD

        Returns:
            True if liquid enough
        """
        try:
            data = await self.get_price(symbol)
            is_liquid = data.volume_24h >= min_volume

            logger.debug(
                f"Liquidity check for {symbol}",
                extra={
                    "data": {
                        "volume": data.volume_24h,
                        "min_volume": min_volume,
                        "is_liquid": is_liquid,
                    }
                },
            )

            return is_liquid

        except Exception as e:
            logger.error(f"Liquidity check failed for {symbol}: {e}")
            return False

    async def get_orderbook_depth(
        self,
        symbol: str,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Get order book depth.

        API: GET /fapi/v1/depth

        Args:
            symbol: Trading pair
            limit: Depth limit (5, 10, 20, 50, 100, 500, 1000)

        Returns:
            Dictionary with bids and asks
        """
        await self.rate_limiter.acquire()

        try:
            response = self.client.rest_api.order_book(symbol=symbol, limit=limit)
            data = response.data()

            data_dict = self._response_to_dict(data)

            return {
                "symbol": symbol,
                "bids": [
                    {"price": float(b[0]), "quantity": float(b[1])}
                    for b in data_dict.get("bids", [])
                ],
                "asks": [
                    {"price": float(a[0]), "quantity": float(a[1])}
                    for a in data_dict.get("asks", [])
                ],
                "time": datetime.utcnow(),
            }

        except Exception as e:
            logger.error(f"Failed to fetch orderbook for {symbol}: {e}")
            raise DataFetchError(f"Orderbook fetch failed: {e}")

    async def get_exchange_info(self) -> Dict[str, Any]:
        """
        Get exchange information.

        API: GET /fapi/v1/exchangeInfo

        Returns:
            Dictionary with exchange info
        """
        await self.rate_limiter.acquire()

        try:
            response = self.client.rest_api.exchange_information()
            data = response.data()

            data_dict = self._response_to_dict(data)

            symbols_list = data_dict.get("symbols", [])
            if hasattr(data, "symbols"):
                symbols_list = []
                for s in data.symbols:
                    if hasattr(s, "__dict__"):
                        symbols_list.append(
                            {
                                "symbol": getattr(s, "symbol", ""),
                                "status": getattr(s, "status", ""),
                                "base_asset": getattr(s, "base_asset", "")
                                or getattr(s, "baseAsset", ""),
                                "quote_asset": getattr(s, "quote_asset", "")
                                or getattr(s, "quoteAsset", ""),
                            }
                        )

            return {
                "timezone": data_dict.get("timezone", "UTC"),
                "server_time": datetime.utcnow(),
                "symbols": symbols_list,
            }

        except Exception as e:
            logger.error(f"Failed to fetch exchange info: {e}")
            raise DataFetchError(f"Exchange info fetch failed: {e}")

    async def get_available_symbols(self) -> List[str]:
        """
        Get all available trading symbols.

        Returns:
            List of symbol strings
        """
        try:
            info = await self.get_exchange_info()
            symbols = [s["symbol"] for s in info.get("symbols", []) if s.get("status") == "TRADING"]

            logger.info(f"Found {len(symbols)} trading symbols")
            return symbols

        except Exception as e:
            logger.error(f"Failed to get available symbols: {e}")
            return []

    async def get_oi_statistics(
        self,
        symbol: str,
        period: str = "1d",
        limit: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Get Open Interest historical statistics.

        API: GET /futures/data/openInterestHist
        Weight: 0 (free!)

        Used for calculating oi_change_pct in activity scoring.
        Returns historical OI data to compare current vs past OI.

        Response format:
        [
            {
                "symbol": "BTCUSDT",
                "sumOpenInterest": "20403.63700000",
                "sumOpenInterestValue": "150570784.07809979",
                "timestamp": "1583127900000"
            }
        ]

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            period: Time period ("5m","15m","30m","1h","2h","4h","6h","12h","1d")
            limit: Number of data points (default 7 for 7-day change)

        Returns:
            List of OI statistics dictionaries with timestamp and sumOpenInterest
        """
        await self.rate_limiter.acquire()

        try:
            # Import the enum for period
            from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
                OpenInterestStatisticsPeriodEnum,
            )

            # Map period string to enum
            period_map = {
                "5m": "PERIOD_5m",
                "15m": "PERIOD_15m",
                "30m": "PERIOD_30m",
                "1h": "PERIOD_1h",
                "2h": "PERIOD_2h",
                "4h": "PERIOD_4h",
                "6h": "PERIOD_6h",
                "12h": "PERIOD_12h",
                "1d": "PERIOD_1d",
            }

            period_enum = OpenInterestStatisticsPeriodEnum[
                period_map.get(period, "PERIOD_1d")
            ].value

            response = self.client.rest_api.open_interest_statistics(
                symbol=symbol,
                period=period_enum,
                limit=min(limit, 500),
            )

            data = response.data()

            # Handle response
            if data is None:
                logger.warning(f"OI statistics response is None for {symbol}")
                return []

            # Convert to list
            if isinstance(data, list):
                items = data
            elif hasattr(data, "__iter__") and not isinstance(data, dict):
                items = list(data)
            else:
                items = [data] if data else []

            # Extract relevant fields
            result = []
            for item in items:
                if hasattr(item, "__dict__"):
                    result.append(
                        {
                            "symbol": getattr(item, "symbol", symbol),
                            "sum_open_interest": float(
                                getattr(item, "sum_open_interest", 0)
                                or getattr(item, "sumOpenInterest", 0)
                                or 0
                            ),
                            "sum_open_interest_value": float(
                                getattr(item, "sum_open_interest_value", 0)
                                or getattr(item, "sumOpenInterestValue", 0)
                                or 0
                            ),
                            "timestamp": getattr(item, "timestamp", 0),
                        }
                    )
                elif isinstance(item, dict):
                    result.append(
                        {
                            "symbol": item.get("symbol", symbol),
                            "sum_open_interest": float(
                                item.get("sumOpenInterest", 0)
                                or item.get("sum_open_interest", 0)
                                or 0
                            ),
                            "sum_open_interest_value": float(
                                item.get("sumOpenInterestValue", 0)
                                or item.get("sum_open_interest_value", 0)
                                or 0
                            ),
                            "timestamp": item.get("timestamp", 0),
                        }
                    )

            logger.debug(f"Fetched {len(result)} OI statistics for {symbol}")
            return result

        except Exception as e:
            logger.error(f"Failed to fetch OI statistics for {symbol}: {e}")
            return []

    async def get_volume_history(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get historical volume data from klines.

        API: GET /fapi/v1/klines
        Weight: 1-5 depending on limit

        Used for calculating volume_spike_score in activity scoring.
        Returns historical volume data to detect volume spikes.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            interval: Kline interval ("1m","5m","15m","1h","4h","1d")
            limit: Number of klines (default 30 for 30-day average)

        Returns:
            List of volume dictionaries with timestamp and volume
        """
        await self.rate_limiter.acquire()

        try:
            # Import the enum for interval
            from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
                KlineCandlestickDataIntervalEnum,
            )

            # Map interval string to enum
            interval_map = {
                "1s": "INTERVAL_1s",
                "1m": "INTERVAL_1m",
                "3m": "INTERVAL_3m",
                "5m": "INTERVAL_5m",
                "15m": "INTERVAL_15m",
                "30m": "INTERVAL_30m",
                "1h": "INTERVAL_1h",
                "2h": "INTERVAL_2h",
                "4h": "INTERVAL_4h",
                "6h": "INTERVAL_6h",
                "8h": "INTERVAL_8h",
                "12h": "INTERVAL_12h",
                "1d": "INTERVAL_1d",
                "3d": "INTERVAL_3d",
                "1w": "INTERVAL_1w",
                "1M": "INTERVAL_1M",
            }

            interval_enum = KlineCandlestickDataIntervalEnum[
                interval_map.get(interval, "INTERVAL_1d")
            ].value

            response = self.client.rest_api.kline_candlestick_data(
                symbol=symbol,
                interval=interval_enum,
                limit=min(limit, 1500),
            )

            data = response.data()

            # Handle response - klines are returned as arrays
            if data is None:
                logger.warning(f"Klines response is None for {symbol}")
                return []

            if hasattr(data, "__iter__") and not isinstance(data, dict):
                klines_list = list(data)
            else:
                klines_list = data if isinstance(data, list) else []

            # Parse kline data
            # Format: [open_time, open, high, low, close, volume, close_time, ...]
            result = []
            for k in klines_list:
                if isinstance(k, (list, tuple)) and len(k) >= 6:
                    result.append(
                        {
                            "open_time": k[0],
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                            "close_time": k[6] if len(k) > 6 else 0,
                        }
                    )

            logger.debug(f"Fetched {len(result)} klines for {symbol}")
            return result

        except Exception as e:
            logger.error(f"Failed to fetch klines for {symbol}: {e}")
            return []

    # =========================================================================
    # Sentiment Data Methods (L/S Ratios, Funding Rate History)
    # =========================================================================

    async def get_top_trader_position_ratio(
        self,
        symbol: str,
        period: str = "1h",
        limit: int = 30,
    ) -> List[LSRatioData]:
        """
        Get Top Trader Long/Short Ratio (Positions).

        API: GET /futures/data/topLongShortPositionRatio
        Weight: 0 (FREE!)
        IP Rate Limit: 1000 requests/5min

        The proportion of net long and net short positions to total open
        positions of the top 20% users with the highest margin balance.

        Interpretation:
        - Ratio > 1: Longs dominate (bullish sentiment from top traders)
        - Ratio < 1: Shorts dominate (bearish sentiment from top traders)
        - Extreme values (> 2 or < 0.5) may signal contrarian opportunity

        Response format:
        [
            {
                "symbol": "BTCUSDT",
                "longShortRatio": "1.4342",
                "longAccount": "0.5891",
                "shortAccount": "0.4108",
                "timestamp": "1583139600000"
            }
        ]

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            period: Time period ("5m","15m","30m","1h","2h","4h","6h","12h","1d")
            limit: Number of data points (default 30, max 500)

        Returns:
            List of LSRatioData objects
        """
        await self.rate_limiter.acquire()

        try:
            from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
                TopTraderLongShortRatioPositionsPeriodEnum,
            )

            # Map period string to enum
            period_map = {
                "5m": "PERIOD_5m",
                "15m": "PERIOD_15m",
                "30m": "PERIOD_30m",
                "1h": "PERIOD_1h",
                "2h": "PERIOD_2h",
                "4h": "PERIOD_4h",
                "6h": "PERIOD_6h",
                "12h": "PERIOD_12h",
                "1d": "PERIOD_1d",
            }

            period_enum = TopTraderLongShortRatioPositionsPeriodEnum[
                period_map.get(period, "PERIOD_1h")
            ].value

            response = self.client.rest_api.top_trader_long_short_ratio_positions(
                symbol=symbol,
                period=period_enum,
                limit=min(limit, 500),
            )

            data = response.data()

            # Handle response
            if data is None:
                logger.warning(f"Top trader position ratio response is None for {symbol}")
                return []

            # Convert to list
            if isinstance(data, list):
                items = data
            elif hasattr(data, "__iter__") and not isinstance(data, dict):
                items = list(data)
            else:
                items = [data] if data else []

            # Parse into LSRatioData objects
            result = []
            for item in items:
                if hasattr(item, "__dict__"):
                    timestamp_ms = int(getattr(item, "timestamp", 0) or 0)
                    result.append(
                        LSRatioData(
                            timestamp=datetime.fromtimestamp(timestamp_ms / 1000)
                            if timestamp_ms
                            else datetime.utcnow(),
                            long_short_ratio=float(
                                getattr(item, "long_short_ratio", 1.0)
                                or getattr(item, "longShortRatio", 1.0)
                                or 1.0
                            ),
                            long_account=float(
                                getattr(item, "long_account", 0.5)
                                or getattr(item, "longAccount", 0.5)
                                or 0.5
                            ),
                            short_account=float(
                                getattr(item, "short_account", 0.5)
                                or getattr(item, "shortAccount", 0.5)
                                or 0.5
                            ),
                        )
                    )
                elif isinstance(item, dict):
                    timestamp_ms = int(item.get("timestamp", 0) or 0)
                    result.append(
                        LSRatioData(
                            timestamp=datetime.fromtimestamp(timestamp_ms / 1000)
                            if timestamp_ms
                            else datetime.utcnow(),
                            long_short_ratio=float(item.get("longShortRatio", 1.0) or 1.0),
                            long_account=float(item.get("longAccount", 0.5) or 0.5),
                            short_account=float(item.get("shortAccount", 0.5) or 0.5),
                        )
                    )

            logger.debug(
                f"Fetched {len(result)} top trader position ratio points for {symbol}",
                extra={
                    "data": {
                        "period": period,
                        "latest_ratio": result[-1].long_short_ratio if result else None,
                    }
                },
            )
            return result

        except Exception as e:
            logger.error(f"Failed to fetch top trader position ratio for {symbol}: {e}")
            return []

    async def get_top_trader_account_ratio(
        self,
        symbol: str,
        period: str = "1h",
        limit: int = 30,
    ) -> List[LSRatioData]:
        """
        Get Top Trader Long/Short Ratio (Accounts).

        API: GET /futures/data/topLongShortAccountRatio
        Weight: 0 (FREE!)
        IP Rate Limit: 1000 requests/5min

        The proportion of net long and net short accounts to total accounts
        of the top 20% users with the highest margin balance.
        Each account is counted once only.

        Interpretation:
        - Shows how many accounts (not position size) are long vs short
        - Can differ from position ratio - useful for detecting divergences
        - May indicate "crowd" vs "smart money" positioning

        Response format:
        [
            {
                "symbol": "BTCUSDT",
                "longShortRatio": "1.8105",
                "longAccount": "0.6442",
                "shortAccount": "0.3558",
                "timestamp": "1583139600000"
            }
        ]

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            period: Time period ("5m","15m","30m","1h","2h","4h","6h","12h","1d")
            limit: Number of data points (default 30, max 500)

        Returns:
            List of LSRatioData objects
        """
        await self.rate_limiter.acquire()

        try:
            from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
                TopTraderLongShortRatioAccountsPeriodEnum,
            )

            # Map period string to enum
            period_map = {
                "5m": "PERIOD_5m",
                "15m": "PERIOD_15m",
                "30m": "PERIOD_30m",
                "1h": "PERIOD_1h",
                "2h": "PERIOD_2h",
                "4h": "PERIOD_4h",
                "6h": "PERIOD_6h",
                "12m": "PERIOD_12h",
                "1d": "PERIOD_1d",
            }

            period_enum = TopTraderLongShortRatioAccountsPeriodEnum[
                period_map.get(period, "PERIOD_1h")
            ].value

            response = self.client.rest_api.top_trader_long_short_ratio_accounts(
                symbol=symbol,
                period=period_enum,
                limit=min(limit, 500),
            )

            data = response.data()

            # Handle response
            if data is None:
                logger.warning(f"Top trader account ratio response is None for {symbol}")
                return []

            # Convert to list
            if isinstance(data, list):
                items = data
            elif hasattr(data, "__iter__") and not isinstance(data, dict):
                items = list(data)
            else:
                items = [data] if data else []

            # Parse into LSRatioData objects
            result = []
            for item in items:
                if hasattr(item, "__dict__"):
                    timestamp_ms = int(getattr(item, "timestamp", 0) or 0)
                    result.append(
                        LSRatioData(
                            timestamp=datetime.fromtimestamp(timestamp_ms / 1000)
                            if timestamp_ms
                            else datetime.utcnow(),
                            long_short_ratio=float(
                                getattr(item, "long_short_ratio", 1.0)
                                or getattr(item, "longShortRatio", 1.0)
                                or 1.0
                            ),
                            long_account=float(
                                getattr(item, "long_account", 0.5)
                                or getattr(item, "longAccount", 0.5)
                                or 0.5
                            ),
                            short_account=float(
                                getattr(item, "short_account", 0.5)
                                or getattr(item, "shortAccount", 0.5)
                                or 0.5
                            ),
                        )
                    )
                elif isinstance(item, dict):
                    timestamp_ms = int(item.get("timestamp", 0) or 0)
                    result.append(
                        LSRatioData(
                            timestamp=datetime.fromtimestamp(timestamp_ms / 1000)
                            if timestamp_ms
                            else datetime.utcnow(),
                            long_short_ratio=float(item.get("longShortRatio", 1.0) or 1.0),
                            long_account=float(item.get("longAccount", 0.5) or 0.5),
                            short_account=float(item.get("shortAccount", 0.5) or 0.5),
                        )
                    )

            logger.debug(
                f"Fetched {len(result)} top trader account ratio points for {symbol}",
                extra={
                    "data": {
                        "period": period,
                        "latest_ratio": result[-1].long_short_ratio if result else None,
                    }
                },
            )
            return result

        except Exception as e:
            logger.error(f"Failed to fetch top trader account ratio for {symbol}: {e}")
            return []

    async def get_funding_rate_history(
        self,
        symbol: str,
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[FundingRateData]:
        """
        Get Funding Rate History.

        API: GET /fapi/v1/fundingRate
        Weight: 5
        Rate Limit: Shares 500/5min/IP with GET /fapi/v1/fundingInfo

        Funding rates show the cost of holding perpetual positions:
        - Positive funding: Longs pay shorts (overcrowded longs)
        - Negative funding: Shorts pay longs (overcrowded shorts)
        - Extreme funding often precedes reversals

        Response format:
        [
            {
                "symbol": "BTCUSDT",
                "fundingRate": "-0.03750000",
                "fundingTime": 1570608000000,
                "markPrice": "34287.54619963"
            }
        ]

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            limit: Number of records (default 100, max 1000)
            start_time: Start timestamp in ms (optional)
            end_time: End timestamp in ms (optional)

        Returns:
            List of FundingRateData objects
        """
        await self.rate_limiter.acquire()

        try:
            params = {"symbol": symbol, "limit": min(limit, 1000)}
            if start_time:
                params["startTime"] = start_time
            if end_time:
                params["endTime"] = end_time

            response = self.client.rest_api.get_funding_rate_history(**params)
            data = response.data()

            # Handle response
            if data is None:
                logger.warning(f"Funding rate history response is None for {symbol}")
                return []

            # Convert to list
            if isinstance(data, list):
                items = data
            elif hasattr(data, "__iter__") and not isinstance(data, dict):
                items = list(data)
            else:
                items = [data] if data else []

            # Parse into FundingRateData objects
            result = []
            for item in items:
                if hasattr(item, "__dict__"):
                    timestamp_ms = int(
                        getattr(item, "funding_time", 0) or getattr(item, "fundingTime", 0) or 0
                    )
                    result.append(
                        FundingRateData(
                            timestamp=datetime.fromtimestamp(timestamp_ms / 1000)
                            if timestamp_ms
                            else datetime.utcnow(),
                            funding_rate=float(
                                getattr(item, "funding_rate", 0)
                                or getattr(item, "fundingRate", 0)
                                or 0
                            ),
                            mark_price=float(
                                getattr(item, "mark_price", 0) or getattr(item, "markPrice", 0) or 0
                            ),
                        )
                    )
                elif isinstance(item, dict):
                    timestamp_ms = int(item.get("fundingTime", 0) or 0)
                    result.append(
                        FundingRateData(
                            timestamp=datetime.fromtimestamp(timestamp_ms / 1000)
                            if timestamp_ms
                            else datetime.utcnow(),
                            funding_rate=float(item.get("fundingRate", 0) or 0),
                            mark_price=float(item.get("markPrice", 0) or 0),
                        )
                    )

            logger.debug(
                f"Fetched {len(result)} funding rate history points for {symbol}",
                extra={
                    "data": {
                        "latest_rate": result[-1].funding_rate if result else None,
                        "avg_rate": sum(r.funding_rate for r in result) / len(result)
                        if result
                        else 0,
                    }
                },
            )
            return result

        except Exception as e:
            logger.error(f"Failed to fetch funding rate history for {symbol}: {e}")
            return []

    async def get_sentiment_data(
        self,
        symbol: str,
        ls_period: str = "1h",
        ls_limit: int = 30,
        funding_limit: int = 168,  # ~7 days of 8-hour funding periods
    ) -> Dict[str, Any]:
        """
        Get all sentiment-related data in parallel.

        Combines:
        - Top Trader Position Ratio (FREE)
        - Top Trader Account Ratio (FREE)
        - Funding Rate History (weight 5)

        Total weight: 5 (minimal impact on rate limits)

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            ls_period: Period for L/S ratios
            ls_limit: Number of L/S ratio data points
            funding_limit: Number of funding rate data points

        Returns:
            Dictionary with all sentiment data
        """
        logger.debug(f"Fetching sentiment data for {symbol}")

        # Fetch all in parallel
        position_task = self.get_top_trader_position_ratio(symbol, ls_period, ls_limit)
        account_task = self.get_top_trader_account_ratio(symbol, ls_period, ls_limit)
        funding_task = self.get_funding_rate_history(symbol, funding_limit)

        position_data, account_data, funding_data = await asyncio.gather(
            position_task,
            account_task,
            funding_task,
            return_exceptions=True,
        )

        return {
            "symbol": symbol,
            "top_trader_position": position_data
            if not isinstance(position_data, Exception)
            else [],
            "top_trader_account": account_data if not isinstance(account_data, Exception) else [],
            "funding_rate_history": funding_data if not isinstance(funding_data, Exception) else [],
            "timestamp": datetime.utcnow(),
        }

    async def close(self) -> None:
        """Close the client connection."""
        logger.info("Futures fetcher closed")
