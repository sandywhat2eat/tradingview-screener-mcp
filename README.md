# TradingView Screener MCP Server

MCP Server for fetching TradingView screener data with dynamic configuration from Supabase. Provides fast 2-3 second response times using persistent browser sessions.

## Features

- **Dynamic Configuration**: Screeners loaded from Supabase `controls` table
- **Fast Response**: 2-3 second fetch times using persistent browser
- **Index Filtering**: Filter results by NIFTY indices (NIFTYBANK, NIFTYIT, etc.)
- **Auto-Configuration**: No code changes needed to add/remove screeners
- **Persistent Session**: Maintains browser session for optimal performance

## Installation

```bash
# Install Node.js dependencies
npm install

# Install Python dependencies (using existing venv)
source /Users/jaykrish/agents/project_output/venv/bin/activate
pip install -r requirements.txt
```

## Configuration

### Environment Variables (.env)

```bash
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
```

### TradingView Cookies

Copy `cookies.json` with TradingView authentication cookies to the root directory.

## Usage

### Start the Persistent Service

The persistent browser service must be running for optimal performance:

```bash
./start_screener_service.sh
```

### Start the MCP Server

```bash
npm start
```

### Stop the Persistent Service

```bash
./stop_screener_service.sh
```

## MCP Configuration

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "tradingview-screener": {
      "command": "node",
      "args": [
        "/Users/jaykrish/Documents/digitalocean/tradingview-screener-mcp/src/tradingview_screener_mcp.js"
      ]
    }
  }
}
```

## Available Tools

### 1. list_screener_types
List all available screener types from database.

### 2. fetch_screener_data
Fetch screener data for a specific type.

**Parameters:**
- `screener_type` (required): Strategy name from controls table
- `index_filter` (optional): NIFTYBANK, NIFTYIT, NIFTY50, etc.

**Example:**
```javascript
{
  "screener_type": "momentum_breakout_with_volume",
  "index_filter": "NIFTYBANK"
}
```

### 3. get_screener_session_health
Check persistent browser session health.

### 4. refresh_screener_session
Restart the browser session.

### 5. refresh_screener_config
Reload screener configurations from database.

### 6. get_screener_config
View current screener configuration.

## Database Schema

Screeners are configured in Supabase `controls` table:

```sql
SELECT strategy, url, description, holding_period, tradetype
FROM controls
WHERE on_off = 'ON'
  AND url LIKE '%tradingview.com%';
```

**Required columns:**
- `strategy`: Unique screener identifier
- `url`: TradingView screener URL
- `on_off`: 'ON' to enable
- `description`: Screener description
- `holding_period`: BTST, swing, position, etc.
- `tradetype`: LONG, SHORT, both

## Architecture

```
MCP Server (Node.js)
    ↓
Python Handler
    ↓
Persistent Browser Service (localhost:8765)
    ↓
TradingView Website (Selenium)
```

## Performance

- **First Request**: ~8-10 seconds (browser initialization)
- **Subsequent Requests**: 2-3 seconds (using persistent session)
- **Cache TTL**: 5 minutes for configuration
- **Session Lifetime**: Until manual restart or crash

## Troubleshooting

### Service Won't Start

```bash
# Check if port 8765 is in use
lsof -i :8765

# View service logs
tail -f logs/screener_service.log
```

### No Data Returned

1. Check cookies.json exists and is valid
2. Verify TradingView URL in database
3. Check service health: `curl http://localhost:8765/health`

### Database Connection Issues

1. Verify .env file has correct Supabase credentials
2. Check controls table has screeners with `on_off = 'ON'`
3. Ensure column names match: `description` (not `desc`)

## License

MIT
