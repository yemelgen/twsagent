#!/usr/bin/env python3
"""
Download contract/security details from Interactive Brokers TWS

Retrieves detailed metadata about securities including identifiers,
exchange info, and classification data.

Examples:
  # Get details for a single symbol
  python download_contracts.py AAPL

  # Get details for multiple symbols
  python download_contracts.py AAPL MSFT GOOGL

  # Read symbols from file (one per line)
  python download_contracts.py --file symbols.txt

  # Save to file
  python download_contracts.py AAPL MSFT -o securities.json
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
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


def get_contract_details(stub, symbol, sec_type="STK", exchange="SMART"):
    """Get full contract details for a symbol"""

    try:
        response = stub.GetContractDetails(
            tws_pb2.ContractDetailsRequest(
                symbol=symbol,
                sec_type=sec_type,
                exchange=exchange,
                currency="USD",
            ),
            timeout=30,
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise TimeoutError(f"Timeout looking up {symbol}")
        raise Exception(f"gRPC error: {e.details()}")

    if not response.contracts:
        return None

    # Return the first contract (usually there's only one for stocks)
    return response.contracts[0]


def format_contract_as_security(contract, symbol):
    """Format IB contract data into securities table format"""

    # Map sec_type to asset_class
    asset_class_map = {
        "STK": "Equity",
        "OPT": "Option",
        "FUT": "Future",
        "CASH": "Forex",
        "BOND": "Bond",
        "CFD": "CFD",
        "FOP": "FutureOption",
        "FUND": "Fund",
        "CMDTY": "Commodity",
    }
    asset_class = asset_class_map.get(contract.sec_type, contract.sec_type)

    # Extract identifiers from security IDs
    identifiers = {
        "isin": None,
        "cusip": None,
        "sedol": None,
        "ric": None,  # Reuters Instrument Code
    }

    for sec_id in contract.sec_ids:
        tag_upper = sec_id.tag.upper()
        if tag_upper == "ISIN":
            identifiers["isin"] = sec_id.value
        elif tag_upper == "CUSIP":
            identifiers["cusip"] = sec_id.value
        elif tag_upper == "SEDOL":
            identifiers["sedol"] = sec_id.value
        elif tag_upper == "RIC":
            identifiers["ric"] = sec_id.value

    try:
        multiplier = float(contract.multiplier) if contract.multiplier else 1.0
    except (ValueError, AttributeError):
        multiplier = 1.0

    # Map category to sector (IB's category is often the sector)
    sector = contract.category or None

    security = {
        "symbol": contract.symbol or symbol,
        "asset_class": asset_class,
        "ibkr_conid": contract.con_id,
        # Identifiers
        "isin": identifiers["isin"],
        "cusip": identifiers["cusip"],
        "sedol": identifiers["sedol"],
        "cik": None,  # IBKR doesn't provide CIK (SEC identifier)
        "lei": None,  # IBKR doesn't provide LEI (Legal Entity Identifier)
        # Basic info
        "name": contract.long_name or contract.local_symbol,
        "currency": contract.currency,
        "primary_exchange": contract.primary_exchange or contract.exchange,
        # Trading info
        "min_tick": contract.min_tick,
        "multiplier": multiplier,
        # Classification
        "sector": sector,
        "industry": contract.industry or None,
        # Status
        "is_active": 1,
        "ts_updated": int(datetime.now().timestamp() * 1000),  # milliseconds
    }

    return security


def main():
    parser = argparse.ArgumentParser(
        description="Download contract details from Interactive Brokers TWS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("symbols", nargs="*", help="Ticker symbols (e.g., AAPL MSFT)")
    parser.add_argument("-f", "--file", help="Read symbols from file (one per line)")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("--sec-type", default="STK", help="Security type (default: STK)")
    parser.add_argument("--exchange", default="SMART", help="Exchange (default: SMART)")
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

        securities = []
        for i, symbol in enumerate(symbols, 1):
            try:
                print(
                    f"[{i}/{len(symbols)}] {symbol}...",
                    file=sys.stderr,
                    end=" ",
                )
                contract = get_contract_details(
                    stub, symbol, args.sec_type, args.exchange
                )

                if contract:
                    security = format_contract_as_security(contract, symbol)
                    securities.append(security)
                    print(f"{contract.con_id}", file=sys.stderr)
                else:
                    print("Not found", file=sys.stderr)

                # Rate limiting
                if i < len(symbols):
                    time.sleep(args.delay)

            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                continue

        print(f"\nRetrieved {len(securities)} securities", file=sys.stderr)

        if args.output:
            with open(args.output, "w") as f:
                json.dump(securities, f, indent=2)
            size_kb = os.path.getsize(args.output) / 1024
            print(f"Saved to {args.output} ({size_kb:.2f} KB)", file=sys.stderr)
        else:
            json.dump(securities, sys.stdout, indent=2)
            print()  # Newline

        stub.Disconnect(tws_pb2.DisconnectRequest())
        return 0

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
