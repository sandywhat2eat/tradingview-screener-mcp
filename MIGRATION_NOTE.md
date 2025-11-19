# TradingView Screener - Extraction from dhan-data-mcp

## Migration Date
November 12, 2025

## Reason for Extraction

The TradingView screener functionality was originally part of `dhan-data-mcp` but has been extracted into a separate standalone MCP server for the following reasons:

### 1. Different Data Source
- **dhan-data-mcp**: Uses Dhan API (official REST API with JSON responses)
- **TradingView screener**: Web scraping TradingView website (HTML/CSV extraction)

### 2. Different Architecture
- **dhan-data-mcp**: Direct API calls to Dhan servers (fast, reliable, no browser needed)
- **TradingView screener**: Requires persistent browser session (Selenium + Chrome) for web automation

### 3. Different Dependencies
- **dhan-data-mcp**: Lightweight (axios, dhanhq library)
- **TradingView screener**: Heavy (Selenium, ChromeDriver, Pandas, browser automation)

### 4. Different Performance Characteristics
- **dhan-data-mcp**: Sub-second responses, no state management
- **TradingView screener**: 10-18 second responses, persistent session required

### 5. Single Responsibility Principle
- **dhan-data-mcp**: Market data from official Dhan API
- **TradingView screener**: Screener alerts from TradingView web interface

## What Was Extracted

### Tools Moved to tradingview-screener-mcp:
1. `list_screener_types` - List available TradingView screeners
2. `list_screener_indices` - List index filters (NIFTYBANK, NIFTYIT, etc.)
3. `fetch_screener_data` - Fetch screener results from TradingView
4. `get_screener_session_health` - Check browser session health
5. `refresh_screener_session` - Restart browser session
6. `refresh_screener_config` - Reload screener config from database
7. `get_screener_config` - Get current screener configuration

### Python Modules Moved:
- `python/tradingview_persistent_service.py` - Persistent browser session manager
- `python/tradingview_screener_handler.py` - MCP handler for screener tools
- `python/screener_config_manager.py` - Database configuration manager

### Configuration Files:
- `cookies.json` - TradingView authentication cookies
- `start_screener_service.sh` - Service startup script
- `stop_screener_service.sh` - Service shutdown script

## Key Improvement: CSV Download

The extracted version now uses **CSV download** instead of HTML scraping:

### Before (HTML Scraping):
```
"Pattern\n15m": "",  // Empty - patterns rendered as icons
"Pattern\n5m": "",   // Empty - not captured
```

### After (CSV Download):
```json
"Candlestick Pattern 15 minutes": "Dragonfly Doji, Long Lower Shadow",
"Candlestick Pattern 5 minutes": "Hammer, Long Lower Shadow"
```

**Benefits:**
- ✅ Complete data with ALL TradingView columns
- ✅ Candlestick pattern names captured correctly
- ✅ More reliable (CSV format is stable)
- ✅ Auto-cleanup (CSV deleted after parsing)

## Migration Path

### Old Usage (dhan-data-mcp):
```javascript
mcp__dhan-data-mcp__fetch_screener_data
mcp__dhan-data-mcp__list_screener_types
```

### New Usage (tradingview-screener):
```javascript
mcp__tradingview-screener__fetch_screener_data
mcp__tradingview-screener__list_screener_types
```

### Configuration Update:

**Remove from dhan-data-mcp tools:**
- fetch_screener_data
- list_screener_types
- list_screener_indices
- get_screener_session_health
- refresh_screener_session
- refresh_screener_config
- get_screener_config

**Add new MCP server to .mcp.json:**
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

## Service Management

### Start Persistent Browser Service:
```bash
cd /Users/jaykrish/Documents/digitalocean/tradingview-screener-mcp
./start_screener_service.sh
```

### Stop Service:
```bash
./stop_screener_service.sh
```

### Check Service Health:
```bash
curl http://localhost:8765/health
```

## Database Schema Requirements

The screener loads configuration from Supabase `controls` table:

**Required columns:**
- `strategy` - Screener identifier
- `url` - TradingView screener URL (must contain 'tradingview.com')
- `on_off` - 'ON' to enable
- `description` - Screener description
- `holding_period` - BTST, swing, position, etc.
- `tradetype` - LONG, SHORT, both
- `instrument_type` - EQ, FUT, OPT
- `max_positions` - Position limit

**Only strategies with TradingView URLs are loaded** (filters by `url LIKE '%tradingview.com%'`).

## Performance Comparison

### dhan-data-mcp (Dhan API):
- Response time: 0.5-2 seconds
- No session management needed
- Unlimited requests
- Official API data

### tradingview-screener (Web Scraping):
- Response time: 12-18 seconds
- Persistent browser session required
- Rate limiting concerns
- Richer screener data with candlestick patterns

## Architecture Benefits

### Before (Monolithic):
```
dhan-data-mcp
├── Dhan API tools (market data)
├── TradingView scraping (screeners) ← Mixed concerns
└── Heavy dependencies for both
```

### After (Separated):
```
dhan-data-mcp
└── Dhan API only (clean, focused)

tradingview-screener-mcp
└── TradingView screeners (isolated, specialized)
```

**Benefits:**
- ✅ Clean separation of concerns
- ✅ Independent scaling (can run on different machines)
- ✅ Easier debugging (logs separated)
- ✅ Faster startup (dhan-data-mcp no longer loads browser)
- ✅ Can disable TradingView without affecting market data

## Backward Compatibility

### Breaking Changes:
- Tool names changed (prefix changed from `dhan-data-mcp` to `tradingview-screener`)
- Service must be started manually (persistent browser session)

### Migration Checklist:
- [ ] Update all code using `mcp__dhan-data-mcp__*screener*` tools
- [ ] Add `tradingview-screener` to `.mcp.json`
- [ ] Start persistent screener service before using
- [ ] Update documentation and scripts

## Future Enhancements

### Potential Improvements:
1. Auto-start service when first tool is called
2. Multiple screener sessions (parallel downloads)
3. Caching layer for frequently accessed screeners
4. Screenshot capture on scraping failures
5. Proxy rotation for rate limit handling

## Rollback Plan

If issues arise, the old implementation is available in dhan-data-mcp git history:
```bash
cd /Users/jaykrish/Documents/digitalocean/dhan-data-mcp
git log --all --grep="tradingview" --oneline
```

## Contact

For issues or questions about this migration, check:
- `/Users/jaykrish/Documents/digitalocean/tradingview-screener-mcp/README.md`
- `/Users/jaykrish/Documents/digitalocean/tradingview-screener-mcp/logs/screener_service.log`

---

**Status:** ✅ MIGRATION COMPLETE
**Verified:** Candlestick patterns successfully captured
**Performance:** 12-18 seconds per screener fetch
**Reliability:** CSV download with HTML scraping fallback
