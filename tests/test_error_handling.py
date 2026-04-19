import grpc
import pytest
import tws_pb2


def test_invalid_contract_id(grpc_stub, tws_session):
    """Test handling of invalid contract ID"""

    with pytest.raises(grpc.RpcError) as exc_info:
        grpc_stub.GetHistoricalData(
            tws_pb2.HistoricalDataRequest(
                con_id=999999999,  # Invalid contract ID
                duration="1 D",
                bar_size="5 mins",
                what_to_show="TRADES",
                use_rth=False,
            )
        )
    assert exc_info.value.code() == grpc.StatusCode.INTERNAL


def test_operations_without_connection(grpc_stub):
    """Test that operations require connection"""

    # Disconnect first
    grpc_stub.Disconnect(tws_pb2.DisconnectRequest())

    # Try to get contract details without connection
    # Should raise FAILED_PRECONDITION error
    with pytest.raises(grpc.RpcError) as exc_info:
        grpc_stub.GetContractDetails(
            tws_pb2.ContractDetailsRequest(
                symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD"
            )
        )

    # Verify the error details
    assert exc_info.value.code() == grpc.StatusCode.FAILED_PRECONDITION
    assert "Not connected to TWS/Gateway" in exc_info.value.details()
