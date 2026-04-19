"""
Pytest configuration and fixtures
"""

import os
import sys
from pathlib import Path

import grpc
import pytest

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "stubs"))

import tws_pb2
import tws_pb2_grpc

# Default configuration values
os.environ["GRPC_HOST"] = os.getenv("GRPC_HOST", "127.0.0.1")
os.environ["GRPC_PORT"] = os.getenv("GRPC_PORT", "5005")
os.environ["TWS_HOST"] = os.getenv("TWS_HOST", "127.0.0.1")
os.environ["TWS_PORT"] = os.getenv("TWS_PORT", "7497")
os.environ["TWS_CLIENT_ID"] = os.getenv("TWS_CLIENT_ID", "1")


@pytest.fixture(scope="module")
def grpc_channel():
    """Create a gRPC channel to the server"""

    grpc_host = os.getenv("GRPC_HOST")
    grpc_port = os.getenv("GRPC_PORT")
    channel = grpc.insecure_channel(f"{grpc_host}:{grpc_port}")
    yield channel
    channel.close()


@pytest.fixture(scope="module")
def grpc_stub(grpc_channel):
    """Create a gRPC stub"""

    return tws_pb2_grpc.TWSAgentStub(grpc_channel)


@pytest.fixture(scope="module")
def tws_session(grpc_stub):
    """Ensure a TWS session is active for the tests"""

    grpc_stub.Connect(tws_pb2.ConnectRequest())
    yield
    grpc_stub.Disconnect(tws_pb2.DisconnectRequest())
