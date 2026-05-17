"""
Options data fetcher using Binance Options SDK.

This module fetches Options market data from Binance using the official
binance-sdk-derivatives-trading-options SDK. It handles:
- Options chain retrieval via exchange information
- Open interest data
- Recent trades for whale detection
- Activity summaries for asset ranking

SDK Reference:
- https://github.com/binance/binance-connector-python/tree/master/clients/derivatives_trading_options
- https://binance-docs.github.io/apidocs/options/en/
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
import re

from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import DERIVATIVES_TRADING_OPTIONS_REST_API_PROD_URL
from binance_sdk_derivatives_trading_options.derivatives_trading_options import DerivativesTradingOptions

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    OptionData,
    ActivityMetrics,
    ExerciseRecord,
)
from binance_signal_generator.utils.rate_limiter import RateLimiter
from binance_signal_generator.utils.logging import get_logger
from binance_signal_generator.utils.exceptions import DataFetchError

logger = get_logger(__name__)


class OptionsFetcher:
    """
    Fetches Options data using official Binance Options SDK.
    
    The Options API provides data about:
    - Exchange information (all option symbols)
    - Open interest per underlying/expiration
    - Mark prices with Greeks
    - Recent trades
    - 24hr tickers
    
    Attributes:
        client: Binance Options SDK client
        rate_limiter: Rate limiter for API calls
    """
    
    # Binance Options API base URLs
    MAINNET_URL = DERIVATIVES_TRADING_OPTIONS_REST_API_PROD_URL  # https://eapi.binance.com
    TESTNET_URL = "https://testnet.binanceops.com"
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """
        Initialize Options fetcher.
        
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
        
        self.client = DerivativesTradingOptions(config_rest_api=configuration)
        
        # Use provided rate limiter or create default
        self.rate_limiter = rate_limiter or RateLimiter(
            requests_per_second=10.0,
            burst=20,
        )
        
        # Cache for exchange info
        self._exchange_info: Optional[Dict[str, Any]] = None
        self._exchange_info_timestamp: Optional[datetime] = None
        
        # Cache for 24hr tickers (refreshed once per execution)
        self._tickers_cache: Optional[List[Dict[str, Any]]] = None
        self._tickers_cache_time: Optional[datetime] = None
        
        # Cache for mark prices (contains IV data)
        self._mark_prices_cache: Optional[List[Dict[str, Any]]] = None
        self._mark_prices_cache_time: Optional[datetime] = None
        
        # Cache for block trades (whale activity)
        self._block_trades_cache: Optional[List[Dict[str, Any]]] = None
        self._block_trades_cache_time: Optional[datetime] = None
        
        logger.info(
            "Options fetcher initialized",
            extra={"data": {"testnet": testnet, "base_url": base_url}}
        )
    
    async def _get_exchange_info(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get and cache exchange information.
        
        API: GET /eapi/v1/exchangeInfo
        
        Returns:
            Dictionary with exchange info
        """
        # Check cache (refresh every hour)
        if not force_refresh and self._exchange_info:
            if self._exchange_info_timestamp:
                age = (datetime.utcnow() - self._exchange_info_timestamp).total_seconds()
                if age < 3600:  # 1 hour
                    return self._exchange_info
        
        await self.rate_limiter.acquire()
        
        try:
            response = self.client.rest_api.exchange_information()
            data = response.data()
            
            # Properly convert SDK response object to dict
            result = {}
            
            # Handle the response object
            if hasattr(data, '__dict__'):
                raw_dict = {k: v for k, v in data.__dict__.items()
                           if not k.startswith('_')}
            elif isinstance(data, dict):
                raw_dict = data
            else:
                raw_dict = {}
            
            # Convert optionSymbols list with proper handling
            option_symbols = []
            
            # Try different keys for option symbols
            symbols_raw = raw_dict.get('optionSymbols') or raw_dict.get('option_symbols') or []
            
            # Also check if it's an attribute
            if not symbols_raw and hasattr(data, 'option_symbols'):
                symbols_raw = data.option_symbols
            if not symbols_raw and hasattr(data, 'optionSymbols'):
                symbols_raw = data.optionSymbols
            
            for sym in symbols_raw:
                if isinstance(sym, dict):
                    option_symbols.append(sym)
                elif hasattr(sym, '__dict__'):
                    # Convert object to dict with proper key mapping
                    sym_dict = {}
                    for k, v in sym.__dict__.items():
                        if not k.startswith('_'):
                            # Map snake_case to camelCase for consistency
                            if k == 'strike_price':
                                sym_dict['strikePrice'] = v
                            elif k == 'expiry_date':
                                sym_dict['expiryDate'] = v
                            else:
                                sym_dict[k] = v
                    option_symbols.append(sym_dict)
            
            result['optionSymbols'] = option_symbols
            
            # Copy other fields
            for k, v in raw_dict.items():
                if k not in ('optionSymbols', 'option_symbols'):
                    result[k] = v
            
            self._exchange_info = result
            self._exchange_info_timestamp = datetime.utcnow()
            
            logger.debug(f"Exchange info loaded with {len(option_symbols)} option symbols")
            
            return self._exchange_info
            
        except Exception as e:
            logger.error(f"Failed to fetch exchange info: {e}")
            raise DataFetchError(f"Exchange info fetch failed: {e}")
    
    async def get_available_underlyings(self) -> List[str]:
        """
        Get all available underlying assets (e.g., BTCUSDT, ETHUSDT).
        
        API: GET /eapi/v1/exchangeInfo
        
        Returns:
            List of underlying symbols
        """
        try:
            exchange_info = await self._get_exchange_info()
            
            # Get option symbols list
            symbols_list = exchange_info.get("optionSymbols", [])
            
            underlyings = set()
            for symbol_info in symbols_list:
                # All items should be dicts now after conversion in _get_exchange_info
                if isinstance(symbol_info, dict):
                    underlying = symbol_info.get("underlying", "")
                else:
                    continue
                    
                if underlying:
                    underlyings.add(underlying)
            
            logger.info(
                "Fetched available underlyings",
                extra={"data": {"count": len(underlyings)}}
            )
            
            return sorted(list(underlyings))
            
        except Exception as e:
            logger.error(f"Failed to fetch underlyings: {e}")
            raise DataFetchError(f"Failed to fetch underlyings: {e}")
    
    async def get_option_symbols_for_underlying(self, underlying: str) -> List[Dict[str, Any]]:
        """
        Get all option symbols for a specific underlying.
        
        Args:
            underlying: Underlying symbol (e.g., "BTCUSDT")
            
        Returns:
            List of option symbol info dictionaries
        """
        exchange_info = await self._get_exchange_info()
        symbols_list = exchange_info.get("optionSymbols", [])
        
        options = []
        for symbol_info in symbols_list:
            if isinstance(symbol_info, dict):
                sym_underlying = symbol_info.get("underlying", "")
            else:
                continue
            
            if sym_underlying == underlying:
                options.append(symbol_info)
        
        return options
    
    async def get_open_interest_for_underlying(
        self,
        underlying: str,
        expiration: Optional[str] = None,
    ) -> List[Any]:
        """
        Get open interest for an underlying asset.

        API: GET /eapi/v1/openInterest
        NOTE: Both underlyingAsset and expiration are REQUIRED parameters.

        Response format:
        [
            {
                "symbol": "ETH-221119-1175-P",
                "sumOpenInterest": "4.01",
                "sumOpenInterestUsd": "4880.2985615624",
                "timestamp": "1668754020000"
            }
        ]

        Args:
            underlying: Underlying asset (e.g., "BTC" for BTCUSDT)
            expiration: Expiration date string (e.g., "260626") - REQUIRED

        Returns:
            List of OpenInterestResponse objects
        """
        await self.rate_limiter.acquire()

        try:
            # Convert underlying format (BTCUSDT -> BTC)
            base = underlying.replace("USDT", "").replace("BUSD", "")

            # CRITICAL: expiration is REQUIRED by the Binance API
            # The API will error if expiration is not provided
            if not expiration:
                logger.warning(
                    f"OpenInterest API requires 'expiration' parameter for {underlying}. "
                    f"Use get_all_open_interest_for_underlying() to fetch all expirations."
                )
                return []

            response = self.client.rest_api.open_interest(
                underlying_asset=base,
                expiration=expiration,
            )

            data = response.data()

            # API returns a list of OpenInterestResponse objects
            if isinstance(data, list):
                return data
            elif hasattr(data, '__iter__'):
                return list(data)
            else:
                logger.warning(f"Unexpected OI response type: {type(data)}")
                return []

        except Exception as e:
            logger.error(f"Failed to fetch open interest for {underlying}: {e}")
            return []
    
    async def get_all_open_interest_for_underlying(self, underlying: str) -> Dict[str, float]:
        """
        Get open interest for all expirations of an underlying.
        
        Fetches OI data for each unique expiration date and returns
        a mapping of symbol -> open interest.
        
        Args:
            underlying: Underlying symbol (e.g., "BTCUSDT")
            
        Returns:
            Dictionary mapping option symbol to open interest value
        """
        try:
            # Get option symbols to extract expiration dates
            option_symbols = await self.get_option_symbols_for_underlying(underlying)
            
            # Extract unique expiration dates from symbol names
            # Symbol format: BTC-260626-140000-C (ASSET-EXPIRY-STRIKE-C/P)
            expirations = set()
            for opt in option_symbols:
                symbol = opt.get("symbol", "")
                parts = symbol.split("-")
                if len(parts) >= 2:
                    expirations.add(parts[1])
            
            logger.debug(f"Found {len(expirations)} unique expirations for {underlying}")
            
            # Fetch OI for each expiration
            oi_map: Dict[str, float] = {}

            for expiry in sorted(expirations):
                oi_list = await self.get_open_interest_for_underlying(underlying, expiry)

                # Process each item in the list
                # API returns: {"symbol": "ETH-221119-1175-P", "sumOpenInterest": "4.01", ...}
                for item in oi_list:
                    # Handle SDK object with actual_instance wrapper
                    if hasattr(item, 'actual_instance'):
                        item = item.actual_instance

                    if hasattr(item, 'symbol'):
                        # SDK returns OpenInterestResponse objects
                        symbol = getattr(item, 'symbol', '')
                        # Try both snake_case and camelCase field names
                        oi_str = (
                            getattr(item, 'sum_open_interest', None) or
                            getattr(item, 'sumOpenInterest', None) or
                            "0"
                        )
                        try:
                            oi = float(oi_str) if oi_str else 0.0
                        except (ValueError, TypeError):
                            oi = 0.0
                        if symbol:
                            oi_map[symbol] = oi
                    elif isinstance(item, dict):
                        # Handle dict format (fallback)
                        symbol = item.get("symbol", "")
                        oi_str = item.get("sumOpenInterest") or item.get("sum_open_interest") or item.get("openInterest", "0")
                        try:
                            oi = float(oi_str) if oi_str else 0.0
                        except (ValueError, TypeError):
                            oi = 0.0
                        if symbol:
                            oi_map[symbol] = oi

            logger.info(f"Fetched OI data for {len(oi_map)} symbols for {underlying}")
            return oi_map
            
        except Exception as e:
            logger.error(f"Failed to fetch all OI for {underlying}: {e}")
            return {}
    
    async def get_mark_prices(self, symbol: Optional[str] = None, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get mark prices and Greeks for option symbols.
        
        API: GET /eapi/v1/mark
        Note: symbol is optional - can fetch ALL mark prices at once.
        
        Args:
            symbol: Optional specific symbol (if None, fetches all)
            use_cache: Use cached data if available (default True)
            
        Returns:
            List of dictionaries with mark price, IV, and greeks
        """
        # Return cached data if available and not expired (30 second cache)
        if use_cache and not symbol and self._mark_prices_cache:
            if self._mark_prices_cache_time:
                age = (datetime.utcnow() - self._mark_prices_cache_time).total_seconds()
                if age < 30:
                    return self._mark_prices_cache
        
        await self.rate_limiter.acquire()
        
        try:
            if symbol:
                response = self.client.rest_api.option_mark_price(symbol=symbol)
            else:
                # Fetch all mark prices (symbol is optional)
                response = self.client.rest_api.option_mark_price()
            
            data = response.data()
            
            marks = []
            
            # Handle different response formats
            if data is None:
                logger.warning("Mark price response is None")
                return []
            
            # If it's already a list
            if isinstance(data, list):
                items = data
            # If it's an iterable object (SDK response)
            elif hasattr(data, '__iter__') and not isinstance(data, dict):
                items = list(data)
            # Single item (when symbol is specified)
            elif isinstance(data, dict) or hasattr(data, '__dict__'):
                items = [data]
            else:
                logger.warning(f"Unexpected mark price data type: {type(data)}")
                return []
            
            for m in items:
                if isinstance(m, dict):
                    marks.append(m)
                elif hasattr(m, '__dict__'):
                    # Convert SDK object to dict
                    m_dict = {}
                    for k, v in m.__dict__.items():
                        if not k.startswith('_'):
                            m_dict[k] = v
                    marks.append(m_dict)
            
            # Cache the result if we fetched all marks
            if not symbol:
                self._mark_prices_cache = marks
                self._mark_prices_cache_time = datetime.utcnow()
            
            logger.debug(f"Fetched {len(marks)} mark prices")
            return marks
            
        except Exception as e:
            logger.error(f"Failed to fetch mark prices: {e}")
            return []
    
    async def get_block_trades(self, symbol: Optional[str] = None, limit: int = 500, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get recent block trades (large trades for whale detection).
        
        API: GET /eapi/v1/blockTrades
        Note: symbol is optional - can fetch ALL block trades at once.
        
        Args:
            symbol: Optional specific symbol (if None, fetches all)
            limit: Number of records (max 500)
            use_cache: Use cached data if available (default True)
            
        Returns:
            List of block trade dictionaries
        """
        # Return cached data if available and not expired (30 second cache)
        if use_cache and not symbol and self._block_trades_cache:
            if self._block_trades_cache_time:
                age = (datetime.utcnow() - self._block_trades_cache_time).total_seconds()
                if age < 30:
                    return self._block_trades_cache
        
        await self.rate_limiter.acquire()
        
        try:
            if symbol:
                response = self.client.rest_api.recent_block_trades_list(
                    symbol=symbol,
                    limit=min(limit, 500),
                )
            else:
                # Fetch all block trades (symbol is optional)
                response = self.client.rest_api.recent_block_trades_list(
                    limit=min(limit, 500),
                )
            
            data = response.data()
            
            trades = []
            
            # Handle different response formats
            if data is None:
                logger.warning("Block trades response is None")
                return []
            
            # If it's already a list
            if isinstance(data, list):
                items = data
            # If it's an iterable object (SDK response)
            elif hasattr(data, '__iter__') and not isinstance(data, dict):
                items = list(data)
            else:
                items = []
            
            for t in items:
                if isinstance(t, dict):
                    trades.append(t)
                elif hasattr(t, '__dict__'):
                    # Convert SDK object to dict
                    t_dict = {}
                    for k, v in t.__dict__.items():
                        if not k.startswith('_'):
                            t_dict[k] = v
                    trades.append(t_dict)
            
            # Cache the result if we fetched all trades
            if not symbol:
                self._block_trades_cache = trades
                self._block_trades_cache_time = datetime.utcnow()
            
            logger.debug(f"Fetched {len(trades)} block trades")
            return trades
            
        except Exception as e:
            logger.error(f"Failed to fetch block trades: {e}")
            return []
    
    async def get_index_price(self, underlying: str) -> float:
        """
        Get the index/spot price for an underlying asset.
        
        API: GET /eapi/v1/index
        
        Args:
            underlying: Underlying symbol (e.g., "BTCUSDT")
            
        Returns:
            Index price as float
        """
        await self.rate_limiter.acquire()
        
        try:
            response = self.client.rest_api.index_price(underlying=underlying)
            data = response.data()
            
            if hasattr(data, 'index_price'):
                return float(data.index_price)
            elif isinstance(data, dict):
                return float(data.get('indexPrice', 0) or 0)
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Failed to fetch index price for {underlying}: {e}")
            return 0.0
    
    async def get_ticker_24hr(self, symbol: Optional[str] = None, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get 24hr ticker data.
        
        API: GET /eapi/v1/ticker/24hr
        
        Args:
            symbol: Optional specific symbol
            use_cache: Use cached tickers if available (default True)
            
        Returns:
            List of ticker dictionaries
        """
        # Return cached tickers if available and not expired (cache for 30 seconds)
        if use_cache and not symbol and self._tickers_cache:
            if self._tickers_cache_time:
                age = (datetime.utcnow() - self._tickers_cache_time).total_seconds()
                if age < 30:  # 30 second cache
                    return self._tickers_cache
        
        await self.rate_limiter.acquire()
        
        try:
            if symbol:
                response = self.client.rest_api.ticker24hr_price_change_statistics(symbol=symbol)
            else:
                response = self.client.rest_api.ticker24hr_price_change_statistics()
            
            data = response.data()
            
            tickers = []
            
            # Handle different response formats
            if data is None:
                logger.warning("Ticker response is None")
                return []
            
            # If it's already a list
            if isinstance(data, list):
                items = data
            # If it's an iterable object (SDK response)
            elif hasattr(data, '__iter__') and not isinstance(data, dict):
                items = list(data)
            # Single item (when symbol is specified)
            elif isinstance(data, dict) or hasattr(data, '__dict__'):
                items = [data]
            else:
                logger.warning(f"Unexpected ticker data type: {type(data)}")
                return []
            
            for t in items:
                if isinstance(t, dict):
                    tickers.append(t)
                elif hasattr(t, '__dict__'):
                    # Convert SDK object to dict
                    t_dict = {}
                    for k, v in t.__dict__.items():
                        if not k.startswith('_'):
                            t_dict[k] = v
                    tickers.append(t_dict)
            
            # Cache the result if we fetched all tickers
            if not symbol:
                self._tickers_cache = tickers
                self._tickers_cache_time = datetime.utcnow()
            
            logger.debug(f"Fetched {len(tickers)} tickers")
            return tickers
            
        except Exception as e:
            logger.error(f"Failed to fetch 24hr ticker: {e}")
            return []
    
    async def get_recent_trades(
        self,
        symbol: str,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Get recent trades for an option symbol.
        
        API: GET /eapi/v1/trades
        
        Args:
            symbol: Option symbol (e.g., "BTC-240115-42000-C")
            limit: Number of trades to fetch (max 1000)
            
        Returns:
            List of trade dictionaries
        """
        await self.rate_limiter.acquire()
        
        try:
            response = self.client.rest_api.recent_trades_list(
                symbol=symbol,
                limit=min(limit, 1000),
            )
            data = response.data()
            
            # Handle list response
            if hasattr(data, '__iter__') and not isinstance(data, dict):
                trades_list = list(data)
            else:
                trades_list = data if isinstance(data, list) else []
            
            trades = []
            for trade in trades_list:
                if hasattr(trade, '__dict__'):
                    trade_dict = {k: v for k, v in trade.__dict__.items() 
                                  if not k.startswith('_')}
                else:
                    trade_dict = trade if isinstance(trade, dict) else {}
                trades.append(trade_dict)
            
            return trades
            
        except Exception as e:
            logger.error(f"Failed to fetch trades for {symbol}: {e}")
            return []
    
    async def get_option_chain(self, underlying: str) -> OptionsChain:
        """
        Get complete options chain for an underlying asset.
        
        This method combines multiple API calls to build the option chain:
        1. Get all option symbols for the underlying
        2. Get 24hr tickers for volume data
        3. Get mark prices for IV and Greeks
        4. Get open interest data for each expiration
        
        Args:
            underlying: Underlying symbol (e.g., "BTCUSDT")
            
        Returns:
            OptionsChain with all strike data
        """
        try:
            # Get all option symbols for this underlying
            option_symbols = await self.get_option_symbols_for_underlying(underlying)
            
            if not option_symbols:
                logger.warning(f"No option symbols found for {underlying}")
                return OptionsChain(
                    underlying=underlying,
                    spot_price=0.0,
                    timestamp=datetime.utcnow(),
                    strikes={},
                )
            
            logger.debug(f"Found {len(option_symbols)} option symbols for {underlying}")
            
            # Get 24hr tickers for all symbols (contains volume but NOT OI)
            tickers = await self.get_ticker_24hr()
            
            # Build ticker lookup by symbol
            ticker_map = {}
            for t in tickers:
                sym = t.get("symbol", "")
                if sym:
                    ticker_map[sym] = t
            
            logger.debug(f"Built ticker map with {len(ticker_map)} symbols")
            
            # Get mark prices for IV and Greeks (bulk fetch)
            mark_prices = await self.get_mark_prices()
            
            # Build mark price lookup by symbol
            mark_map = {}
            for m in mark_prices:
                sym = m.get("symbol", "")
                if sym:
                    mark_map[sym] = m
            
            logger.debug(f"Built mark price map with {len(mark_map)} symbols")
            
            # Get Open Interest data separately (not in 24hr ticker)
            oi_map = await self.get_all_open_interest_for_underlying(underlying)
            logger.debug(f"Built OI map with {len(oi_map)} symbols")
            
            # Log first few option symbols for debugging
            if option_symbols:
                sample_symbols = [opt.get("symbol", "") for opt in option_symbols[:3]]
                logger.debug(f"Sample option symbols: {sample_symbols}")
                # Check if any match
                matched = [s for s in sample_symbols if s in ticker_map]
                logger.debug(f"Matched symbols: {matched}")
                # Show OI data for matched symbols
                oi_matched = [s for s in sample_symbols if s in oi_map]
                logger.debug(f"Matched OI symbols: {oi_matched}")
                if oi_matched:
                    logger.debug(f"Sample OI data: {[(s, oi_map[s]) for s in oi_matched[:3]]}")
            
            # Get index price for spot price
            spot_price = await self.get_index_price(underlying)
            
            # Group by strike
            strikes: Dict[float, StrikeData] = {}
            total_call_oi = 0
            total_put_oi = 0
            total_call_volume = 0.0
            total_put_volume = 0.0
            matched_count = 0
            oi_matched_count = 0
            iv_matched_count = 0
            total_call_iv = 0.0
            total_put_iv = 0.0
            call_iv_count = 0
            put_iv_count = 0
            
            for opt in option_symbols:
                symbol = opt.get("symbol", "")
                strike = float(opt.get("strikePrice", 0) or 0)
                side = opt.get("side", "")  # CALL or PUT
                
                if strike == 0 or not symbol:
                    continue
                
                # Get ticker data
                ticker = ticker_map.get(symbol, {})
                
                if ticker:
                    matched_count += 1
                
                # Get OI data from separate API call
                oi = oi_map.get(symbol, 0.0)
                if oi > 0:
                    oi_matched_count += 1
                
                # Get mark price data for IV and Greeks
                mark = mark_map.get(symbol, {})
                if mark:
                    iv_matched_count += 1
                
                # Parse data - ticker uses snake_case from SDK
                volume = float(ticker.get("volume", 0) or 0)
                amount = float(ticker.get("amount", 0) or 0)  # Total value traded
                last_price = float(ticker.get("last_price", 0) or 0)
                
                # Get IV and Greeks from mark price
                # API returns markIV as decimal (e.g., "1.45" = 145%)
                iv = 0.0
                delta = 0.0
                gamma = 0.0
                
                if mark:
                    # Convert IV from decimal to percentage (1.45 -> 145%)
                    iv_str = mark.get("mark_iv") or mark.get("markIV") or "0"
                    try:
                        iv = float(iv_str) if iv_str else 0.0
                    except (ValueError, TypeError):
                        iv = 0.0
                    
                    delta_str = mark.get("delta", "0")
                    gamma_str = mark.get("gamma", "0")
                    
                    try:
                        delta = float(delta_str) if delta_str else 0.0
                        gamma = float(gamma_str) if gamma_str else 0.0
                    except (ValueError, TypeError):
                        pass
                
                # Track IV averages
                if iv > 0:
                    if side == "CALL":
                        total_call_iv += iv
                        call_iv_count += 1
                    elif side == "PUT":
                        total_put_iv += iv
                        put_iv_count += 1
                
                option_data = OptionData(
                    open_interest=int(oi),
                    volume=int(volume),
                    iv=iv,
                    delta=delta,
                    gamma=gamma,
                    last_price=last_price,
                )
                
                # Create strike entry if not exists
                if strike not in strikes:
                    strikes[strike] = StrikeData(
                        strike=strike,
                        call=OptionData(),
                        put=OptionData(),
                    )
                
                # Use 'amount' (total traded value in USDT) as volume proxy
                # For USDT-margined options, 'amount' is already in USDT
                # No conversion needed
                volume_value = amount if amount > 0 else volume * last_price
                
                if side == "CALL":
                    strikes[strike].call = option_data
                    total_call_oi += int(oi)
                    total_call_volume += volume_value
                elif side == "PUT":
                    strikes[strike].put = option_data
                    total_put_oi += int(oi)
                    total_put_volume += volume_value
            
            # Calculate average IV for chain
            avg_call_iv = total_call_iv / call_iv_count if call_iv_count > 0 else 0.0
            avg_put_iv = total_put_iv / put_iv_count if put_iv_count > 0 else 0.0
            
            logger.debug(
                f"Option chain for {underlying}: {len(strikes)} strikes, "
                f"{matched_count}/{len(option_symbols)} tickers matched, "
                f"{oi_matched_count}/{len(option_symbols)} OI matched, "
                f"{iv_matched_count}/{len(option_symbols)} IV matched, "
                f"CallOI: {total_call_oi}, PutOI: {total_put_oi}, "
                f"CallVol: {total_call_volume:.2f}, PutVol: {total_put_volume:.2f}, "
                f"AvgCallIV: {avg_call_iv:.2%}, AvgPutIV: {avg_put_iv:.2%}"
            )
            
            return OptionsChain(
                underlying=underlying,
                spot_price=spot_price,
                timestamp=datetime.utcnow(),
                strikes=strikes,
                total_call_oi=total_call_oi,
                total_put_oi=total_put_oi,
                total_call_volume=total_call_volume,
                total_put_volume=total_put_volume,
                avg_call_iv=avg_call_iv,
                avg_put_iv=avg_put_iv,
            )
            
        except Exception as e:
            logger.error(f"Failed to build options chain for {underlying}: {e}")
            raise DataFetchError(f"Options chain build failed for {underlying}: {e}")
    
    async def get_activity_summary(
        self,
        underlying: str,
        oi_change_pct: float = 0.0,
        volume_spike_score: float = 0.0,
    ) -> ActivityMetrics:
        """
        Get quick activity summary for asset ranking.

        Combines multiple lightweight API calls to provide
        activity metrics for ranking.

        Args:
            underlying: Underlying symbol
            oi_change_pct: OI change percentage from historical API (/futures/data/openInterestHist)
            volume_spike_score: Volume spike score from historical API (/fapi/v1/klines)

        Returns:
            ActivityMetrics for the underlying
        """
        try:
            # Fetch option chain for comprehensive data
            chain = await self.get_option_chain(underlying)

            # Get block trades for whale activity
            block_trades = await self.get_block_trades(limit=500)

            # Calculate whale activity from block trades (pass spot price for USD conversion)
            whale_activity = self._calculate_whale_activity(underlying, block_trades, chain.spot_price)

            # Calculate metrics
            total_oi = chain.total_call_oi + chain.total_put_oi
            total_volume = chain.total_call_volume + chain.total_put_volume
            active_strikes = len([s for s in chain.strikes.values()
                                 if s.call.open_interest > 0 or s.put.open_interest > 0])

            # Calculate PCR extremeness
            pcr = chain.get_pcr()
            pcr_extremeness = self._calc_pcr_extremeness(pcr)

            # Calculate IV percentile from real data
            iv_percentile = self._calc_iv_percentile(chain)

            return ActivityMetrics(
                symbol=underlying,
                timestamp=datetime.utcnow(),
                oi_change_pct=oi_change_pct,  # From /futures/data/openInterestHist
                volume_spike_score=volume_spike_score,  # From /fapi/v1/klines
                iv_percentile=iv_percentile,
                pcr_extremeness=pcr_extremeness,
                whale_activity=whale_activity,
                total_options_volume=total_volume,
                num_strikes_active=active_strikes,
            )

        except Exception as e:
            logger.error(f"Failed to get activity summary for {underlying}: {e}")
            # Return empty metrics on failure
            return ActivityMetrics(
                symbol=underlying,
                timestamp=datetime.utcnow(),
            )
    
    def _calculate_whale_activity(self, underlying: str, block_trades: List[Dict[str, Any]], spot_price: float = 0.0) -> float:
        """
        Calculate whale activity score from block trades.
        
        IMPORTANT: The quoteQty from Binance API is in BASE CURRENCY (BTC, ETH, etc.),
        NOT in USD. We need to multiply by spot price to get USD value.
        
        Example from API:
        {"symbol": "ETH-260522-2200-C", "price": "45.2", "qty": "0.01", "quoteQty": "0.452"}
        - quoteQty = 0.452 ETH (not $0.452!)
        - Real USD value = 0.452 ETH × $2,400 = $1,084.80
        
        Args:
            underlying: Underlying symbol (e.g., "BTCUSDT")
            block_trades: List of block trade dictionaries
            spot_price: Current spot price for USD conversion
            
        Returns:
            Whale activity score (0-1)
        """
        if not block_trades:
            return 0.0
        
        # Extract base asset (BTCUSDT -> BTC)
        base = underlying.replace("USDT", "").replace("BUSD", "")
        
        # Filter trades for this underlying
        underlying_trades = [
            t for t in block_trades
            if t.get("symbol", "").startswith(f"{base}-")
        ]
        
        if not underlying_trades:
            return 0.0
        
        # Calculate total premium traded in USD
        # For USDT-margined options, values should already be in USDT
        # Log sample trade to understand API response format
        if underlying_trades:
            sample_trade = underlying_trades[0]
            logger.debug(f"Sample block trade for {underlying}: {sample_trade}")
        
        total_premium_usd = 0.0
        large_trades = 0
        
        for trade in underlying_trades:
            # For USDT-margined options, quoteQty should be in USDT
            # Try multiple field name variations
            quote_qty = (
                trade.get("quoteQty") or
                trade.get("quote_qty") or
                trade.get("amount") or
                trade.get("premium") or
                trade.get("value") or
                trade.get("total") or
                0
            )
            quote_qty = abs(float(quote_qty) if quote_qty else 0)
            
            # For USDT-margined options, no conversion needed - already in USDT
            premium_usd = quote_qty
            
            total_premium_usd += premium_usd
            
            # Count large trades (>$10K USD)
            if premium_usd >= 10000:
                large_trades += 1
        
        # Score based on:
        # 1. Number of block trades (more = higher score)
        # 2. Total premium in USD (higher = higher score)
        # 3. Number of large trades (more = higher score)
        
        trade_count_score = min(len(underlying_trades) / 50, 1.0)  # 50+ trades = max
        premium_score = min(total_premium_usd / 1000000, 1.0)  # $1M+ premium = max
        large_trade_score = min(large_trades / 10, 1.0)  # 10+ large trades = max
        
        # Weighted average
        whale_score = (trade_count_score * 0.3 + premium_score * 0.4 + large_trade_score * 0.3)
        
        logger.debug(
            f"Whale activity for {underlying}: {whale_score:.3f} "
            f"(trades={len(underlying_trades)}, premium=${total_premium_usd:.0f}, large={large_trades})"
        )
        
        return whale_score
    
    
    def _calc_pcr_extremeness(self, pcr: float) -> float:
        """
        Calculate how extreme PCR is (0 = neutral, 1 = very extreme).
        
        PCR = 1.0 is neutral.
        PCR > 1.5 or < 0.5 is very extreme.
        """
        if pcr <= 0:
            return 0.0
        
        if pcr > 1.0:
            return min((pcr - 1.0) / 0.5, 1.0)
        else:
            return min((1.0 - pcr) / 0.5, 1.0)
    
    def _calc_iv_percentile(self, chain: OptionsChain) -> float:
        """
        Calculate IV percentile from options chain.
        
        Uses the average IV from mark prices (real data from API).
        The IV is returned as decimal (e.g., 1.45 = 145% annualized).
        
        Args:
            chain: Options chain with avg_call_iv and avg_put_iv populated
            
        Returns:
            IV percentile (0-1) based on typical crypto IV ranges
        """
        # Use average IV from chain (populated from mark price API)
        avg_iv = chain.avg_call_iv if chain.avg_call_iv > 0 else chain.avg_put_iv
        
        # If both are available, use weighted average
        if chain.avg_call_iv > 0 and chain.avg_put_iv > 0:
            avg_iv = (chain.avg_call_iv + chain.avg_put_iv) / 2
        
        if avg_iv == 0:
            return 0.5  # Default neutral if no IV data
        
        # IV normalization for crypto options
        # Binance returns IV as decimal (1.45 = 145% annualized)
        if avg_iv < 0.5:
            return 0.2  # Low IV
        elif avg_iv < 0.75:
            return 0.4  # Below average
        elif avg_iv < 1.0:
            return 0.5  # Normal
        elif avg_iv < 1.25:
            return 0.65  # Above average
        elif avg_iv < 1.5:
            return 0.8  # High IV
        else:
            return 0.95  # Very high IV
    
    async def get_historical_exercise_records(
        self,
        underlying: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100,
    ) -> List[ExerciseRecord]:
        """
        Get historical exercise records.
        
        API: GET /eapi/v1/exerciseHistory
        Weight: 3
        
        Shows which options were exercised (ITM at expiry) vs expired OTM.
        Useful for validating max pain theory - options often expire near max pain.
        
        Response format:
        [
            {
                "symbol": "BTC-220121-60000-P",
                "strikePrice": "60000",
                "realStrikePrice": "38844.69652571",
                "expiryDate": 1642752000000,
                "strikeResult": "REALISTIC_VALUE_STRICKEN"
            }
        ]
        
        Strike Results:
        - REALISTIC_VALUE_STRICKEN: Exercised (was ITM at expiry)
        - EXTRINSIC_VALUE_EXPIRED: Expired OTM (worthless)
        
        Args:
            underlying: Underlying index like BTCUSDT (optional)
            start_time: Start timestamp in ms (optional)
            end_time: End timestamp in ms (optional)
            limit: Number of records (default 100, max 100)
            
        Returns:
            List of ExerciseRecord objects
        """
        await self.rate_limiter.acquire()
        
        try:
            params = {"limit": min(limit, 100)}
            if underlying:
                params["underlying"] = underlying
            if start_time:
                params["startTime"] = start_time
            if end_time:
                params["endTime"] = end_time
            
            response = self.client.rest_api.historical_exercise_records(**params)
            data = response.data()
            
            # Handle response
            if data is None:
                logger.warning("Historical exercise records response is None")
                return []
            
            # Convert to list
            if isinstance(data, list):
                items = data
            elif hasattr(data, '__iter__') and not isinstance(data, dict):
                items = list(data)
            else:
                items = [data] if data else []
            
            # Parse into ExerciseRecord objects
            result = []
            for item in items:
                if hasattr(item, '__dict__'):
                    timestamp_ms = int(getattr(item, 'expiry_date', 0) or getattr(item, 'expiryDate', 0) or 0)
                    result.append(ExerciseRecord(
                        symbol=getattr(item, 'symbol', ''),
                        strike_price=float(getattr(item, 'strike_price', 0) or getattr(item, 'strikePrice', 0) or 0),
                        real_strike_price=float(getattr(item, 'real_strike_price', 0) or getattr(item, 'realStrikePrice', 0) or 0),
                        expiry_date=datetime.fromtimestamp(timestamp_ms / 1000) if timestamp_ms else datetime.utcnow(),
                        strike_result=getattr(item, 'strike_result', '') or getattr(item, 'strikeResult', '') or '',
                    ))
                elif isinstance(item, dict):
                    timestamp_ms = int(item.get("expiryDate", 0) or 0)
                    result.append(ExerciseRecord(
                        symbol=item.get("symbol", ""),
                        strike_price=float(item.get("strikePrice", 0) or 0),
                        real_strike_price=float(item.get("realStrikePrice", 0) or 0),
                        expiry_date=datetime.fromtimestamp(timestamp_ms / 1000) if timestamp_ms else datetime.utcnow(),
                        strike_result=item.get("strikeResult", ""),
                    ))
            
            logger.debug(
                f"Fetched {len(result)} exercise records",
                extra={"data": {
                    "underlying": underlying,
                    "exercised": sum(1 for r in result if r.strike_result == "REALISTIC_VALUE_STRICKEN"),
                    "expired_otm": sum(1 for r in result if r.strike_result == "EXTRINSIC_VALUE_EXPIRED"),
                }}
            )
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch historical exercise records: {e}")
            return []

    async def close(self) -> None:
        """Close the client connection."""
        logger.info("Options fetcher closed")
