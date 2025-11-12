#!/bin/bash

# TradingView Persistent Screener Service Stop Script

echo "Stopping TradingView Persistent Screener Service..."

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [ -f "$SCRIPT_DIR/logs/screener_service.pid" ]; then
    PID=$(cat "$SCRIPT_DIR/logs/screener_service.pid")
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        echo "✅ Service stopped (PID: $PID)"
        rm "$SCRIPT_DIR/logs/screener_service.pid"
    else
        echo "⚠️  No process found with PID: $PID"
        rm "$SCRIPT_DIR/logs/screener_service.pid"
    fi
else
    echo "⚠️  No PID file found. Service may not be running."
    # Try to find and kill the process anyway
    PYTHON_PID=$(lsof -ti:8765)
    if [ ! -z "$PYTHON_PID" ]; then
        kill $PYTHON_PID
        echo "✅ Killed process on port 8765 (PID: $PYTHON_PID)"
    fi
fi
