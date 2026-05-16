"""
Unit tests for data fetching modules.

Tests for Options and Futures data fetchers using Binance SDK.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from binance_signal_generator.data.options_fetcher import (
    OptionsFetcher,
    OptionsChain,
    StrikeData,
    OptionData,
)
from binance_signal_generator.data.futures_fetcher import (
    FuturesFetcher,
    FuturesData,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_options_client():
    """Create mock Binance Options client."""
    with patch("binance_signal_generator.data.options_fetcher.Options") as mock:
        yield mock


@pytest.fixture
def mock_futures_client():
    """Create mock Binance Futures client."""
    with patch("binance_signal_generator.data.futures_fetcher.UMFutures") as mock:
        yield mock


@pytest.fixture
def sample_option_chain_response():
    """Sample API response for options chain."""
    return {
        "underlyingPrice": 42000.0,
        "optionChain": [
            {
                "strikePrice": 41000.0,
                "call": {
                    "openInterest": 5000,
                    "volume": 1000,
                    "impliedVolatility": 0.65,
                    "delta": 0.45,
                    "gamma": 0.02,
                    "theta": -0.15,
                    "vega": 0.30,
                    "lastPrice": 1.5,
                    "bidPrice": 1.48,
                    "askPrice": 1.52,
                },
                "put": {
                    "openInterest": 3000,
                    "volume": 800,
                    "impliedVolatility": 0.70,
                    "delta": -0.35,
                    "gamma": 0.02,
                    "theta": -0.12,
                    "vega": 0.28,
                    "lastPrice": 0.8,
                    "bidPrice": 0.78,
                    "askPrice": 0.82,
                },
            },
            {
                "strikePrice": 42000.0,
                "call": {
                    "openInterest": 8000,
                    "volume": 2000,
                    "impliedVolatility": 0.55,
                    "delta": 0.50,
                    "gamma": 0.03,
                    "theta": -0.10,
                    "vega": 0.35,
                    "lastPrice": 2.0,
                    "bidPrice": 1.98,
                    "askPrice": 2.02,
                },
                "put": {
                    "openInterest": 6000,
                    "volume": 1500,
                    "impliedVolatility": 0.60,
                    "delta": -0.40,
                    "gamma": 0.03,
                    "theta": -0.08,
                    "vega": 0.32,
                    "lastPrice": 1.2,
                    "bidPrice": 1.18,
                    "askPrice": 1.22,
                },
            },
        ],
    }


@pytest.fixture
def sample_futures_ticker_response():
    """Sample API response for futures ticker."""
    return {
        "lastPrice": 42150.0,
        "quoteVolume": 1500000000.0,
        "highPrice": 43000.0,
        "lowPrice": 41000.0,
        "priceChangePercent": 2.5,
    }


@pytest.fixture
def sample_trades_response():
    """Sample API response for recent trades."""
    return [
        {
            "id": "12345",
            "price": 1.5,
            "qty": 100,
            "quoteQty": 150000,  # $150k = whale trade
            "time": 1705312800000,
            "side": "BUY",
            "symbol": "BTC-240115-42000-C",
        },
        {
            "id": "12346",
            "price": 0.8,
            "qty": 50,
            "quoteQty": 50000,  # Not a whale trade
            "time": 1705312860000,
            "side": "SELL",
            "symbol": "BTC-240115-41000-P",
        },
    ]


# =============================================================================
# Options Fetcher Tests
# =============================================================================


class TestOptionsFetcher:
    """Tests for OptionsFetcher class."""

    @pytest.fixture
    def fetcher(self, mock_options_client):
        """Create OptionsFetcher instance."""
        return OptionsFetcher(api_key="test_key", api_secret="test_secret", testnet=False)

    def test_init(self, fetcher):
        """Test OptionsFetcher initialization."""
        assert fetcher is not None
        assert fetcher.client is not None

    def test_init_testnet(self, mock_options_client):
        """Test OptionsFetcher initialization with testnet."""
        fetcher = OptionsFetcher(api_key="test_key", api_secret="test_secret", testnet=True)
        assert fetcher is not None

    @pytest.mark.asyncio
    async def test_get_option_chain(self, fetcher, sample_option_chain_response):
        """Test fetching options chain."""
        # Mock the API response
        fetcher.client.option_chain = Mock(return_value=sample_option_chain_response)

        result = await fetcher.get_option_chain("BTCUSDT")

        assert result is not None
        assert isinstance(result, OptionsChain)
        assert result.underlying == "BTCUSDT"
        assert result.spot_price == 42000.0
        assert len(result.strikes) == 2
        assert result.total_call_oi == 13000  # 5000 + 8000
        assert result.total_put_oi == 9000  # 3000 + 6000

    @pytest.mark.asyncio
    async def test_get_option_chain_strike_data(self, fetcher, sample_option_chain_response):
        """Test options chain strike data parsing."""
        fetcher.client.option_chain = Mock(return_value=sample_option_chain_response)

        result = await fetcher.get_option_chain("BTCUSDT")

        # Check first strike
        strike_41000 = result.strikes.get(41000.0)
        assert strike_41000 is not None
        assert strike_41000.call.open_interest == 5000
        assert strike_41000.put.open_interest == 3000
        assert strike_41000.call.iv == 0.65
        assert strike_41000.put.iv == 0.70

    @pytest.mark.asyncio
    async def test_get_recent_trades(self, fetcher, sample_trades_response):
        """Test fetching recent trades."""
        fetcher.client.recent_trades = Mock(return_value=sample_trades_response)

        result = await fetcher.get_recent_trades("BTCUSDT", limit=100)

        assert result is not None
        assert len(result) == 2
        assert result[0]["premium"] == 150000
        assert result[0]["side"] == "BUY"

    @pytest.mark.asyncio
    async def test_get_open_interest(self, fetcher):
        """Test fetching open interest."""
        fetcher.client.open_interest = Mock(
            return_value={
                "symbol": "BTC-240115-42000-C",
                "openInterest": 5000,
                "time": 1705312800000,
            }
        )

        result = await fetcher.get_open_interest("BTC-240115-42000-C")

        assert result is not None
        assert result["open_interest"] == 5000

    @pytest.mark.asyncio
    async def test_get_available_symbols(self, fetcher):
        """Test getting available symbols."""
        fetcher.client.exchange_info = Mock(
            return_value={
                "optionSymbols": [
                    {"underlying": "BTCUSDT"},
                    {"underlying": "ETHUSDT"},
                    {"underlying": "BTCUSDT"},  # Duplicate
                ]
            }
        )

        result = await fetcher.get_available_symbols()

        assert "BTCUSDT" in result
        assert "ETHUSDT" in result
        assert len(result) == 2  # Unique only

    @pytest.mark.asyncio
    async def test_get_option_chain_error_handling(self, fetcher):
        """Test error handling in options chain fetch."""
        fetcher.client.option_chain = Mock(side_effect=Exception("API Error"))

        with pytest.raises(Exception):
            await fetcher.get_option_chain("BTCUSDT")


# =============================================================================
# Futures Fetcher Tests
# =============================================================================


class TestFuturesFetcher:
    """Tests for FuturesFetcher class."""

    @pytest.fixture
    def fetcher(self, mock_futures_client):
        """Create FuturesFetcher instance."""
        return FuturesFetcher(api_key="test_key", api_secret="test_secret", testnet=False)

    def test_init(self, fetcher):
        """Test FuturesFetcher initialization."""
        assert fetcher is not None
        assert fetcher.client is not None

    @pytest.mark.asyncio
    async def test_get_price(self, fetcher, sample_futures_ticker_response):
        """Test fetching futures price."""
        fetcher.client.ticker_24hr = Mock(return_value=sample_futures_ticker_response)

        result = await fetcher.get_price("BTCUSDT")

        assert result is not None
        assert isinstance(result, FuturesData)
        assert result.symbol == "BTCUSDT"
        assert result.price == 42150.0
        assert result.volume_24h == 1500000000.0
        assert result.price_change_pct == 2.5

    @pytest.mark.asyncio
    async def test_get_open_interest(self, fetcher):
        """Test fetching futures open interest."""
        fetcher.client.open_interest = Mock(
            return_value={"openInterest": "50000.5", "symbol": "BTCUSDT", "time": 1705312800000}
        )

        result = await fetcher.get_open_interest("BTCUSDT")

        assert result is not None
        assert result["open_interest"] == 50000.5

    @pytest.mark.asyncio
    async def test_get_funding_rate(self, fetcher):
        """Test fetching funding rate."""
        fetcher.client.funding_rate = Mock(
            return_value=[
                {"fundingRate": "0.0001", "fundingTime": 1705312800000, "symbol": "BTCUSDT"}
            ]
        )

        result = await fetcher.get_funding_rate("BTCUSDT")

        assert result is not None
        assert result["funding_rate"] == 0.0001

    @pytest.mark.asyncio
    async def test_get_mark_price(self, fetcher):
        """Test fetching mark price."""
        fetcher.client.mark_price = Mock(
            return_value={"markPrice": "42200.0", "indexPrice": "42180.0", "symbol": "BTCUSDT"}
        )

        result = await fetcher.get_mark_price("BTCUSDT")

        assert result is not None
        assert result["mark_price"] == 42200.0
        assert result["index_price"] == 42180.0

    @pytest.mark.asyncio
    async def test_get_klines(self, fetcher):
        """Test fetching klines."""
        fetcher.client.klines = Mock(
            return_value=[
                [1705312800000, "42000", "42500", "41800", "42200", "1000", 1705399200000],
                [1705399200000, "42200", "42800", "42000", "42500", "1200", 1705485600000],
            ]
        )

        result = await fetcher.get_klines("BTCUSDT", interval="1h", limit=2)

        assert result is not None
        assert len(result) == 2
        assert result[0]["open"] == 42000.0
        assert result[0]["high"] == 42500.0
        assert result[0]["low"] == 41800.0
        assert result[0]["close"] == 42200.0

    @pytest.mark.asyncio
    async def test_check_liquidity_sufficient(self, fetcher, sample_futures_ticker_response):
        """Test liquidity check with sufficient volume."""
        fetcher.client.ticker_24hr = Mock(return_value=sample_futures_ticker_response)

        result = await fetcher.check_liquidity("BTCUSDT", min_volume=1000000)

        assert result is True  # 1.5B > 1M

    @pytest.mark.asyncio
    async def test_check_liquidity_insufficient(self, fetcher, sample_futures_ticker_response):
        """Test liquidity check with insufficient volume."""
        fetcher.client.ticker_24hr = Mock(return_value=sample_futures_ticker_response)

        result = await fetcher.check_liquidity("BTCUSDT", min_volume=2000000000)

        assert result is False  # 1.5B < 2B


# =============================================================================
# Data Model Tests
# =============================================================================


class TestOptionsChainModel:
    """Tests for OptionsChain data model."""

    def test_create_options_chain(self):
        """Test creating options chain."""
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=10000,
            total_put_oi=8000,
        )

        assert chain.underlying == "BTCUSDT"
        assert chain.spot_price == 42000.0
        assert chain.total_call_oi == 10000
        assert chain.total_put_oi == 8000

    def test_get_pcr(self):
        """Test PCR calculation."""
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=10000,
            total_put_oi=8000,
        )

        pcr = chain.get_pcr()

        assert pcr == 0.8  # 8000 / 10000

    def test_get_pcr_zero_call_oi(self):
        """Test PCR with zero call OI."""
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_oi=0,
            total_put_oi=8000,
        )

        pcr = chain.get_pcr()

        assert pcr == float("inf")

    def test_get_volume_pcr(self):
        """Test volume PCR calculation."""
        chain = OptionsChain(
            underlying="BTCUSDT",
            spot_price=42000.0,
            timestamp=datetime.utcnow(),
            total_call_volume=5000.0,
            total_put_volume=4000.0,
        )

        pcr = chain.get_volume_pcr()

        assert pcr == 0.8  # 4000 / 5000


class TestFuturesDataModel:
    """Tests for FuturesData data model."""

    def test_create_futures_data(self):
        """Test creating futures data."""
        data = FuturesData(
            symbol="BTCUSDT",
            price=42000.0,
            timestamp=datetime.utcnow(),
            volume_24h=1500000000.0,
            open_interest=50000.0,
            funding_rate=0.0001,
        )

        assert data.symbol == "BTCUSDT"
        assert data.price == 42000.0
        assert data.volume_24h == 1500000000.0
        assert data.open_interest == 50000.0
        assert data.funding_rate == 0.0001


class TestStrikeDataModel:
    """Tests for StrikeData data model."""

    def test_create_strike_data(self):
        """Test creating strike data."""
        strike = StrikeData(
            strike=42000.0,
            call=OptionData(open_interest=5000, volume=1000, iv=0.65),
            put=OptionData(open_interest=3000, volume=800, iv=0.70),
        )

        assert strike.strike == 42000.0
        assert strike.call.open_interest == 5000
        assert strike.put.open_interest == 3000
        assert strike.call.iv == 0.65
        assert strike.put.iv == 0.70


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestRateLimiter:
    """Tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_acquire(self):
        """Test rate limiter acquire."""
        from binance_signal_generator.utils.rate_limiter import RateLimiter

        limiter = RateLimiter(requests_per_second=10, burst=5)

        # Should acquire immediately
        await limiter.acquire()
        assert limiter._tokens == 4  # Decreased by 1

    @pytest.mark.asyncio
    async def test_rate_limiter_burst(self):
        """Test rate limiter burst capacity."""
        from binance_signal_generator.utils.rate_limiter import RateLimiter

        limiter = RateLimiter(requests_per_second=10, burst=5)

        # Should be able to acquire burst times
        for _ in range(5):
            await limiter.acquire()


# =============================================================================
# Integration Tests
# =============================================================================


class TestDataIntegration:
    """Integration tests for data modules."""

    @pytest.mark.asyncio
    async def test_full_options_flow(self, mock_options_client):
        """Test full options data fetching flow."""
        fetcher = OptionsFetcher(api_key="test_key", api_secret="test_secret")

        # Mock responses
        fetcher.client.exchange_info = Mock(
            return_value={"optionSymbols": [{"underlying": "BTCUSDT"}]}
        )

        fetcher.client.option_chain = Mock(
            return_value={"underlyingPrice": 42000.0, "optionChain": []}
        )

        # Get symbols
        symbols = await fetcher.get_available_symbols()
        assert "BTCUSDT" in symbols

        # Get option chain
        chain = await fetcher.get_option_chain("BTCUSDT")
        assert chain.spot_price == 42000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
