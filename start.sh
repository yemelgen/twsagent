#!/bin/bash
# Start the IB Agent gRPC server

# Get the directory of this script
APPDIR=$(dirname $(readlink -f $0))


# Activate virtualenv if it exists
if [ -d "$APPDIR/venv" ]; then
    # shellcheck disable=SC1090
    source "$APPDIR/venv/bin/activate"
fi

# Check if IB API is installed
if [ ! -d "$APPDIR/ibapi" ]; then
    echo "Error: ibapi module not found. Please install the IB API."
    exit 1
fi

# Start the gRPC server
exec /usr/bin/env python3 "$APPDIR/app/main.py" "$@"
