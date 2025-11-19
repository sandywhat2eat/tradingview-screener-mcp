#!/usr/bin/env python3
"""
TradingView Screener Handler - MCP Integration
Uses HTTP client to communicate with persistent screener service for 2-3 second response times
Now with dynamic configuration from Supabase controls table
"""

import json
import sys
import argparse
import requests
import subprocess
import time
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

# Add for configuration management
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screener_config_manager import get_config_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradingViewScreenerClient:
    """HTTP client for persistent screener service"""
    
    def __init__(self, service_url: str = "http://localhost:8765"):
        self.service_url = service_url
        self.session = requests.Session()
        self._ensure_service_running()
    
    def _ensure_service_running(self):
        """Ensure the persistent service is running"""
        try:
            # Check if service is healthy
            response = self.session.get(f"{self.service_url}/health", timeout=1)
            if response.status_code == 200:
                logger.info("Persistent service is running")
                return
        except requests.exceptions.RequestException:
            pass
        
        # Service not running, start it
        logger.info("Starting persistent screener service...")

        # Start service in background with environment variables
        service_script = os.path.join(os.path.dirname(__file__), "tradingview_persistent_service.py")
        env = os.environ.copy()
        # Load .env file for service
        from dotenv import load_dotenv
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(project_root, '.env'))
        env.update(os.environ)

        subprocess.Popen(
            [sys.executable, service_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env
        )
        
        # Wait for service to be ready
        max_wait = 15
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                response = self.session.get(f"{self.service_url}/health", timeout=1)
                if response.status_code == 200:
                    logger.info("Service started successfully")
                    time.sleep(2)  # Give it a moment to fully initialize
                    return
            except requests.exceptions.RequestException:
                time.sleep(0.5)
        
        raise RuntimeError("Failed to start persistent screener service")
    
    def fetch_screener_data(self, screener_type: str, index_filter: Optional[str] = None) -> Dict[str, Any]:
        """Fetch screener data from persistent service"""
        try:
            start_time = time.time()
            
            # Make request to service
            response = self.session.post(
                f"{self.service_url}/fetch",
                json={
                    "screener_type": screener_type,
                    "index_filter": index_filter
                },
                timeout=60
            )
            
            if response.status_code != 200:
                return {"error": f"Service returned status {response.status_code}"}
            
            result = response.json()
            
            # Add client-side timing
            elapsed = time.time() - start_time
            if "metadata" in result:
                result["metadata"]["total_time_seconds"] = round(elapsed, 2)
            
            return result
            
        except requests.exceptions.Timeout:
            return {"error": "Request timed out"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Request failed: {str(e)}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get service status"""
        try:
            response = self.session.get(f"{self.service_url}/status", timeout=2)
            return response.json()
        except Exception as e:
            return {"error": str(e), "status": "unreachable"}
    
    def restart_service(self) -> Dict[str, Any]:
        """Restart the browser session in service"""
        try:
            response = self.session.post(f"{self.service_url}/restart", timeout=5)
            return response.json()
        except Exception as e:
            return {"error": str(e)}

# MCP Tool Handlers
def handle_fetch_screener_data(args):
    """Handle fetch_screener_data tool call"""
    try:
        client = TradingViewScreenerClient()
        return client.fetch_screener_data(
            screener_type=args.screener_type,
            index_filter=args.index_filter
        )
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        return {"error": str(e)}

def handle_list_screener_types(args):
    """List available screener types from database"""
    try:
        # Get configuration manager
        config_manager = get_config_manager()
        
        # Fetch available screeners from database
        screeners = config_manager.list_available_screeners()
        
        # Format for MCP response
        screener_types = []
        for screener in screeners:
            screener_types.append({
                "type": screener['type'],
                "name": screener['name'],
                "description": screener['description'],
                "holding_period": screener.get('holding_period', 'unknown'),
                "trade_type": screener.get('trade_type', 'LONG'),
                "enabled": screener.get('enabled', True)
            })
        
        # Add cache status for debugging
        cache_status = config_manager.get_cache_status()
        
        return {
            "screener_types": screener_types,
            "total_count": len(screener_types),
            "source": "database",
            "cache_status": cache_status
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch screener types from database: {e}")
        # Fallback to hardcoded values
        return {
            "screener_types": [
                {
                    "type": "btst",
                    "name": "BTST/STBT",
                    "description": "Buy Today Sell Tomorrow - Short-term momentum trades for next day exit",
                    "holding_period": "BTST",
                    "trade_type": "LONG",
                    "enabled": True
                },
                {
                    "type": "swing",
                    "name": "Swing Trading",
                    "description": "Good for swing trading - Medium-term positional trades (2-10 days)",
                    "holding_period": "swing",
                    "trade_type": "LONG",
                    "enabled": True
                },
                {
                    "type": "position",
                    "name": "Positional Trading",
                    "description": "Good for positional trading - Long-term trades (weeks to months)",
                    "holding_period": "positional",
                    "trade_type": "both",
                    "enabled": True
                }
            ],
            "source": "fallback",
            "error": str(e)
        }

def handle_list_screener_indices(args):
    """List available index filters"""
    indices = [
        {"code": "NIFTY50", "name": "Nifty 50", "description": "Top 50 large-cap stocks"},
        {"code": "NIFTYBANK", "name": "Bank Nifty", "description": "Banking sector stocks"},
        {"code": "NIFTYIT", "name": "Nifty IT", "description": "Information Technology sector"},
        {"code": "NIFTYMETAL", "name": "Nifty Metal", "description": "Metal and mining sector"},
        {"code": "NIFTYPHARMA", "name": "Nifty Pharma", "description": "Pharmaceutical sector"},
        {"code": "NIFTYAUTO", "name": "Nifty Auto", "description": "Automobile sector"},
        {"code": "NIFTYFMCG", "name": "Nifty FMCG", "description": "Fast Moving Consumer Goods"},
        {"code": "NIFTYENERGY", "name": "Nifty Energy", "description": "Energy sector stocks"},
        {"code": "NIFTYINFRA", "name": "Nifty Infrastructure", "description": "Infrastructure sector"},
        {"code": "NIFTYMEDIA", "name": "Nifty Media", "description": "Media and entertainment"},
        {"code": "NIFTYMNC", "name": "Nifty MNC", "description": "Multinational companies"},
        {"code": "NIFTYPSUBANK", "name": "Nifty PSU Bank", "description": "Public sector banks"},
        {"code": "NIFTYREALTY", "name": "Nifty Realty", "description": "Real estate sector"},
        {"code": "NIFTYCOMMODITIES", "name": "Nifty Commodities", "description": "Commodity sector"},
        {"code": "NIFTYCONSUMPTION", "name": "Nifty Consumption", "description": "Consumption theme"},
        {"code": "NIFTYSERVICES", "name": "Nifty Services", "description": "Services sector"},
        {"code": "NIFTYMIDCAP50", "name": "Nifty Midcap 50", "description": "Top 50 mid-cap stocks"},
        {"code": "NIFTYSMALLCAP100", "name": "Nifty Smallcap 100", "description": "Top 100 small-cap stocks"},
        {"code": "NIFTYMIDCAP100", "name": "Nifty Midcap 100", "description": "Top 100 mid-cap stocks"},
        {"code": "NIFTYMIDCAP150", "name": "Nifty Midcap 150", "description": "Top 150 mid-cap stocks"},
        {"code": "NIFTYSMALLCAP50", "name": "Nifty Smallcap 50", "description": "Top 50 small-cap stocks"},
        {"code": "NIFTYSMALLCAP250", "name": "Nifty Smallcap 250", "description": "Top 250 small-cap stocks"}
    ]
    return {"indices": indices}

def handle_get_screener_session_health(args):
    """Get session health status"""
    try:
        client = TradingViewScreenerClient()
        return client.get_service_status()
    except Exception as e:
        return {"error": str(e), "status": "service_error"}

def handle_refresh_screener_session(args):
    """Refresh the browser session"""
    try:
        client = TradingViewScreenerClient()
        return client.restart_service()
    except Exception as e:
        return {"error": str(e)}

def handle_refresh_screener_config(args):
    """Refresh screener configuration from database"""
    try:
        # Refresh local configuration
        config_manager = get_config_manager()
        configs = config_manager.refresh_configuration()
        
        # Also refresh in the persistent service
        client = TradingViewScreenerClient()
        response = client.session.post(f"{client.service_url}/refresh_config", timeout=5)
        service_result = response.json() if response.status_code == 200 else {"error": "Failed to refresh service"}
        
        return {
            "status": "success",
            "local_configs": len(configs),
            "service_refresh": service_result,
            "screeners": list(configs.keys())
        }
    except Exception as e:
        logger.error(f"Config refresh failed: {e}")
        return {"error": str(e)}

def handle_get_screener_config(args):
    """Get current screener configuration"""
    try:
        config_manager = get_config_manager()
        screeners = config_manager.list_available_screeners()
        cache_status = config_manager.get_cache_status()
        
        return {
            "status": "success",
            "screeners": screeners,
            "cache": cache_status,
            "total_count": len(screeners)
        }
    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        return {"error": str(e)}

def main():
    """Main entry point for MCP tool calls"""
    parser = argparse.ArgumentParser(description='TradingView Screener Handler')
    parser.add_argument('--screener_type', type=str, help='Screener type (btst/swing/position)')
    parser.add_argument('--index_filter', type=str, help='Optional index filter')
    parser.add_argument('tool', type=str, help='Tool to execute')
    
    args = parser.parse_args()
    
    # Route to appropriate handler
    handlers = {
        'handle_fetch_screener_data': handle_fetch_screener_data,
        'handle_list_screener_types': handle_list_screener_types,
        'handle_list_screener_indices': handle_list_screener_indices,
        'handle_get_screener_session_health': handle_get_screener_session_health,
        'handle_refresh_screener_session': handle_refresh_screener_session,
        'handle_refresh_screener_config': handle_refresh_screener_config,
        'handle_get_screener_config': handle_get_screener_config
    }
    
    handler = handlers.get(args.tool)
    if not handler:
        result = {"error": f"Unknown tool: {args.tool}"}
    else:
        result = handler(args)
    
    # Output result
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()