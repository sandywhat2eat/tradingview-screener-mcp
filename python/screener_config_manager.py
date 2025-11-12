#!/usr/bin/env python3
"""
Screener Configuration Manager
Fetches and manages TradingView screener configurations from Supabase controls table
"""

import os
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScreenerConfigManager:
    """Manages dynamic screener configurations from Supabase"""
    
    def __init__(self, cache_ttl_minutes: int = 5):
        """Initialize configuration manager with caching
        
        Args:
            cache_ttl_minutes: Cache time-to-live in minutes (default: 5)
        """
        # Load environment variables
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        load_dotenv(os.path.join(project_root, '.env'))
        
        # Initialize Supabase client
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_ANON_KEY')
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment")
        
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
        # Cache configuration
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._config_cache = None
        self._cache_timestamp = None
        self._fallback_config = None
        
        # Strategy name normalization mapping
        self.strategy_mapping = {
            'BTST_STBT': 'btst',
            'BTST': 'btst',
            'Swing': 'swing',
            'swing': 'swing',
            'position_montly': 'position',
            'position_monthly': 'position',
            'position': 'position',
            'positional': 'position'
        }
    
    def _normalize_strategy_name(self, strategy: str) -> str:
        """Normalize strategy name to consistent format
        
        Args:
            strategy: Raw strategy name from database
            
        Returns:
            Normalized strategy identifier
        """
        # First check if there's a mapping
        normalized = self.strategy_mapping.get(strategy)
        if normalized:
            return normalized
        
        # Otherwise, convert to lowercase and replace spaces/special chars
        return strategy.lower().replace(' ', '_').replace('-', '_')
    
    def fetch_active_screeners(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch active screener configurations from database
        
        Args:
            force_refresh: Force refresh even if cache is valid
            
        Returns:
            Dictionary of screener configurations keyed by normalized strategy name
        """
        # Check cache validity
        if not force_refresh and self._config_cache and self._cache_timestamp:
            if datetime.now() - self._cache_timestamp < self.cache_ttl:
                logger.info("Using cached screener configurations")
                return self._config_cache
        
        try:
            # Fetch from Supabase
            logger.info("Fetching screener configurations from database")
            response = self.supabase.table('controls').select(
                'strategy, url, description, on_off, holding_period, tradetype, '
                'instrument_type, max_positions'
            ).eq('on_off', 'ON').execute()
            
            if not response.data:
                logger.warning("No active screeners found in database")
                return self._use_fallback_config()
            
            # Process configurations
            config = {}
            for screener in response.data:
                # Normalize strategy name for use as key
                normalized_name = self._normalize_strategy_name(screener['strategy'])
                
                config[normalized_name] = {
                    'original_name': screener['strategy'],
                    'url': screener['url'],
                    'description': screener.get('description', ''),
                    'holding_period': screener.get('holding_period', 'unknown'),
                    'trade_type': screener.get('tradetype', 'LONG'),
                    'instrument_type': screener.get('instrument_type', 'EQ'),
                    'max_positions': screener.get('max_positions'),
                    'enabled': True
                }
            
            # Update cache
            self._config_cache = config
            self._cache_timestamp = datetime.now()
            self._fallback_config = config  # Save as fallback
            
            logger.info(f"Loaded {len(config)} active screener configurations")
            return config
            
        except Exception as e:
            logger.error(f"Failed to fetch screener configurations: {e}")
            return self._use_fallback_config()
    
    def _use_fallback_config(self) -> Dict[str, Any]:
        """Use fallback configuration if database is unavailable
        
        Returns:
            Fallback configuration or hardcoded defaults
        """
        if self._fallback_config:
            logger.info("Using fallback screener configuration")
            return self._fallback_config
        
        # Hardcoded fallback for critical screeners
        logger.warning("Using hardcoded fallback screener configuration")
        return {
            'btst': {
                'original_name': 'BTST_STBT',
                'url': 'https://www.tradingview.com/screener/0DOKyjG6/',
                'description': 'Buy Today Sell Tomorrow - Short-term momentum trades',
                'holding_period': 'BTST',
                'trade_type': 'LONG',
                'enabled': True
            },
            'swing': {
                'original_name': 'Swing',
                'url': 'https://www.tradingview.com/screener/mToYMbsV/',
                'description': 'Swing trading - Medium-term trades (2-10 days)',
                'holding_period': 'swing',
                'trade_type': 'LONG',
                'enabled': True
            },
            'position': {
                'original_name': 'position_montly',
                'url': 'https://www.tradingview.com/screener/xERJ4xGd/',
                'description': 'Position trading - Long-term trades (weeks to months)',
                'holding_period': 'positional',
                'trade_type': 'both',
                'enabled': True
            }
        }
    
    def get_screener_by_type(self, screener_type: str) -> Optional[Dict[str, Any]]:
        """Get specific screener configuration by type
        
        Args:
            screener_type: Screener type identifier
            
        Returns:
            Screener configuration or None if not found
        """
        configs = self.fetch_active_screeners()
        
        # Try direct lookup
        if screener_type in configs:
            return configs[screener_type]
        
        # Try normalized lookup
        normalized = self._normalize_strategy_name(screener_type)
        if normalized in configs:
            return configs[normalized]
        
        # Try to find by original name
        for key, config in configs.items():
            if config.get('original_name', '').lower() == screener_type.lower():
                return config
        
        return None
    
    def get_screener_url(self, screener_type: str) -> Optional[str]:
        """Get screener URL by type
        
        Args:
            screener_type: Screener type identifier
            
        Returns:
            Screener URL or None if not found
        """
        config = self.get_screener_by_type(screener_type)
        return config['url'] if config else None
    
    def list_available_screeners(self) -> List[Dict[str, Any]]:
        """List all available screener configurations
        
        Returns:
            List of screener configurations with metadata
        """
        configs = self.fetch_active_screeners()
        
        screeners = []
        for key, config in configs.items():
            screeners.append({
                'type': key,
                'name': config['original_name'],
                'description': config['description'],
                'url': config['url'],
                'holding_period': config.get('holding_period', 'unknown'),
                'trade_type': config.get('trade_type', 'LONG'),
                'enabled': config.get('enabled', True)
            })
        
        return screeners
    
    def refresh_configuration(self) -> Dict[str, Any]:
        """Force refresh configuration from database
        
        Returns:
            Updated configuration
        """
        logger.info("Force refreshing screener configurations")
        return self.fetch_active_screeners(force_refresh=True)
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get cache status information
        
        Returns:
            Cache status details
        """
        if not self._cache_timestamp:
            return {
                'cached': False,
                'message': 'No configuration cached'
            }
        
        age = datetime.now() - self._cache_timestamp
        expires_in = self.cache_ttl - age
        
        return {
            'cached': True,
            'cache_age_seconds': int(age.total_seconds()),
            'expires_in_seconds': int(max(0, expires_in.total_seconds())),
            'config_count': len(self._config_cache) if self._config_cache else 0,
            'cache_timestamp': self._cache_timestamp.isoformat()
        }

# Singleton instance for module-level access
_config_manager = None

def get_config_manager() -> ScreenerConfigManager:
    """Get or create singleton configuration manager
    
    Returns:
        ScreenerConfigManager instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ScreenerConfigManager()
    return _config_manager

# Convenience functions for direct access
def get_screener_url(screener_type: str) -> Optional[str]:
    """Get screener URL by type"""
    return get_config_manager().get_screener_url(screener_type)

def list_screeners() -> List[Dict[str, Any]]:
    """List all available screeners"""
    return get_config_manager().list_available_screeners()

def refresh_configs() -> Dict[str, Any]:
    """Force refresh configurations"""
    return get_config_manager().refresh_configuration()

if __name__ == "__main__":
    # Test the configuration manager
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Screener Configuration Manager')
    parser.add_argument('--list', action='store_true', help='List available screeners')
    parser.add_argument('--get', type=str, help='Get specific screener configuration')
    parser.add_argument('--refresh', action='store_true', help='Force refresh configurations')
    parser.add_argument('--status', action='store_true', help='Get cache status')
    
    args = parser.parse_args()
    
    manager = get_config_manager()
    
    if args.list:
        screeners = manager.list_available_screeners()
        print(json.dumps(screeners, indent=2))
    elif args.get:
        config = manager.get_screener_by_type(args.get)
        if config:
            print(json.dumps(config, indent=2))
        else:
            print(f"Screener '{args.get}' not found")
            sys.exit(1)
    elif args.refresh:
        configs = manager.refresh_configuration()
        print(f"Refreshed {len(configs)} screener configurations")
        print(json.dumps(list(configs.keys()), indent=2))
    elif args.status:
        status = manager.get_cache_status()
        print(json.dumps(status, indent=2))
    else:
        # Default: list available screeners
        screeners = manager.list_available_screeners()
        print("Available Screeners:")
        for s in screeners:
            print(f"  - {s['type']}: {s['name']} - {s['description']}")