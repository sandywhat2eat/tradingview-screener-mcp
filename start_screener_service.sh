#!/bin/bash

# TradingView Persistent Screener Service Startup Script
# Starts the persistent browser service for fast 2-3 second screener data fetching

echo "Starting TradingView Persistent Screener Service..."

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment
source /Users/jaykrish/agents/project_output/venv/bin/activate

# Check if service is already running
if curl -s http://localhost:8765/health > /dev/null 2>&1; then
    echo "Service is already running!"
    echo "To restart, run: $0 restart"
    exit 0
fi

# Start the persistent service
cd "$SCRIPT_DIR"
nohup python3 python/tradingview_persistent_service.py > logs/screener_service.log 2>&1 &
SERVICE_PID=$!

echo "Service started with PID: $SERVICE_PID"
echo $SERVICE_PID > logs/screener_service.pid

# Wait for service to be ready
echo "Waiting for service to be ready..."
for i in {1..15}; do
    if curl -s http://localhost:8765/health > /dev/null 2>&1; then
        echo "✅ Service is ready!"
        echo ""
        echo "Service endpoints:"
        echo "  - Health: http://localhost:8765/health"
        echo "  - Status: http://localhost:8765/status"
        echo "  - Fetch: POST http://localhost:8765/fetch"
        echo ""
        echo "To stop the service, run: ./stop_screener_service.sh"
        exit 0
    fi
    sleep 1
done

echo "❌ Service failed to start. Check logs/screener_service.log for details."
exit 1
