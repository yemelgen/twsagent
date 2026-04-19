#!/usr/bin/env python3
"""
Example: Get watchlist from TWS export

This script retrieves your TWS watchlist and outputs it as JSON.

Usage:
    python examples/download_watchlist.py
    python examples/download_watchlist.py --export-path ~/Jts/export.csv
    python examples/download_watchlist.py -o watchlist.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

import grpc

# Add project root and stubs to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "stubs"))

import tws_pb2
import tws_pb2_grpc


def get_watchlist(stub, export_path=None):
    """Get watchlist from TWS export file"""

    request = tws_pb2.WatchlistRequest()
    if export_path:
        request.export_path = export_path

    try:
        response = stub.GetWatchlist(request)
        return response
    except grpc.RpcError as e:
        print(f"Error: {e.code()}: {e.details()}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Get watchlist from TWS export file")
    parser.add_argument(
        "--export-path",
        help="Path to TWS export.csv file (default: ~/Jts/export.csv)",
        default=None,
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file for JSON data (optional)",
        default=None,
    )
    parser.add_argument(
        "--grpc-host",
        default=os.getenv("GRPC_HOST", "127.0.0.1"),
        help="gRPC server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--grpc-port",
        default=os.getenv("GRPC_PORT", "5005"),
        help="gRPC server port (default: 5005)",
    )

    args = parser.parse_args()

    channel = grpc.insecure_channel(f"{args.grpc_host}:{args.grpc_port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    response = get_watchlist(stub, args.export_path)

    if not response:
        return 1

    if not response.contracts:
        print(json.dumps({"error": "Watchlist is empty or export file not found"}))
        return 1

    watchlist_data = []

    for contract in response.contracts:
        watchlist_data.append(
            {
                "symbol": contract.symbol,
                "sec_type": contract.sec_type,
                "exchange": contract.exchange,
                "primary_exchange": contract.primary_exchange,
                "expiry": contract.expiry,
                "strike": contract.strike,
                "right": contract.right,
                "multiplier": contract.multiplier,
                "currency": contract.currency,
            }
        )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(watchlist_data, f, indent=2)
    else:
        print(json.dumps(watchlist_data, indent=2))

    channel.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
