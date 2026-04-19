import logging
import logging.config
import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "stubs"))

# Import the gRPC service implementation
from service import serve
from settings import LOGGING

# Configure logging
logging.config.dictConfig(LOGGING)


if __name__ == "__main__":
    serve()
