#!/usr/bin/env python
"""
Debug script to test Binance API responses directly.
This helps identify the correct field names for SDK responses.
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")

async def test_futures_api():
    """Test Futures API response format."""
    from binance_common.configuration import ConfigurationRestAPI
    from binance_common.constants import DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL
    from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import DerivativesTradingUsdsFutures
    
    print("\n" + "="*60)
    print("TESTING FUTURES API")
    print("="*60)
    
    configuration = ConfigurationRestAPI(
        api_key=API_KEY,
        api_secret=API_SECRET,
        base_path=DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
    )
    
    client = DerivativesTradingUsdsFutures(config_rest_api=configuration)
    
    # Test ticker/24hr
    print("\n--- Testing /fapi/v1/ticker/24hr ---")
    try:
        response = client.rest_api.ticker24hr_price_change_statistics(symbol="BTCUSDT")
        data = response.data()
        
        print(f"Response type: {type(data)}")
        
        if isinstance(data, list):
            print(f"List length: {len(data)}")
            if len(data) > 0:
                data = data[0]
        
        if hasattr(data, '__dict__'):
            print("\nObject attributes:")
            for key, value in data.__dict__.items():
                if not key.startswith('_'):
                    print(f"  {key}: {value}")
        elif isinstance(data, dict):
            print("\nDict keys:")
            for key, value in data.items():
                print(f"  {key}: {value}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test mark price
    print("\n--- Testing /fapi/v1/premiumIndex ---")
    try:
        response = client.rest_api.mark_price(symbol="BTCUSDT")
        data = response.data()
        
        print(f"Response type: {type(data)}")
        
        if isinstance(data, list):
            print(f"List length: {len(data)}")
            if len(data) > 0:
                data = data[0]
        
        if hasattr(data, '__dict__'):
            print("\nObject attributes:")
            for key, value in data.__dict__.items():
                if not key.startswith('_'):
                    print(f"  {key}: {value}")
        elif isinstance(data, dict):
            print("\nDict keys:")
            for key, value in data.items():
                print(f"  {key}: {value}")
    except Exception as e:
        print(f"Error: {e}")


async def test_options_api():
    """Test Options API response format."""
    from binance_common.configuration import ConfigurationRestAPI
    from binance_common.constants import DERIVATIVES_TRADING_OPTIONS_REST_API_PROD_URL
    from binance_sdk_derivatives_trading_options.derivatives_trading_options import DerivativesTradingOptions
    
    print("\n" + "="*60)
    print("TESTING OPTIONS API")
    print("="*60)
    
    configuration = ConfigurationRestAPI(
        api_key=API_KEY,
        api_secret=API_SECRET,
        base_path=DERIVATIVES_TRADING_OPTIONS_REST_API_PROD_URL,
    )
    
    client = DerivativesTradingOptions(config_rest_api=configuration)
    
    # Test index price
    print("\n--- Testing /eapi/v1/index ---")
    try:
        response = client.rest_api.index_price(underlying="BTCUSDT")
        data = response.data()
        
        print(f"Response type: {type(data)}")
        
        if hasattr(data, '__dict__'):
            print("\nObject attributes:")
            for key, value in data.__dict__.items():
                if not key.startswith('_'):
                    print(f"  {key}: {value}")
        elif isinstance(data, dict):
            print("\nDict keys:")
            for key, value in data.items():
                print(f"  {key}: {value}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test open interest
    print("\n--- Testing /eapi/v1/openInterest ---")
    try:
        response = client.rest_api.open_interest(underlying_asset="BTC")
        data = response.data()
        
        print(f"Response type: {type(data)}")
        
        if isinstance(data, list):
            print(f"List length: {len(data)}")
            if len(data) > 0:
                item = data[0]
                print("\nFirst item:")
                if hasattr(item, '__dict__'):
                    for key, value in item.__dict__.items():
                        if not key.startswith('_'):
                            print(f"  {key}: {value}")
        elif hasattr(data, '__dict__'):
            print("\nObject attributes:")
            for key, value in data.__dict__.items():
                if not key.startswith('_'):
                    print(f"  {key}: {value}")
    except Exception as e:
        print(f"Error: {e}")


async def main():
    """Run all tests."""
    print("="*60)
    print("BINANCE API DEBUG SCRIPT")
    print("="*60)
    print(f"API Key: {API_KEY[:10]}..." if API_KEY else "No API Key set!")
    
    await test_futures_api()
    await test_options_api()
    
    print("\n" + "="*60)
    print("DEBUG COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
