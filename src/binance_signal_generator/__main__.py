"""
Entry point for running the package as a module.

Usage:
    python -m binance_signal_generator [options]
    
This allows the package to be executed directly from the command line.
"""

import sys
from binance_signal_generator.cli import main

if __name__ == "__main__":
    sys.exit(main())
