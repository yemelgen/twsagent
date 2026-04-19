# TWS Agent -- gRPC Service for Interactive Brokers TWS API

A gRPC-based service that provides a modern RPC interface to Interactive Brokers TWS/Gateway API.

## Features

- gRPC interface with protobuf serialization
- Timezone-aware datetime formatting utilities
- Connection management to TWS/Gateway
- Contract details lookup with full security identifiers
- Historical data retrieval with ISO 8601 formatted timestamps
- Historical tick data (TRADES, BID_ASK, MIDPOINT)
- Option chain retrieval (expirations and strikes)
- Wall Street Horizon corporate events (earnings, dividends, splits, etc.)
- Watchlist export parsing (read TWS watchlist from export.csv)
- Portfolio positions and completed orders
- Market scanner functionality
- Built-in IB API rate limiting (pacing) at the service level

## Architecture

```
Client Apps -> gRPC -> IBAgent Service -> ibapi -> TWS/Gateway
```

## Quick Start

### 1. Install

The install script creates a virtualenv, downloads the IB API, and installs dependencies:

```bash
python install.py
```

For development, you can install manually:

```bash
# Copy IB API Python source to project root
cp -r /path/to/TWS-API/source/pythonclient/ibapi ./ibapi

# Install in editable mode
pip install -e .
```

### 2. Start TWS or IB Gateway

Make sure TWS or IB Gateway is running and API connections are enabled:
- TWS Paper Trading: Port 7497
- TWS Live Trading: Port 7496
- Gateway Paper Trading: Port 4002
- Gateway Live Trading: Port 4001

### 3. Start the gRPC Server

```bash
./start.sh
```

### 4. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html
```

### 5. Use from Client Applications

See the [examples/](examples/) directory for Python client examples.

## Configuration

Set environment variables to customize the service:

```bash
# gRPC server settings
export GRPC_HOST=0.0.0.0
export GRPC_PORT=5005
export GRPC_MAX_WORKERS=10

# TWS/Gateway connection defaults
export TWS_HOST=127.0.0.1
export TWS_PORT=7497
export TWS_CLIENT_ID=1

# Logging configuration
export IBAPI_LOG_LEVEL=WARNING  # Options: DEBUG, INFO, WARNING, ERROR (default: WARNING)
```

Alternatively, edit `settings.ini`:

```ini
[grpc]
host = 127.0.0.1
port = 5005
max_workers = 10

[tws]
host = 127.0.0.1
port = 7497
client_id = 1

[logging]
path = {home}/logs
filename = twsagent.log

[watchlist]
export_path = {home}/Jts/export.csv

[pacing]
historical_max_requests = 50
historical_window_seconds = 600
identical_gap_seconds = 15
general_min_interval_seconds = 1.0
```

**Note:** Setting `IBAPI_LOG_LEVEL=WARNING` (default) suppresses verbose debug messages from the IB API library.

### Pacing (Rate Limiting)

The service enforces IB API pacing rules at the service level to prevent violations:

- **Historical data**: Max 50 requests per 10-minute sliding window, plus a 15-second gap between identical requests
- **General requests**: Minimum 1-second interval between any IB API calls

These limits are configurable via the `[pacing]` section in `settings.ini` or environment variables (`PACING_HIST_MAX`, `PACING_HIST_WINDOW`, `PACING_IDENTICAL_GAP`, `PACING_GENERAL_INTERVAL`).

### Watchlist Export

The service can read TWS watchlist data from the exported CSV file:

1. In TWS, export your watchlist using File > Export > Export Data
2. The default export location is `~/Jts/export.csv`
3. Configure the path in `settings.ini` if you use a different location
4. Call the `GetWatchlist` RPC method to retrieve the parsed watchlist

The parser supports all contract types: stocks (STK), options (OPT), futures (FUT), forex (CASH), crypto (CRYPTO), and indices (IND).

## Examples

### Download Bars (OHLCV)

```bash
python examples/download_bars.py TQQQ
python examples/download_bars.py TQQQ --bar-size 5s --days 2
python examples/download_bars.py TQQQ --bar-size 1d --years 2
python examples/download_bars.py TQQQ --extended -o bars.json
```

### Download Ticks

```bash
python examples/download_trades.py TQQQ --ts 1772205420 --duration 60
python examples/download_trades.py TQQQ --ts 1772160000 --duration 86400
python examples/download_trades.py TQQQ --ts 1772160000 --duration 86400 --extended -o trades.json
```

### Download Contract Details

```bash
python examples/download_contracts.py AAPL
python examples/download_contracts.py AAPL MSFT GOOGL
python examples/download_contracts.py --file symbols.txt -o securities.json
```

### Download Option Chains

```bash
python examples/download_options.py AAPL
python examples/download_options.py AAPL TSLA SPY
python examples/download_options.py ES --sec-type FUT
```

### Download Corporate Events (WSH)

Requires a Wall Street Horizon subscription.

```bash
python examples/download_events.py AAPL
python examples/download_events.py AAPL --filter Earnings
python examples/download_events.py AAPL --start 20240101 --end 20241231
```

### Download Positions

```bash
python examples/download_positions.py
python examples/download_positions.py -o positions.json
```

### Download Completed Orders

```bash
python examples/download_orders.py
python examples/download_orders.py --api-only
python examples/download_orders.py --format flat -o orders.json
```

### Download Watchlist

```bash
python examples/download_watchlist.py
python examples/download_watchlist.py --export-path ~/Jts/export.csv
python examples/download_watchlist.py -o watchlist.json
```

### Run Market Scanner

```bash
python examples/run_scanner.py --list-scans
python examples/run_scanner.py --scan TOP_PERC_GAIN --location STK.US.MAJOR --rows 20
python examples/run_scanner.py --scan MOST_ACTIVE --above-price 10
```

## Development

### Regenerate Protobuf Code

**IMPORTANT:** The files `stubs/tws_pb2.py` and `stubs/tws_pb2_grpc.py` are **auto-generated**. Never edit them manually.

When you modify [proto/tws.proto](proto/tws.proto), regenerate the Python code:

```bash
pip install grpcio-tools protobuf

mkdir -p stubs
touch stubs/__init__.py

python3 -m grpc_tools.protoc \
  --proto_path=./proto \
  --python_out=./stubs \
  --grpc_python_out=./stubs \
  proto/tws.proto
```

Restart your server to use the new generated code.

## Documentation

- [TWS API Documentation](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#api-introduction)
- [TWS API Reference](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-ref/#introduction)
- [TWS API Download](https://interactivebrokers.github.io/)
- [gRPC Python Guide](https://grpc.io/docs/languages/python/)


## License

MIT
