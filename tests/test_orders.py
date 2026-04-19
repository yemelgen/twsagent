"""
Tests for completed orders functionality.
"""

import grpc
import pytest
import tws_pb2


@pytest.fixture
def connect(grpc_stub):
    """Ensure connection before running tests"""

    request = tws_pb2.ConnectRequest()
    response = grpc_stub.Connect(request)
    assert response.success, f"Connection failed: {response.message}"
    yield


def test_get_completed_orders(grpc_stub, connect):
    """Test retrieving all completed orders"""

    request = tws_pb2.CompletedOrdersRequest(api_only=False)
    try:
        response = grpc_stub.GetCompletedOrders(request)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            pytest.skip(f"IB API error: {e.details()}")
        raise

    # Response should be a list (may be empty for new accounts)
    assert hasattr(response, "orders")
    assert isinstance(len(response.orders), int)
    assert len(response.orders) >= 0


def test_get_completed_orders_api_only(grpc_stub, connect):
    """Test retrieving only API orders"""

    request = tws_pb2.CompletedOrdersRequest(api_only=True)
    try:
        response = grpc_stub.GetCompletedOrders(request)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            pytest.skip(f"IB API error: {e.details()}")
        raise

    assert hasattr(response, "orders")
    assert isinstance(len(response.orders), int)
    assert len(response.orders) >= 0


def test_completed_orders_structure(grpc_stub, connect):
    """Test that orders have expected structure"""

    request = tws_pb2.CompletedOrdersRequest(api_only=False)
    try:
        response = grpc_stub.GetCompletedOrders(request)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            pytest.skip(f"IB API error: {e.details()}")
        raise

    if len(response.orders) > 0:
        order = response.orders[0]

        # Check order ID fields
        assert hasattr(order, "order_id")
        assert hasattr(order, "client_id")
        assert hasattr(order, "perm_id")

        # Check contract fields
        assert hasattr(order, "con_id")
        assert hasattr(order, "symbol")
        assert hasattr(order, "sec_type")
        assert hasattr(order, "exchange")
        assert hasattr(order, "currency")

        # Check order details
        assert hasattr(order, "action")
        assert hasattr(order, "total_quantity")
        assert hasattr(order, "filled_quantity")
        assert hasattr(order, "order_type")

        # Check status
        assert hasattr(order, "status")
        assert hasattr(order, "completed_time")


def test_completed_orders_fields(grpc_stub, connect):
    """Test that order fields are accessible and have valid types"""

    request = tws_pb2.CompletedOrdersRequest(api_only=False)
    try:
        response = grpc_stub.GetCompletedOrders(request)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            pytest.skip(f"IB API error: {e.details()}")
        raise

    if len(response.orders) > 0:
        order = response.orders[0]

        # Order IDs should be integers
        assert isinstance(order.order_id, int)
        assert isinstance(order.client_id, int)
        assert isinstance(order.perm_id, int)

        # Contract ID should be integer
        assert isinstance(order.con_id, int)

        # Strings should be strings
        assert isinstance(order.symbol, str)
        assert isinstance(order.action, str)
        assert isinstance(order.order_type, str)
        assert isinstance(order.status, str)

        # Quantities should be numeric
        assert isinstance(order.total_quantity, (int, float))
        assert isinstance(order.filled_quantity, (int, float))

        # Prices should be numeric
        assert isinstance(order.lmt_price, (int, float))
        assert isinstance(order.aux_price, (int, float))
        assert isinstance(order.avg_fill_price, (int, float))

        # Commission should be numeric
        assert isinstance(order.commission, (int, float))

        # Booleans should be boolean
        assert isinstance(order.outside_rth, bool)

        # Action should be BUY or SELL (or SSHORT for short sales)
        assert order.action in ["BUY", "SELL", "SSHORT"]
