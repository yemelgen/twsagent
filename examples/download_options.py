#!/usr/bin/env python3
"""
Download option chain data from Interactive Brokers TWS

Retrieves available option expirations and strikes for underlying securities.
Output format is flat JSON arrays.

Examples:
  # Get option chain for AAPL
  python download_options.py AAPL

  # Get option chains for multiple symbols
  python download_options.py AAPL TSLA SPY

  # Read symbols from file
  python download_options.py --file symbols.txt

  # Save to file
  python download_options.py AAPL -o options.json

  # Get specific exchange
  python download_options.py AAPL --exchange SMART

  # Get option chain for a futures underlying
  python download_options.py ES --sec-type FUT

  # Get option chain for an index
  python download_options.py SPX --sec-type IND
"""

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "stubs"))

import grpc
import tws_pb2
import tws_pb2_grpc


def connect_tws(stub):
    """Connect to TWS"""

    response = stub.Connect(
        tws_pb2.ConnectRequest(host="127.0.0.1", port=7497, client_id=1)
    )
    if not response.success:
        raise Exception(f"Failed to connect: {response.message}")
    return response.message


def get_option_chain(stub, symbol, exchange="", sec_type="STK"):
    """Get option chain for a symbol"""

    try:
        response = stub.GetOptionChain(
            tws_pb2.OptionChainRequest(
                underlying_symbol=symbol,
                fut_fop_exchange=exchange,
                underlying_sec_type=sec_type,
                underlying_con_id=0,
            ),
            timeout=30,
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise TimeoutError(f"Timeout getting option chain for {symbol}")
        raise Exception(f"gRPC error: {e.details()}")

    if not response.chains:
        return []

    return response.chains


def format_option_chain_flat(symbol, chains):
    """Format option chain data as flat records

    Returns list of option records with one entry
    per expiration/strike combination.
    This makes it easy to stream individual option contracts.
    """

    records = []

    for chain in chains:
        for expiration in chain.expirations:
            for strike in chain.strikes:
                records.append(
                    {
                        "symbol": symbol,
                        "underlying_con_id": chain.underlying_con_id,
                        "exchange": chain.exchange,
                        "trading_class": chain.trading_class,
                        "multiplier": chain.multiplier,
                        "expiration": expiration,
                        "strike": strike,
                    }
                )

    return records


def format_option_chain_summary(symbol, chains):
    """Format option chain data as summary view

    Returns compact list with expirations and strikes grouped by exchange.
    Good for overview/analysis.
    """

    summaries = []

    for chain in chains:
        summaries.append(
            {
                "symbol": symbol,
                "underlying_con_id": chain.underlying_con_id,
                "exchange": chain.exchange,
                "trading_class": chain.trading_class,
                "multiplier": chain.multiplier,
                "expirations": list(chain.expirations),
                "strikes": list(chain.strikes),
                "num_expirations": len(chain.expirations),
                "num_strikes": len(chain.strikes),
                "total_contracts": len(chain.expirations)
                * len(chain.strikes)
                * 2,  # calls + puts
            }
        )

    return summaries


def main():
    parser = argparse.ArgumentParser(
        description="Download option chain data from Interactive Brokers TWS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("symbols", nargs="*", help="Ticker symbols (e.g., AAPL TSLA)")
    parser.add_argument("-f", "--file", help="Read symbols from file (one per line)")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument(
        "--exchange",
        default="",
        help='Exchange filter (default: "" for all exchanges)',
    )
    parser.add_argument(
        "--sec-type",
        default="STK",
        choices=["STK", "FUT", "IND", "FOP", "WAR", "IOPT"],
        help=(
            "Security type of the underlying:"
            " STK (stock), FUT (futures),"
            " IND (index), FOP (futures option),"
            " WAR (warrant),"
            " IOPT (Dutch structured product)"
            " (default: STK)"
        ),
    )
    parser.add_argument(
        "--format",
        choices=["flat", "summary"],
        default="flat",
        help="Output format: flat records or summary (grouped)",
    )
    parser.add_argument("--host", default="localhost", help="gRPC host")
    parser.add_argument("--port", type=int, default=5005, help="gRPC port")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )

    args = parser.parse_args()

    symbols = args.symbols or []
    if args.file:
        with open(args.file, "r") as f:
            file_symbols = [
                line.strip() for line in f if line.strip() and not line.startswith("#")
            ]
            symbols.extend(file_symbols)

    if not symbols:
        parser.error("No symbols provided. Use positional arguments or --file")

    channel = grpc.insecure_channel(f"{args.host}:{args.port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    try:
        print(connect_tws(stub), file=sys.stderr)
        print(f"Processing {len(symbols)} symbol(s)...", file=sys.stderr)

        all_records = []
        for i, symbol in enumerate(symbols, 1):
            try:
                print(
                    f"[{i}/{len(symbols)}] {symbol}...",
                    file=sys.stderr,
                    end=" ",
                )

                chains = get_option_chain(stub, symbol, args.exchange, args.sec_type)

                if not chains:
                    print("No option chain found", file=sys.stderr)
                    continue

                if args.format == "flat":
                    records = format_option_chain_flat(symbol, chains)
                else:
                    records = format_option_chain_summary(symbol, chains)

                all_records.extend(records)
                print(f"{len(records)} record(s) retrieved", file=sys.stderr)

                # Rate limiting
                if i < len(symbols):
                    time.sleep(args.delay)

            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                continue

        print(f"\nRetrieved {len(all_records)} total records", file=sys.stderr)

        if args.output:
            with open(args.output, "w") as f:
                json.dump(all_records, f, indent=2)
            size_kb = os.path.getsize(args.output) / 1024
            print(f"Saved to {args.output} ({size_kb:.2f} KB)", file=sys.stderr)
        else:
            json.dump(all_records, sys.stdout, indent=2)
            print()  # Newline

        stub.Disconnect(tws_pb2.DisconnectRequest())
        return 0

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
