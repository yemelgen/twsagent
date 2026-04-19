"""
Tests for market scanner functionality.
"""

import pytest
import tws_pb2


@pytest.fixture
def connect(grpc_stub):
    """Ensure connection before running tests"""

    request = tws_pb2.ConnectRequest()
    response = grpc_stub.Connect(request)
    assert response.success, f"Connection failed: {response.message}"
    yield


def test_get_scanner_parameters(grpc_stub, connect):
    """Test retrieving scanner parameters"""

    request = tws_pb2.ScannerParametersRequest()
    response = grpc_stub.GetScannerParameters(request)

    assert hasattr(response, "xml")
    assert isinstance(response.xml, str)
    if response.xml:
        assert "scan" in response.xml.lower() or "instrument" in response.xml.lower()


def test_run_most_active_scanner(grpc_stub, connect):
    """Test running most active scanner"""

    request = tws_pb2.MarketScannerRequest(
        number_of_rows=10,
        instrument="STK",
        location_code="STK.US.MAJOR",
        scan_code="MOST_ACTIVE",
    )
    response = grpc_stub.RunMarketScanner(request)

    assert hasattr(response, "results")
    assert isinstance(len(response.results), int)
    assert len(response.results) > 0


def test_scanner_result_structure(grpc_stub, connect):
    """Test that scanner results have expected structure"""

    request = tws_pb2.MarketScannerRequest(
        number_of_rows=5,
        instrument="STK",
        location_code="STK.US.MAJOR",
        scan_code="MOST_ACTIVE",
    )
    response = grpc_stub.RunMarketScanner(request)

    if len(response.results) > 0:
        result = response.results[0]

        # Check basic fields
        assert hasattr(result, "rank")
        assert hasattr(result, "con_id")
        assert hasattr(result, "symbol")
        assert hasattr(result, "sec_type")
        assert hasattr(result, "currency")

        # Rank should be a non-negative integer (0-based)
        assert isinstance(result.rank, int)
        assert result.rank >= 0

        # Symbol should be a non-empty string
        assert isinstance(result.symbol, str)
        assert len(result.symbol) > 0
        assert len(result.symbol) > 0

        # Con ID should be positive
        assert isinstance(result.con_id, int)
        assert result.con_id > 0


def test_scanner_with_price_filter(grpc_stub, connect):
    """Test scanner with price filters"""

    request = tws_pb2.MarketScannerRequest(
        number_of_rows=10,
        instrument="STK",
        location_code="STK.US.MAJOR",
        scan_code="MOST_ACTIVE",
        above_price=10.0,  # Stocks above $10
        below_price=500.0,  # Stocks below $500
    )
    response = grpc_stub.RunMarketScanner(request)

    assert hasattr(response, "results")
    assert isinstance(len(response.results), int)


def test_scanner_top_gainers(grpc_stub, connect):
    """Test scanner for top % gainers"""

    request = tws_pb2.MarketScannerRequest(
        number_of_rows=20,
        instrument="STK",
        location_code="STK.US.MAJOR",
        scan_code="TOP_PERC_GAIN",
    )
    response = grpc_stub.RunMarketScanner(request)

    assert hasattr(response, "results")
    assert len(response.results) > 0

    # Results should be ranked
    if len(response.results) > 1:
        assert response.results[0].rank < response.results[1].rank
