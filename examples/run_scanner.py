#!/usr/bin/env python3
"""
Run market scanner to find securities matching specific criteria.

The market scanner can find stocks, options, futures, etc.
based on various criteria
like most active, top gainers/losers, highest volume, etc.

Common scan codes:
  - TOP_PERC_GAIN: Top % gainers
  - TOP_PERC_LOSE: Top % losers
  - MOST_ACTIVE: Most active by volume
  - MOST_ACTIVE_USD: Most active by dollar volume
  - HOT_BY_VOLUME: Stocks with unusual volume
  - HOT_BY_PRICE: Stocks with unusual price activity
  - HOT_BY_PRICE_RANGE: Hot by price range
  - HOT_BY_OPT_VOLUME: Hot by option volume
  - OPT_VOLUME_MOST_ACTIVE: Highest option volume
  - HIGH_OPT_VOLUME_PUT_CALL_RATIO: High option put/call ratio
  - LOW_OPT_VOLUME_PUT_CALL_RATIO: Low option put/call ratio
  - TOP_VOLUME_RATE: Highest volume rate
  - NOT_YET_TRADED_TODAY: Not yet traded today

Location codes:
  - STK.US: All US stocks
  - STK.US.MAJOR: Major US exchanges (NYSE, NASDAQ, AMEX, ARCA, BATS)
  - STK.US.MINOR: OTC Markets (Pink Sheets)
  - STK.NASDAQ: NASDAQ only
  - STK.NASDAQ.NMS: NASDAQ National Market
  - STK.NASDAQ.SCM: NASDAQ Small Cap
  - STK.NYSE: NYSE only
  - STK.AMEX: AMEX only
  - STK.ARCA: ARCA only
  - STK.BATS: BATS only
  - ETF.EQ.US: US Equity ETFs
  - ETF.FI.US: US Fixed Income ETFs

Examples:
    # Get available scanner parameters (scan codes, locations, filters)
    python run_scanner.py --params

    # List available scan codes in a readable format
    python run_scanner.py --list-scans

    # List available location codes
    python run_scanner.py --list-locations

    # Top 20 % gainers on major US exchanges
    python run_scanner.py --scan TOP_PERC_GAIN --location STK.US.MAJOR --rows 20

    # Most active stocks with price > $10
    python run_scanner.py --scan MOST_ACTIVE --above-price 10

    # Top option volume stocks
    python run_scanner.py --scan OPT_VOLUME_MOST_ACTIVE --rows 50

    # Small cap gainers (market cap under $2B)
    python run_scanner.py --scan TOP_PERC_GAIN --market-cap-below 2e9

    # Large cap stocks with unusual volume
    python run_scanner.py --scan HOT_BY_VOLUME --market-cap-above 10e9
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "stubs"))

import grpc
import tws_pb2
import tws_pb2_grpc


def ensure_connected(stub):
    """Ensure connection to TWS/Gateway"""
    try:
        response = stub.Connect(tws_pb2.ConnectRequest())
        if not response.success:
            print(f"Warning: {response.message}", file=sys.stderr)
    except Exception as e:
        print(f"Connection warning: {e}", file=sys.stderr)


def run_scanner(
    host="localhost",
    port=5005,
    scan_code="MOST_ACTIVE",
    location="STK.US.MAJOR",
    instrument="STK",
    rows=50,
    above_price=0,
    below_price=0,
    above_volume=0,
    market_cap_above=0,
    market_cap_below=0,
    stock_type="ALL",
    output_format="json",
    output_file=None,
):
    """Run a market scanner query"""
    channel = grpc.insecure_channel(f"{host}:{port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    ensure_connected(stub)

    request = tws_pb2.MarketScannerRequest(
        number_of_rows=rows,
        instrument=instrument,
        location_code=location,
        scan_code=scan_code,
        above_price=above_price,
        below_price=below_price,
        above_volume=above_volume,
        market_cap_above=market_cap_above,
        market_cap_below=market_cap_below,
        stock_type_filter=stock_type,
    )

    response = stub.RunMarketScanner(request)

    results = []
    for result in response.results:
        result_dict = {
            "rank": result.rank,
            "con_id": result.con_id,
            "symbol": result.symbol,
            "sec_type": result.sec_type,
            "primary_exchange": result.primary_exchange,
            "currency": result.currency,
            "local_symbol": result.local_symbol,
            "trading_class": result.trading_class,
            "distance": result.distance,
            "benchmark": result.benchmark,
            "projection": result.projection,
            "market_name": result.market_name,
        }
        results.append(result_dict)

    if output_format == "flat":
        output = "\n".join(json.dumps(result) for result in results)
    elif output_format == "simple":
        lines = [
            f"{r['rank']}. {r['symbol']} ({r['distance']})" for r in results
        ]
        output = "\n".join(lines)
    else:
        output = json.dumps(results, indent=2)

    if output_file:
        with open(output_file, "w") as f:
            f.write(output)
        print(f"Scanner results written to {output_file}")
    else:
        print(output)

    return len(results)


def parse_scan_codes(xml_string):
    """Parse scan codes from XML parameters"""
    try:
        root = ET.fromstring(xml_string)
        scans = []

        for scan_type in root.findall(".//ScanType"):
            display_name = scan_type.find("displayName")
            scan_code = scan_type.find("scanCode")
            instruments = scan_type.find("instruments")

            if display_name is not None and scan_code is not None:
                scan_info = {
                    "code": scan_code.text,
                    "name": display_name.text,
                    "instruments": instruments.text
                    if instruments is not None
                    else "",
                }
                scans.append(scan_info)

        return scans
    except Exception as e:
        print(f"Error parsing scan codes: {e}", file=sys.stderr)
        return []


def parse_location_codes(xml_string):
    """Parse location codes from XML parameters"""
    try:
        root = ET.fromstring(xml_string)
        locations = []

        def extract_locations(location_elem, parent_path=""):
            display_name = location_elem.find("displayName")
            location_code = location_elem.find("locationCode")
            instruments = location_elem.find("instruments")

            if display_name is not None and location_code is not None:
                loc_info = {
                    "code": location_code.text,
                    "name": display_name.text,
                    "instruments": instruments.text
                    if instruments is not None
                    else "",
                    "level": len(parent_path.split(".")) if parent_path else 0,
                }
                locations.append(loc_info)

            # Recursively process child locations
            location_tree = location_elem.find("LocationTree")
            if location_tree is not None:
                for child_loc in location_tree.findall("Location"):
                    extract_locations(
                        child_loc,
                        location_code.text if location_code is not None else "",
                    )

        for location in root.findall(".//LocationTree/Location"):
            extract_locations(location)

        return locations
    except Exception as e:
        print(f"Error parsing location codes: {e}", file=sys.stderr)
        return []


def list_scan_codes(host="localhost", port=5005, instrument_filter=None):
    """List available scan codes in a readable format"""
    channel = grpc.insecure_channel(f"{host}:{port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    # Ensure connected to TWS
    ensure_connected(stub)

    request = tws_pb2.ScannerParametersRequest()
    response = stub.GetScannerParameters(request)

    if not response.xml:
        print("No scanner parameters returned", file=sys.stderr)
        return False

    scans = parse_scan_codes(response.xml)

    # Filter by instrument if specified
    if instrument_filter:
        scans = [
            s for s in scans if instrument_filter in s["instruments"].split(",")
        ]

    # Group by first word of name for better organization
    groups = {}
    for scan in scans:
        first_word = scan["name"].split()[0] if scan["name"] else "Other"
        if first_word not in groups:
            groups[first_word] = []
        groups[first_word].append(scan)

    print(f"\nAvailable Scan Codes ({len(scans)} total):\n")
    for group, items in sorted(groups.items()):
        print(f"  {group}:")
        for scan in sorted(items, key=lambda x: x["name"]):
            instruments_str = (
                scan["instruments"][:50] + "..."
                if len(scan["instruments"]) > 50
                else scan["instruments"]
            )
            print(f"    {scan['code']:40s} - {scan['name']}")
            if instrument_filter is None and scan["instruments"]:
                print(f"      {'':40s}   Instruments: {instruments_str}")
        print()

    return True


def list_location_codes(host="localhost", port=5005):
    """List available location codes in a readable format"""
    channel = grpc.insecure_channel(f"{host}:{port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    # Ensure connected to TWS
    ensure_connected(stub)

    request = tws_pb2.ScannerParametersRequest()
    response = stub.GetScannerParameters(request)

    if not response.xml:
        print("No scanner parameters returned", file=sys.stderr)
        return False

    locations = parse_location_codes(response.xml)

    print(f"\nAvailable Location Codes ({len(locations)} total):\n")
    for loc in locations:
        indent = "  " * loc["level"]
        instruments_str = (
            f" [{loc['instruments']}]" if loc["instruments"] else ""
        )
        print(f"{indent}{loc['code']:30s} - {loc['name']}{instruments_str}")

    return True


def get_scanner_parameters(host="localhost", port=5005):
    """Get available scanner parameters"""
    channel = grpc.insecure_channel(f"{host}:{port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    ensure_connected(stub)

    request = tws_pb2.ScannerParametersRequest()
    response = stub.GetScannerParameters(request)

    if response.xml:
        print(response.xml)
        return True
    else:
        print("No scanner parameters returned", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Run market scanner")
    parser.add_argument("--host", default="localhost", help="gRPC server host")
    parser.add_argument(
        "--port", type=int, default=5005, help="gRPC server port"
    )
    parser.add_argument(
        "--params",
        action="store_true",
        help="Get scanner parameters as raw XML",
    )
    parser.add_argument(
        "--list-scans",
        action="store_true",
        help="List available scan codes in readable format",
    )
    parser.add_argument(
        "--list-locations",
        action="store_true",
        help="List available location codes in readable format",
    )
    parser.add_argument(
        "--scan",
        default="MOST_ACTIVE",
        help="Scan code (TOP_PERC_GAIN, MOST_ACTIVE, etc.)",
    )
    parser.add_argument(
        "--location",
        default="STK.US.MAJOR",
        help="Location code (STK.US.MAJOR, STK.NASDAQ, etc.)",
    )
    parser.add_argument(
        "--instrument",
        default="STK",
        help="Instrument type (STK, OPT, FUT, etc.)",
    )
    parser.add_argument(
        "--rows", type=int, default=50, help="Max number of results"
    )
    parser.add_argument(
        "--above-price", type=float, default=0, help="Minimum price filter"
    )
    parser.add_argument(
        "--below-price", type=float, default=0, help="Maximum price filter"
    )
    parser.add_argument(
        "--above-volume", type=int, default=0, help="Minimum volume filter"
    )
    parser.add_argument(
        "--market-cap-above",
        type=float,
        default=0,
        help="Minimum market cap filter (e.g., 1e9 for $1B)",
    )
    parser.add_argument(
        "--market-cap-below",
        type=float,
        default=0,
        help="Maximum market cap filter (e.g., 10e9 for $10B)",
    )
    parser.add_argument(
        "--stock-type",
        default="ALL",
        choices=["ALL", "STOCK", "ETF"],
        help="Stock type filter",
    )
    parser.add_argument(
        "--format",
        choices=["json", "flat", "simple"],
        default="json",
        help=(
            "Output format (json=pretty, flat=one per line, simple=rank symbol)"
        ),
    )
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")

    args = parser.parse_args()

    try:
        if args.params:
            success = get_scanner_parameters(host=args.host, port=args.port)
            sys.exit(0 if success else 1)

        if args.list_scans:
            success = list_scan_codes(
                host=args.host,
                port=args.port,
                instrument_filter=args.instrument
                if args.instrument != "STK"
                else None,
            )
            sys.exit(0 if success else 1)

        if args.list_locations:
            success = list_location_codes(host=args.host, port=args.port)
            sys.exit(0 if success else 1)

        count = run_scanner(
            host=args.host,
            port=args.port,
            scan_code=args.scan,
            location=args.location,
            instrument=args.instrument,
            rows=args.rows,
            above_price=args.above_price,
            below_price=args.below_price,
            above_volume=args.above_volume,
            market_cap_above=args.market_cap_above,
            market_cap_below=args.market_cap_below,
            stock_type=args.stock_type,
            output_format=args.format,
            output_file=args.output,
        )
        if not args.output:
            print(f"\nScanner returned {count} result(s)", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
