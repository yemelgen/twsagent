#!/usr/bin/env python
"""Configuration"""

import os
import sys
import configparser

# Path to the application and log directory
APP_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_PATH)
HOME_PATH = os.environ.get("HOME", PROJECT_ROOT)
DEFAULT_LOG_PATH = os.path.join(os.environ.get("TWS_LOGPATH", HOME_PATH), "logs")

# Default watchlist export path based on platform
if sys.platform == "win32":
    DEFAULT_WATCHLIST_PATH = os.path.join(HOME_PATH, "Jts", "export.csv")
elif sys.platform == "darwin":  # macOS
    DEFAULT_WATCHLIST_PATH = os.path.join(HOME_PATH, "Jts", "export.csv")
else:  # Linux and others
    DEFAULT_WATCHLIST_PATH = os.path.join(HOME_PATH, "Jts", "export.csv")

# Load settings from settings.ini with defaults
config = configparser.ConfigParser()
config.read_dict(
    {
        "grpc": {"host": "127.0.0.1", "port": "5005", "max_workers": "10"},
        "tws": {"host": "127.0.0.1", "port": "7497", "client_id": "1"},
        "logging": {"path": DEFAULT_LOG_PATH, "filename": "twsagent.log"},
        "watchlist": {"export_path": DEFAULT_WATCHLIST_PATH},
        "pacing": {
            "historical_max_requests": "50",
            "historical_window_seconds": "600",
            "identical_gap_seconds": "15",
            "general_min_interval_seconds": "1.0",
            "contract_max_requests": "5",
            "contract_window_seconds": "2.0",
        },
    }
)
config.read(os.path.join(PROJECT_ROOT, "settings.ini"))

# Read from INI file first, then override with environment variables
os.environ["GRPC_HOST"] = os.environ.get("GRPC_HOST") or config.get("grpc", "host")
os.environ["GRPC_PORT"] = os.environ.get("GRPC_PORT") or config.get("grpc", "port")
os.environ["GRPC_MAX_WORKERS"] = os.environ.get("GRPC_MAX_WORKERS") or config.get(
    "grpc", "max_workers"
)
os.environ["TWS_HOST"] = os.environ.get("TWS_HOST") or config.get("tws", "host")
os.environ["TWS_PORT"] = os.environ.get("TWS_PORT") or config.get("tws", "port")
os.environ["TWS_CLIENT_ID"] = os.environ.get("TWS_CLIENT_ID") or config.get(
    "tws", "client_id"
)

# Pacing configuration
PACING_HIST_MAX = int(
    os.environ.get("PACING_HIST_MAX") or config.get("pacing", "historical_max_requests")
)
PACING_HIST_WINDOW = int(
    os.environ.get("PACING_HIST_WINDOW")
    or config.get("pacing", "historical_window_seconds")
)
PACING_IDENTICAL_GAP = int(
    os.environ.get("PACING_IDENTICAL_GAP")
    or config.get("pacing", "identical_gap_seconds")
)
PACING_GENERAL_INTERVAL = float(
    os.environ.get("PACING_GENERAL_INTERVAL")
    or config.get("pacing", "general_min_interval_seconds")
)
PACING_CONTRACT_MAX = int(
    os.environ.get("PACING_CONTRACT_MAX")
    or config.get("pacing", "contract_max_requests")
)
PACING_CONTRACT_WINDOW = float(
    os.environ.get("PACING_CONTRACT_WINDOW")
    or config.get("pacing", "contract_window_seconds")
)

# Logging level configuration
IBAPI_LOG_LEVEL = os.environ.get("IBAPI_LOG_LEVEL", "WARNING")

# Logging configuration
LOG_PATH = config.get("logging", "path").format(
    home=HOME_PATH, project_root=PROJECT_ROOT
)
LOG_FILE = os.path.join(LOG_PATH, config.get("logging", "filename"))

# Watchlist export path
WATCHLIST_EXPORT_PATH = config.get("watchlist", "export_path").format(
    home=HOME_PATH, project_root=PROJECT_ROOT
)

# Ensure the log directory exists
if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)

# Define the logging configuration dictionary
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "log.CustomFormatter",
            "format": "%(levelname)s %(asctime)s %(name)s: %(message)s",
            "datefmt": "%d/%m/%Y %H:%M:%S%z",
        },
    },
    "handlers": {
        "rotating_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "default",
            "filename": LOG_FILE,
            "maxBytes": 1048576 * 3,  # 3 MB
            "backupCount": 7,
            "encoding": "utf8",
        },
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["rotating_file", "console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "grpc": {
            "handlers": ["rotating_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "ibapi": {
            "handlers": ["rotating_file", "console"],
            "level": IBAPI_LOG_LEVEL,
            "propagate": False,
        },
    },
    "root": {"level": "DEBUG", "handlers": ["rotating_file", "console"]},
}
