"""
Command-line interface for the Binance Signal Generator.

This module provides the main entry point for running the signal
generation pipeline from the command line.

Usage:
    # Run with default config (adaptive asset selection)
    python -m binance_signal_generator
    
    # Run with custom config
    python -m binance_signal_generator --config /path/to/config.yaml
    
    # Run for specific symbols
    python -m binance_signal_generator --symbols BTCUSDT ETHUSDT
    
    # Dry run (no database)
    python -m binance_signal_generator --dry-run
    
    # Pretty print output
    python -m binance_signal_generator --pretty
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from typing import Optional, List

from binance_signal_generator import __version__
from binance_signal_generator.config.loader import load_config, Config
from binance_signal_generator.config.validators import ensure_valid_config
from binance_signal_generator.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig
from binance_signal_generator.output.json_output import JSONOutput, get_output_summary
from binance_signal_generator.utils.exceptions import SignalGeneratorError, PipelineError
from binance_signal_generator.utils.logging import setup_logging, get_logger
from binance_signal_generator.models import ExecutionResult

logger = get_logger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="binance-signals",
        description="Generate trading signals from Binance Options data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default config (adaptive selection)
  python -m binance_signal_generator
  
  # Run with custom config
  python -m binance_signal_generator --config /path/to/config.yaml
  
  # Run in dry-run mode (no database)
  python -m binance_signal_generator --dry-run
  
  # Run for specific symbols (bypasses activity scan)
  python -m binance_signal_generator --symbols BTCUSDT ETHUSDT
  
  # Pretty print JSON output
  python -m binance_signal_generator --pretty
  
  # Write output to file
  python -m binance_signal_generator --output signals.json
  
  # Compact output (one signal per line)
  python -m binance_signal_generator --compact
        """,
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to configuration file (default: ./config.yaml or env BINANCE_SIGNALS_CONFIG)",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without saving to database",
    )
    
    parser.add_argument(
        "--symbols",
        type=str,
        nargs="+",
        metavar="SYMBOL",
        help="Specific symbols to analyze (bypasses adaptive selection)",
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (can be used multiple times: -v, -vv)",
    )
    
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress all output except signals (errors go to stderr)",
    )
    
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty print JSON output with indentation",
    )
    
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Output one signal per line (compact format)",
    )
    
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate configuration and exit",
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="PATH",
        help="Write output to file instead of stdout",
    )
    
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        metavar="N",
        help="Number of top assets to analyze (default: 5)",
    )
    
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.30,
        metavar="SCORE",
        help="Minimum signal confidence to output (default: 0.30)",
    )
    
    parser.add_argument(
        "--min-activity",
        type=float,
        default=0.15,
        metavar="SCORE",
        help="Minimum activity score for asset selection (default: 0.15)",
    )
    
    return parser


def setup_verbosity(args: argparse.Namespace) -> str:
    """
    Determine log level from verbosity arguments.
    
    Args:
        args: Parsed arguments
        
    Returns:
        Log level string
    """
    if args.quiet:
        return "ERROR"
    
    if args.verbose >= 2:
        return "DEBUG"
    elif args.verbose >= 1:
        return "INFO"
    else:
        return "WARNING"


async def run_pipeline(
    config: Config,
    symbols: Optional[List[str]] = None,
    dry_run: bool = False,
    top_n: int = 5,
    min_confidence: float = 0.50,
    min_activity: float = 0.30,
) -> ExecutionResult:
    """
    Run the signal generation pipeline.
    
    Args:
        config: Configuration object
        symbols: Optional list of specific symbols to analyze
        dry_run: If True, don't save to database
        top_n: Number of top assets to analyze
        min_confidence: Minimum signal confidence
        min_activity: Minimum activity score for asset selection
        
    Returns:
        ExecutionResult with generated signals
    """
    # Create pipeline configuration
    pipeline_config = PipelineConfig(
        top_n_assets=top_n,
        min_activity_score=min_activity,
        min_signal_confidence=min_confidence,
        save_to_database=not dry_run,
    )
    
    # Initialize orchestrator
    orchestrator = PipelineOrchestrator(
        config=config,
        pipeline_config=pipeline_config,
    )
    
    try:
        # Run the pipeline
        result = await orchestrator.run(symbols=symbols)
        
        # Log summary
        summary = get_output_summary(result)
        logger.info("Pipeline completed", extra={"data": summary})
        
        return result
        
    finally:
        # Cleanup
        await orchestrator.close()


def output_result(
    result: ExecutionResult,
    pretty: bool = False,
    output_file: Optional[str] = None,
    compact: bool = False,
) -> None:
    """
    Output the execution result as JSON.
    
    Args:
        result: Execution result to output
        pretty: If True, pretty print JSON
        output_file: Optional file path to write output
        compact: If True, output one signal per line
    """
    output = JSONOutput(
        pretty=pretty,
        output_file=output_file,
        include_metadata=not compact,
    )
    output.output(result)


def main(args: Optional[List[str]] = None) -> int:
    """
    Main entry point for the CLI.
    
    Args:
        args: Command line arguments (default: sys.argv[1:])
        
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    # Load configuration
    try:
        config = load_config(parsed_args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        return 1
    
    # Setup logging
    log_level = setup_verbosity(parsed_args)
    setup_logging(
        level=log_level,
        log_file=config.logging.file_path if hasattr(config.logging, 'file_path') else None,
        console_enabled=log_level == "DEBUG",
        json_format=False,
    )
    
    # Validate configuration
    if parsed_args.validate_config:
        try:
            ensure_valid_config(config)
            print("Configuration is valid")
            return 0
        except Exception as e:
            print(f"Configuration validation failed: {e}", file=sys.stderr)
            return 1
    
    try:
        ensure_valid_config(config)
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    # Run the pipeline
    try:
        result = asyncio.run(
            run_pipeline(
                config=config,
                symbols=parsed_args.symbols,
                dry_run=parsed_args.dry_run,
                top_n=parsed_args.top_n,
                min_confidence=parsed_args.min_confidence,
                min_activity=parsed_args.min_activity,
            )
        )
        
        # Output result
        output_result(
            result,
            pretty=parsed_args.pretty,
            output_file=parsed_args.output,
            compact=parsed_args.compact,
        )
        
        # Return appropriate exit code
        if result.errors and not result.signals:
            return 1
        return 0
        
    except SignalGeneratorError as e:
        logger.error(f"Signal generation failed: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1
        
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        print("\nInterrupted", file=sys.stderr)
        return 130
        
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
