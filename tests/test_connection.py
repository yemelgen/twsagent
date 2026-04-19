import os

import tws_pb2


def test_connect_success(grpc_stub):
    """Test successful connection to TWS"""

    response = grpc_stub.Connect(
        tws_pb2.ConnectRequest(
            host=os.getenv("TWS_HOST", "127.0.0.1"),
            port=int(os.getenv("TWS_PORT", "7497")),
            client_id=int(os.getenv("TWS_CLIENT_ID", "1")),
        )
    )

    assert response.success is True
    assert "Connected" in response.message or "Already connected" in response.message


def test_connect_with_defaults(grpc_stub):
    """Test connection using default parameters"""

    response = grpc_stub.Connect(tws_pb2.ConnectRequest())

    assert response.success is True


def test_disconnect(grpc_stub):
    """Test disconnection from TWS"""

    # First ensure we're connected
    grpc_stub.Connect(tws_pb2.ConnectRequest())

    # Then disconnect
    response = grpc_stub.Disconnect(tws_pb2.DisconnectRequest())

    assert response.success is True
