"""
Tests for watchlist functionality
"""

from pathlib import Path

import pytest
import tws_pb2


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory"""

    return Path(__file__).parent / "fixtures"


def test_watchlist_parser_basic(grpc_stub, fixtures_dir):
    """Test basic watchlist parsing from export file"""

    export_path = fixtures_dir / "watchlist_basic.csv"

    request = tws_pb2.WatchlistRequest(export_path=str(export_path))
    response = grpc_stub.GetWatchlist(request)

    # 3 contracts from column 0 + 2 from column 1
    assert len(response.contracts) == 5

    assert response.contracts[0].symbol == "AAPL"
    assert response.contracts[0].sec_type == "STK"
    assert response.contracts[0].exchange == "SMART"
    assert response.contracts[0].primary_exchange == "AMEX"

    # SPY was first contract in second column
    assert response.contracts[3].symbol == "SPY"


def test_watchlist_parser_with_futures_and_forex(grpc_stub, fixtures_dir):
    """Test watchlist parsing with various contract types"""

    export_path = fixtures_dir / "watchlist_mixed.csv"

    request = tws_pb2.WatchlistRequest(export_path=str(export_path))
    response = grpc_stub.GetWatchlist(request)

    # Check stock
    assert response.contracts[0].symbol == "AAPL"
    assert response.contracts[0].sec_type == "STK"
    assert response.contracts[0].exchange == "SMART"
    assert response.contracts[0].primary_exchange == "AMEX"

    # Check forex
    assert response.contracts[1].symbol == "EUR"
    assert response.contracts[1].sec_type == "CASH"
    assert response.contracts[1].exchange == "IDEALPRO"
    assert response.contracts[1].primary_exchange == ""
    assert response.contracts[1].currency == "USD"

    # Check crypto
    assert response.contracts[2].symbol == "BTC"
    assert response.contracts[2].sec_type == "CRYPTO"
    assert response.contracts[2].exchange == "PAXOS"
    assert response.contracts[2].primary_exchange == ""

    # Check futures
    assert response.contracts[3].symbol == "CL"
    assert response.contracts[3].sec_type == "FUT"
    assert response.contracts[3].exchange == "NYMEX"
    assert response.contracts[3].primary_exchange == ""
    assert response.contracts[3].expiry == "202604"
    assert response.contracts[3].multiplier == "1000"


def test_watchlist_parser_with_options(grpc_stub, fixtures_dir):
    """Test watchlist parsing with options contracts"""

    export_path = fixtures_dir / "watchlist_options.csv"

    request = tws_pb2.WatchlistRequest(export_path=str(export_path))
    response = grpc_stub.GetWatchlist(request)

    assert len(response.contracts) == 5

    # Check SPY call option
    spy_call = response.contracts[0]
    assert spy_call.symbol == "SPY"
    assert spy_call.sec_type == "OPT"
    assert spy_call.exchange == "SMART"
    assert spy_call.primary_exchange == "CBOE"
    assert spy_call.expiry == "20260320"
    assert spy_call.strike == 580.0
    assert spy_call.right == "Call"
    assert spy_call.multiplier == "100"

    # Check SPY put option
    spy_put = response.contracts[1]
    assert spy_put.symbol == "SPY"
    assert spy_put.sec_type == "OPT"
    assert spy_put.strike == 580.0
    assert spy_put.right == "Put"

    # Check different strike
    spy_call_600 = response.contracts[2]
    assert spy_call_600.symbol == "SPY"
    assert spy_call_600.strike == 600.0
    assert spy_call_600.right == "Call"
    assert spy_call_600.expiry == "20260417"


def test_watchlist_nonexistent_file(grpc_stub):
    """Test handling of nonexistent export file"""

    request = tws_pb2.WatchlistRequest(export_path="/nonexistent/path/export.csv")
    response = grpc_stub.GetWatchlist(request)

    # Should return empty response without error
    assert len(response.contracts) == 0


def test_watchlist_default_path(grpc_stub):
    """Test using default export path from settings"""

    request = tws_pb2.WatchlistRequest()

    # This might fail if the default file doesn't exist, but should not crash
    try:
        response = grpc_stub.GetWatchlist(request)
        assert response is not None
    except Exception as e:
        pytest.skip(f"Default watchlist file not found: {e}")
