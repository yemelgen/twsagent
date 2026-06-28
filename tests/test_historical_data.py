from datetime import datetime, time, timedelta, timezone

import pytest
import tws_pb2


@pytest.fixture
def aapl_contract_id(grpc_stub, tws_session):
    """Get AAPL contract ID for testing"""

    response = grpc_stub.GetContractDetails(
        tws_pb2.ContractDetailsRequest(
            symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD"
        )
    )
    assert len(response.contracts) > 0
    return response.contracts[0].con_id


def test_get_historical_data_daily(grpc_stub, aapl_contract_id, tws_session):
    """Test getting daily historical data"""

    response = grpc_stub.GetHistoricalData(
        tws_pb2.HistoricalDataRequest(
            con_id=aapl_contract_id,
            duration="1 D",
            bar_size="5 mins",
            what_to_show="TRADES",
            use_rth=False,
        )
    )

    assert len(response.bars) > 0

    bar = response.bars[0]
    assert bar.time != ""
    # Verify ISO 8601 format with UTC timezone
    dt = datetime.fromisoformat(bar.time)
    assert dt.tzinfo is not None
    assert bar.time.endswith("+00:00"), f"Expected UTC timezone, got: {bar.time}"

    assert bar.open > 0
    assert bar.high >= bar.open
    assert bar.low <= bar.close
    assert bar.volume >= 0


def test_get_historical_data_weekly(grpc_stub, aapl_contract_id, tws_session):
    """Test getting weekly historical data"""

    response = grpc_stub.GetHistoricalData(
        tws_pb2.HistoricalDataRequest(
            con_id=aapl_contract_id,
            duration="1 W",
            bar_size="1 hour",
            what_to_show="TRADES",
            use_rth=True,
        )
    )

    assert len(response.bars) > 0

    # Verify all bars have valid ISO 8601 timestamps
    for bar in response.bars:
        dt = datetime.fromisoformat(bar.time)
        assert dt.tzinfo is not None


def test_get_historical_data_bar_structure(grpc_stub, aapl_contract_id, tws_session):
    """Test that bars have correct structure"""

    response = grpc_stub.GetHistoricalData(
        tws_pb2.HistoricalDataRequest(
            con_id=aapl_contract_id,
            duration="1 D",
            bar_size="1 hour",
            what_to_show="TRADES",
            use_rth=False,
        )
    )

    assert len(response.bars) > 0

    previous_dt = None
    for bar in response.bars:
        dt = datetime.fromisoformat(bar.time)  # Will raise if not ISO 8601
        assert dt.tzinfo is not None, "Timestamp should have timezone info"
        assert bar.time.endswith("+00:00"), f"Expected UTC timezone, got: {bar.time}"

        # Chronological order check
        if previous_dt is not None:
            assert dt >= previous_dt, "Bars not in chronological order"
        previous_dt = dt

        # OHLC validation
        assert bar.high >= bar.low
        assert bar.high >= bar.open
        assert bar.high >= bar.close
        assert bar.low <= bar.open
        assert bar.low <= bar.close

        # Basic value checks
        assert bar.volume >= 0
        assert bar.wap >= 0


def test_get_historical_data_with_end_date_time(
    grpc_stub, aapl_contract_id, tws_session
):
    """Test historical bars ending at a specific IB timestamp"""

    end_dt = datetime.combine(
        datetime.now(timezone.utc).date(),
        time(21, 0),
        tzinfo=timezone.utc,
    )
    while end_dt.weekday() >= 5:
        end_dt -= timedelta(days=1)
    if end_dt > datetime.now(timezone.utc):
        end_dt -= timedelta(days=1)

    end_date_time = end_dt.strftime("%Y%m%d %H:%M:%S UTC")
    response = grpc_stub.GetHistoricalData(
        tws_pb2.HistoricalDataRequest(
            con_id=aapl_contract_id,
            duration="1 W",
            bar_size="1 hour",
            what_to_show="TRADES",
            use_rth=True,
            end_date_time=end_date_time,
        )
    )

    assert len(response.bars) > 0
    bar_times = [datetime.fromisoformat(bar.time) for bar in response.bars]
    assert max(bar_times) <= end_dt
