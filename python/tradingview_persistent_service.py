#!/usr/bin/env python3
"""
TradingView Persistent Screener Service
Maintains browser session for ultra-fast screener data fetching (2-3 seconds)
Now with dynamic configuration from Supabase controls table
"""

import asyncio
import json
import os
import sys
import time
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
import aiohttp
from aiohttp import web
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import subprocess
import logging

# Add the parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screener_config_manager import get_config_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradingViewPersistentSession:
    """Persistent browser session for TradingView screener data"""
    
    def __init__(self):
        self.driver = None
        self.download_dir = None
        self.cookies_path = None
        self.session_start_time = None
        self.request_count = 0
        self.last_request_time = None
        # Dynamic configuration manager
        self.config_manager = get_config_manager()
        self.screener_urls = {}  # Will be populated from database
        self._load_screener_urls()
        self.index_mapping = {
            "NIFTY50": "NIFTY",
            "NIFTY": "NIFTY",
            "NIFTYBANK": "CNXBANK",
            "BANKNIFTY": "CNXBANK",
            "NIFTYIT": "CNXIT",
            "NIFTYMETAL": "CNXMETAL",
            "NIFTYPHARMA": "CNXPHARMA",
            "NIFTYAUTO": "CNXAUTO",
            "NIFTYFMCG": "CNXFMCG",
            "NIFTYENERGY": "CNXENERGY",
            "NIFTYINFRA": "CNXINFRA",
            "NIFTYMEDIA": "CNXMEDIA",
            "NIFTYMNC": "CNXMNC",
            "NIFTYPSUBANK": "CNXPSUBANK",
            "NIFTYREALTY": "CNXREALTY",
            "NIFTYCOMMODITIES": "CNXCOMMODITIES",
            "NIFTYCONSUMPTION": "CNXCONSUMPTION",
            "NIFTYSERVICES": "CNXSERVICES",
            "NIFTYMIDCAP50": "CNXMIDCAP",
            "NIFTYSMALLCAP100": "CNXSMALLCAP",
            "NIFTYMIDCAP100": "CNXMID100",
            "NIFTYMIDCAP150": "CNXMID150",
            "NIFTYSMALLCAP50": "CNXSMALL50",
            "NIFTYSMALLCAP250": "CNXSMALL250"
        }
    
    def _load_screener_urls(self):
        """Load screener URLs from configuration manager"""
        try:
            configs = self.config_manager.fetch_active_screeners()
            self.screener_urls = {}
            for key, config in configs.items():
                if config.get('url'):
                    self.screener_urls[key] = config['url']
                    logger.info(f"Loaded screener '{key}': {config.get('original_name', key)}")
            
            if not self.screener_urls:
                logger.warning("No screener URLs loaded from database, using fallback")
                # Fallback to hardcoded URLs
                self.screener_urls = {
                    "btst": "https://www.tradingview.com/screener/0DOKyjG6/",
                    "swing": "https://www.tradingview.com/screener/mToYMbsV/", 
                    "position": "https://www.tradingview.com/screener/xERJ4xGd/"
                }
        except Exception as e:
            logger.error(f"Failed to load screener URLs: {e}")
            # Use fallback
            self.screener_urls = {
                "btst": "https://www.tradingview.com/screener/0DOKyjG6/",
                "swing": "https://www.tradingview.com/screener/mToYMbsV/", 
                "position": "https://www.tradingview.com/screener/xERJ4xGd/"
            }
    
    def refresh_screener_config(self):
        """Refresh screener configuration from database"""
        logger.info("Refreshing screener configuration from database")
        self.config_manager.refresh_configuration()
        self._load_screener_urls()
        return len(self.screener_urls)
        
    def _setup_virtual_display(self):
        """Setup virtual display for headless operation"""
        try:
            os.environ['DISPLAY'] = ':99'
            result = subprocess.run(['pgrep', 'Xvfb'], capture_output=True, text=True)
            if result.returncode != 0:
                subprocess.Popen(['Xvfb', ':99', '-screen', '0', '1920x1080x24'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(2)
                logger.info("Virtual display started")
            else:
                logger.info("Virtual display already running")
            return True
        except Exception as e:
            logger.warning(f"Virtual display setup failed: {e}")
            return False

    async def initialize(self):
        """Initialize browser session once"""
        try:
            # Setup virtual display
            self._setup_virtual_display()

            # Setup download directory
            self.download_dir = tempfile.mkdtemp(prefix="tv_screener_")
            logger.info(f"Created download directory: {self.download_dir}")

            # Find cookies.json
            self.cookies_path = self._find_cookies_file()

            # Configure Chrome options
            options = webdriver.ChromeOptions()
            prefs = {
                "download.default_directory": self.download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            }
            options.add_experimental_option("prefs", prefs)

            # Essential headless options
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-plugins")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--start-maximized")

            # Memory and performance optimizations
            options.add_argument("--memory-pressure-off")
            options.add_argument("--disable-background-timer-throttling")
            options.add_argument("--disable-backgrounding-occluded-windows")
            options.add_argument("--disable-renderer-backgrounding")
            options.add_argument("--disable-features=TranslateUI")
            options.add_argument("--disable-background-networking")

            # Security options
            options.add_argument("--disable-web-security")
            options.add_argument("--allow-running-insecure-content")
            options.add_argument("--ignore-certificate-errors")
            options.add_argument("--ignore-ssl-errors")
            options.add_argument("--ignore-certificate-errors-spki-list")

            # Anti-detection options
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)

            # Create driver with webdriver-manager
            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {
                'behavior': 'allow',
                'downloadPath': self.download_dir
            })
            
            # Load initial page and cookies
            self.driver.get("https://in.tradingview.com")
            await asyncio.sleep(2)
            
            # Load cookies
            if self.cookies_path and os.path.exists(self.cookies_path):
                with open(self.cookies_path, 'r') as f:
                    cookies_data = json.load(f)
                    # Handle both formats: direct list or {url, cookies} object
                    cookies = cookies_data if isinstance(cookies_data, list) else cookies_data.get('cookies', [])
                    
                    for cookie in cookies:
                        # Clean up cookie data for Selenium
                        cookie_dict = {
                            'name': cookie.get('name'),
                            'value': cookie.get('value'),
                            'domain': cookie.get('domain', '.tradingview.com'),
                            'path': cookie.get('path', '/')
                        }
                        
                        # Only add optional fields if they exist
                        if 'secure' in cookie:
                            cookie_dict['secure'] = cookie['secure']
                        if 'httpOnly' in cookie:
                            cookie_dict['httpOnly'] = cookie['httpOnly']
                        if 'expirationDate' in cookie:
                            cookie_dict['expiry'] = int(cookie['expirationDate'])
                        
                        # Filter out cookies with missing required fields
                        if cookie_dict['name'] and cookie_dict['value']:
                            try:
                                self.driver.add_cookie(cookie_dict)
                            except Exception as e:
                                logger.warning(f"Could not add cookie {cookie_dict.get('name')}: {e}")
            
            self.session_start_time = datetime.now()
            logger.info("Browser session initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            return False
    
    def _find_cookies_file(self):
        """Find cookies.json file"""
        possible_paths = [
            "cookies.json",
            "../cookies.json", 
            "../../cookies.json",
            "/root/cookies.json",
            "/root/dhan-data-mcp/cookies.json"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"Found cookies at: {path}")
                return path
        
        logger.warning("No cookies.json found, proceeding without authentication")
        return None
    
    async def fetch_screener_data(self, screener_type: str, index_filter: Optional[str] = None) -> Dict[str, Any]:
        """Fetch screener data - optimized for speed"""
        start_time = time.time()
        
        try:
            # Navigate to screener URL
            url = self.screener_urls.get(screener_type)
            if not url:
                return {"error": f"Invalid screener type: {screener_type}"}
            
            # Only navigate if we're not already on this screener
            current_url = self.driver.current_url
            if url not in current_url:
                self.driver.get(url)
                await asyncio.sleep(3)  # Wait for page load
            else:
                # Just refresh if we're already on this screener
                self.driver.refresh()
                await asyncio.sleep(2)
            
            # Apply index filter(s) if provided
            if index_filter:
                # Check if it's multiple indices (comma-separated)
                if isinstance(index_filter, str) and ',' in index_filter:
                    # Multiple indices
                    indices = [idx.strip() for idx in index_filter.split(',')]
                    index_codes = [self.index_mapping.get(idx.upper(), idx) for idx in indices]
                    success = await self._apply_multi_index_filter(index_codes)
                    if not success:
                        logger.warning(f"Could not apply multi-index filter: {indices}")
                else:
                    # Single index (backward compatible)
                    index_code = self.index_mapping.get(index_filter.upper(), index_filter)
                    success = await self._apply_index_filter_fast(index_code)
                    if not success:
                        logger.warning(f"Could not apply index filter: {index_filter}")

            # Download CSV data (includes candlestick patterns and all columns)
            data = await self._download_csv_data()

            # Fallback to HTML scraping if CSV download fails
            if not data:
                logger.warning("CSV download failed, falling back to HTML scraping")
                data = await self._scrape_table_data()
                if not data:
                    return {"error": "Failed to scrape data"}
            
            elapsed = time.time() - start_time
            self.request_count += 1
            self.last_request_time = datetime.now()
            
            return {
                "success": True,
                "data": data,
                "metadata": {
                    "screener_type": screener_type,
                    "index_filter": index_filter,
                    "fetch_time_seconds": round(elapsed, 2),
                    "timestamp": datetime.now().isoformat(),
                    "request_count": self.request_count
                }
            }
            
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return {"error": str(e)}
    
    async def _apply_multi_index_filter(self, index_codes: list) -> bool:
        """Apply multiple index filters sequentially without closing dialog"""
        try:
            if not index_codes:
                return True
            
            logger.info(f"Applying multiple index filters: {index_codes}")
            
            # Wait for page to load
            await asyncio.sleep(3)
            
            # Click on Index filter button ONCE
            try:
                index_button = WebDriverWait(self.driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Index')]"))
                )
                index_button.click()
                logger.info("Opened Index filter dialog")
                await asyncio.sleep(2)
            except TimeoutException:
                logger.error("Could not find Index button")
                return False
            
            # Select each index one by one
            successful_selections = []
            for index_code in index_codes:
                if await self._select_single_index_in_dialog(index_code):
                    successful_selections.append(index_code)
                    # Clear search box for next selection
                    await self._clear_search_box()
                    await asyncio.sleep(1)  # Small delay between selections
            
            # Close dialog by clicking outside or pressing ESC
            try:
                # Try pressing ESC
                from selenium.webdriver.common.keys import Keys
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except:
                # Fallback: click outside
                self.driver.find_element(By.TAG_NAME, "body").click()
            
            await asyncio.sleep(2)
            logger.info(f"Successfully selected {len(successful_selections)} indices: {successful_selections}")
            return len(successful_selections) > 0
            
        except Exception as e:
            logger.error(f"Error applying multi-index filter: {e}")
            return False
    
    async def _clear_search_box(self) -> bool:
        """Clear the search box in the dialog using the X button"""
        try:
            # Try to click the clear (X) button in the search box
            clear_button_selectors = [
                "//*[@id=':r10l:']/div/div/div[1]/div/div[1]/div[4]/span/span[3]/div/span/svg",
                "//svg[contains(@class, 'clear')]",
                "//button[contains(@aria-label, 'clear')]",
                "//span[contains(@class, 'clear')]//svg",
                "//div[contains(@class, 'search')]//svg"
            ]
            
            for selector in clear_button_selectors:
                try:
                    clear_button = self.driver.find_element(By.XPATH, selector)
                    if clear_button and clear_button.is_displayed():
                        clear_button.click()
                        logger.info("Clicked search clear button")
                        await asyncio.sleep(0.5)
                        return True
                except:
                    continue
            
            # Fallback: Try to clear the input field directly
            search_selectors = [
                "input[type='text']",
                "input[placeholder*='Search']", 
                "input[placeholder*='search']"
            ]
            
            for selector in search_selectors:
                try:
                    search_box = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if search_box and search_box.is_displayed():
                        # Select all and delete
                        from selenium.webdriver.common.keys import Keys
                        search_box.click()
                        search_box.send_keys(Keys.COMMAND + 'a' if 'darwin' in sys.platform else Keys.CONTROL + 'a')
                        search_box.send_keys(Keys.DELETE)
                        logger.info("Cleared search box using select-all and delete")
                        return True
                except:
                    continue
            
            logger.warning("Could not clear search box")
            return False
        except Exception as e:
            logger.error(f"Error clearing search box: {e}")
            return False
    
    async def _select_single_index_in_dialog(self, index_code: str) -> bool:
        """Select a single index within the already open dialog"""
        try:
            # Map index codes to search terms
            index_names = {
                'NIFTY': 'Nifty',
                'CNXBANK': 'Bank Nifty',
                'CNXIT': 'Nifty IT',
                'CNXAUTO': 'Nifty Auto',
                'CNXPHARMA': 'Nifty Pharma',
                'CNXFMCG': 'Nifty FMCG',
                'CNXMETAL': 'Nifty Metal',
                'CNXENERGY': 'Nifty Energy'
            }
            
            search_term = index_names.get(index_code, index_code)
            logger.info(f"Selecting index: {index_code} -> {search_term}")
            
            # Find search box within dialog
            search_selectors = [
                "input[type='text']",
                "input[placeholder*='Search']", 
                "input[placeholder*='search']",
                ".search-input"
            ]
            
            search_box = None
            for selector in search_selectors:
                try:
                    search_box = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if search_box and search_box.is_displayed():
                        break
                except TimeoutException:
                    continue
            
            if not search_box:
                logger.error("Could not find search box in dialog")
                return False
            
            # Type search term
            search_box.send_keys(search_term)
            await asyncio.sleep(1.5)
            
            # Look for the checkbox or clickable item
            # Based on your screenshot, items have checkboxes
            item_selectors = [
                f"//div[contains(text(), '{index_code}')]",
                f"//span[contains(text(), '{search_term}')]",
                f"//div[contains(text(), '{search_term}')]",
                f"//*[contains(text(), '{index_code}')]/..//input[@type='checkbox']"
            ]
            
            for selector in item_selectors:
                try:
                    element = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    element.click()
                    logger.info(f"Selected: {search_term}")
                    await asyncio.sleep(0.5)
                    return True
                except TimeoutException:
                    continue
            
            logger.error(f"Could not select index: {search_term}")
            return False
            
        except Exception as e:
            logger.error(f"Error selecting index {index_code}: {e}")
            return False
    
    async def _apply_index_filter_fast(self, index_code: str) -> bool:
        """Apply index filter using PROVEN working method from original"""
        try:
            # Index name mappings for search (from original working code)
            index_names = {
                'NIFTY': 'Nifty 50',
                'CNXBANK': 'Nifty Bank', 
                'CNXIT': 'Nifty IT',
                'CNX100': 'Nifty 100',
                'CNX200': 'Nifty 200',
                'CNXAUTO': 'Nifty Auto',
                'CNXPHARMA': 'Nifty Pharma',
                'CNXFMCG': 'Nifty FMCG',
                'CNXMETAL': 'Nifty Metal',
                'CNXENERGY': 'Nifty Energy'
            }
            
            search_term = index_names.get(index_code, index_code)
            logger.info(f"Applying index filter: {index_code} -> {search_term}")
            
            # Wait for page to load
            await asyncio.sleep(3)
            
            # Click on Index filter button (EXACT method from original)
            try:
                index_button = WebDriverWait(self.driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Index')]"))
                )
                index_button.click()
                logger.info("Clicked Index button")
                await asyncio.sleep(5)
            except TimeoutException:
                logger.error("Could not find Index button")
                return False
            
            # Find search box (EXACT method from original)
            try:
                search_selectors = [
                    "input[type='text']",
                    "input[placeholder*='Search']", 
                    "input[placeholder*='search']",
                    ".search-input",
                    "input"
                ]
                
                search_box = None
                for selector in search_selectors:
                    try:
                        search_box = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        break
                    except TimeoutException:
                        continue
                
                if search_box:
                    search_box.clear()
                    search_box.send_keys(search_term)
                    await asyncio.sleep(2)
                    
                    # Find and click the matching option (EXACT method from original)
                    exact_selectors = [
                        f"//*[text()='{search_term}']",
                        f"//span[text()='{search_term}']", 
                        f"//div[text()='{search_term}']"
                    ]
                    
                    for selector in exact_selectors:
                        try:
                            option = WebDriverWait(self.driver, 2).until(
                                EC.element_to_be_clickable((By.XPATH, selector))
                            )
                            option.click()
                            logger.info(f"Selected index: {search_term}")
                            await asyncio.sleep(2)
                            return True
                        except TimeoutException:
                            continue
                    
                    # Fallback: try contains selectors (from original)
                    contains_selectors = [
                        f"//*[contains(text(), '{search_term}')]",
                        f"//span[contains(text(), '{search_term}')]"
                    ]
                    
                    for selector in contains_selectors:
                        try:
                            options = self.driver.find_elements(By.XPATH, selector)
                            if options:
                                first_option = options[0]
                                if first_option.is_displayed() and first_option.is_enabled():
                                    first_option.click()
                                    logger.info(f"Selected index (fallback): {search_term}")
                                    await asyncio.sleep(2)
                                    return True
                        except Exception:
                            continue
                
                logger.error(f"Could not find or select index option: {search_term}")
                return False
                
            except Exception as e:
                logger.error(f"Error during index search and selection: {e}")
                return False
            
        except Exception as e:
            logger.error(f"Error applying index filter: {e}")
            return False

    async def _download_csv_data(self) -> Optional[list]:
        """Download CSV export and parse data - gets ALL columns including candlestick patterns"""
        try:
            # Clean up old CSV files first
            self._clean_old_csv_files()

            # Step 1: Click menu trigger to open export menu
            menu_trigger_xpath = "//*[@id='js-screener-container']/div[2]/div/div[1]/div[1]/div[1]/div/h2"
            try:
                menu_trigger = await asyncio.to_thread(
                    lambda: WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, menu_trigger_xpath))
                    )
                )
                self.driver.execute_script("arguments[0].scrollIntoView(true);", menu_trigger)
                await asyncio.sleep(0.5)
                menu_trigger.click()
                logger.info("Menu trigger clicked successfully")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Failed to click menu trigger: {e}")
                return None

            # Step 2: Click "Export screen results" button - simple text match
            try:
                export_button = await asyncio.to_thread(
                    lambda: WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Export screen results')]"))
                    )
                )
                export_button.click()
                logger.info("Export button clicked successfully")
            except Exception as e:
                logger.error(f"Failed to click export button: {e}")
                return None

            # Step 3: Wait for CSV download to complete
            await asyncio.sleep(2)  # Give download time to start

            downloaded_file = await self._wait_for_csv_download(timeout_seconds=15)
            if not downloaded_file:
                logger.error("CSV download failed or timed out")
                return None

            # Step 4: Parse CSV file
            import pandas as pd
            df = pd.read_csv(downloaded_file)

            # Convert to list of dictionaries
            data = df.to_dict('records')
            logger.info(f"Parsed {len(data)} rows from CSV with {len(df.columns)} columns")
            logger.info(f"Columns: {list(df.columns)[:10]}")

            return data

        except Exception as e:
            logger.error(f"CSV download failed: {e}")
            return None

    def _clean_old_csv_files(self):
        """Delete all existing CSV files in download directory"""
        try:
            if not os.path.exists(self.download_dir):
                return

            deleted_count = 0
            for filename in os.listdir(self.download_dir):
                if filename.lower().endswith('.csv'):
                    file_path = os.path.join(self.download_dir, filename)
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete {filename}: {e}")

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old CSV files")
        except Exception as e:
            logger.warning(f"Error cleaning old CSV files: {e}")

    async def _wait_for_csv_download(self, timeout_seconds: int = 15) -> Optional[str]:
        """Wait for CSV download to complete and return file path"""
        start_time = time.time()
        initial_files = set(os.listdir(self.download_dir))
        logger.info(f"Waiting for download in: {self.download_dir}")

        while time.time() - start_time < timeout_seconds:
            current_files = set(os.listdir(self.download_dir))
            new_files = current_files - initial_files

            # Filter for CSV files
            csv_files = [f for f in new_files if f.lower().endswith(".csv") and not f.startswith('.')]

            if csv_files:
                latest_csv = max(csv_files, key=lambda f: os.path.getmtime(os.path.join(self.download_dir, f)))
                latest_csv_path = os.path.join(self.download_dir, latest_csv)

                # Check if download is complete (no .crdownload file)
                base_name = os.path.splitext(latest_csv)[0]
                is_downloading = any(
                    f.startswith(base_name) and f.lower().endswith(".crdownload")
                    for f in os.listdir(self.download_dir)
                )

                if not is_downloading:
                    # Wait briefly for file to stabilize (2 checks)
                    await asyncio.sleep(1)
                    if os.path.exists(latest_csv_path):
                        size1 = os.path.getsize(latest_csv_path)
                        await asyncio.sleep(1)
                        if os.path.exists(latest_csv_path):
                            size2 = os.path.getsize(latest_csv_path)
                            if size1 == size2 and size1 > 0:
                                logger.info(f"Download complete: {latest_csv} ({size1} bytes)")
                                return latest_csv_path
                            elif size2 > 0:
                                # Size changed but file exists, give it one more second
                                await asyncio.sleep(1)
                                if os.path.exists(latest_csv_path):
                                    final_size = os.path.getsize(latest_csv_path)
                                    if final_size > 0:
                                        logger.info(f"Download complete (after wait): {latest_csv} ({final_size} bytes)")
                                        return latest_csv_path

            await asyncio.sleep(2)

        logger.error("Download timeout")
        return None

    async def _scrape_table_data(self) -> Optional[list]:
        """Scrape data directly from table - much faster and more reliable"""
        try:
            # Wait for table to load
            await asyncio.sleep(1)
            
            data = []
            
            # Try multiple table selectors
            table_selectors = [
                "table.tv-data-table tbody tr",  # Standard table
                "div[data-role='list'] div[data-role='row']",  # Modern list view
                ".tv-screener-table__result-row",  # Screener specific
                "tr.tv-screener-table__result-row",  # Alternative
                "tbody tr"  # Generic fallback
            ]
            
            rows = []
            for selector in table_selectors:
                try:
                    rows = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if rows:
                        logger.info(f"Found {len(rows)} rows using selector: {selector}")
                        break
                except:
                    continue
            
            if not rows:
                logger.warning("No table rows found with any selector")
                return []
            
            # Get header to understand columns
            headers = []
            try:
                header_cells = self.driver.find_elements(By.CSS_SELECTOR, "th, thead td, [data-role='columnheader']")
                headers = [cell.text.strip() for cell in header_cells if cell.text.strip()]
            except:
                # Default headers if we can't find them
                headers = ["Symbol", "Description", "Price", "Change%", "Volume", "Market Cap", "P/E", "EPS"]
            
            logger.info(f"Table headers: {headers[:8]}")
            
            # Extract data from each row
            for i, row in enumerate(rows[:100]):  # Limit to 100 rows for speed
                try:
                    # Get all cells in the row
                    cells = row.find_elements(By.CSS_SELECTOR, "td, div[data-role='cell'], .tv-screener-table__cell")
                    
                    if not cells:
                        continue
                    
                    # Extract symbol (usually first column or has specific class)
                    symbol = ""
                    try:
                        # Try to find symbol link
                        symbol_link = row.find_element(By.CSS_SELECTOR, "a[href*='/symbols/'], .tv-screener-table__symbol")
                        symbol = symbol_link.text.strip()
                    except:
                        # Fallback to first cell
                        if cells:
                            symbol = cells[0].text.strip()
                    
                    if not symbol:
                        continue
                    
                    # Build row data
                    row_data = {"Symbol": symbol}
                    
                    # Map remaining cells to headers
                    for j, cell in enumerate(cells[1:min(len(cells), len(headers))], 1):
                        try:
                            header = headers[j] if j < len(headers) else f"Column{j}"
                            value = cell.text.strip()
                            row_data[header] = value
                        except:
                            continue
                    
                    data.append(row_data)
                    
                except Exception as e:
                    logger.debug(f"Error processing row {i}: {e}")
                    continue
            
            logger.info(f"Scraped {len(data)} rows from table")
            return data
            
        except Exception as e:
            logger.error(f"Error scraping table: {e}")
            return None
    
    async def _export_data_fast(self, screener_type: str) -> Optional[str]:
        """Export data - optimized version"""
        try:
            # Try the menu trigger approach first (most reliable)
            menu_trigger_xpath = "//*[@id='js-screener-container']/div[2]/div/div[1]/div[1]/div[1]/div/h2"
            
            try:
                menu_trigger = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, menu_trigger_xpath))
                )
                self.driver.execute_script("arguments[0].click();", menu_trigger)
                await asyncio.sleep(1)
                
                # Find and click export option
                export_xpath = "//div[contains(text(), 'Export screen results')]/.."
                export_button = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, export_xpath))
                )
                self.driver.execute_script("arguments[0].click();", export_button)
                
            except TimeoutException:
                # Fallback: Try direct export button
                export_button = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-name='screener-export-button']"))
                )
                self.driver.execute_script("arguments[0].click();", export_button)
                await asyncio.sleep(0.5)
                
                # Click export to CSV
                csv_option = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Export to CSV')]"))
                )
                self.driver.execute_script("arguments[0].click();", csv_option)
            
            # Wait for download - reduced timeout
            max_wait = 5
            start = time.time()
            
            while time.time() - start < max_wait:
                csv_files = list(Path(self.download_dir).glob("*.csv"))
                if csv_files and csv_files[0].stat().st_size > 0:
                    return str(csv_files[0])
                await asyncio.sleep(0.2)
            
            return None
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return None
    
    def _csv_to_json(self, csv_file: str) -> list:
        """Convert CSV to JSON - using proven working method"""
        import csv
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as csvfile:
                # Auto-detect delimiter
                sample = csvfile.read(1024)
                csvfile.seek(0)
                
                delimiter = ','
                try:
                    sniffer = csv.Sniffer()
                    delimiter = sniffer.sniff(sample).delimiter
                except:
                    delimiter = ','
                
                reader = csv.DictReader(csvfile, delimiter=delimiter)
                data = [row for row in reader]
                
                logger.info(f"Converted CSV to JSON: {len(data)} records")
                return data
                
        except Exception as e:
            logger.error(f"Error converting CSV to JSON: {e}")
            return []
    
    async def get_status(self) -> Dict[str, Any]:
        """Get service status"""
        return {
            "status": "running" if self.driver else "stopped",
            "session_uptime_minutes": (
                round((datetime.now() - self.session_start_time).total_seconds() / 60, 2)
                if self.session_start_time else 0
            ),
            "request_count": self.request_count,
            "last_request": self.last_request_time.isoformat() if self.last_request_time else None,
            "browser_alive": self._check_browser_alive()
        }
    
    def _check_browser_alive(self) -> bool:
        """Check if browser is responsive"""
        try:
            self.driver.title
            return True
        except:
            return False
    
    async def restart_browser(self):
        """Restart browser session"""
        logger.info("Restarting browser session...")
        await self.cleanup()
        await asyncio.sleep(1)
        return await self.initialize()
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        
        if self.download_dir and os.path.exists(self.download_dir):
            try:
                shutil.rmtree(self.download_dir)
            except:
                pass

# HTTP API Server
class ScreenerAPIServer:
    """HTTP API server for screener service"""
    
    def __init__(self, session: TradingViewPersistentSession):
        self.session = session
        self.app = web.Application()
        self.setup_routes()
    
    def setup_routes(self):
        """Setup API routes"""
        self.app.router.add_post('/fetch', self.handle_fetch)
        self.app.router.add_get('/status', self.handle_status)
        self.app.router.add_post('/restart', self.handle_restart)
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_post('/refresh_config', self.handle_refresh_config)
        self.app.router.add_get('/config', self.handle_get_config)
    
    async def handle_fetch(self, request):
        """Handle fetch request"""
        try:
            data = await request.json()
            screener_type = data.get('screener_type', 'btst')
            index_filter = data.get('index_filter')
            
            result = await self.session.fetch_screener_data(screener_type, index_filter)
            return web.json_response(result)
            
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_status(self, request):
        """Handle status request"""
        status = await self.session.get_status()
        return web.json_response(status)
    
    async def handle_restart(self, request):
        """Handle restart request"""
        success = await self.session.restart_browser()
        return web.json_response({"success": success})
    
    async def handle_health(self, request):
        """Health check endpoint"""
        return web.json_response({"status": "healthy"})
    
    async def handle_refresh_config(self, request):
        """Refresh screener configuration from database"""
        try:
            count = self.session.refresh_screener_config()
            return web.json_response({
                "status": "success",
                "message": f"Refreshed {count} screener configurations",
                "screeners": list(self.session.screener_urls.keys())
            })
        except Exception as e:
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    async def handle_get_config(self, request):
        """Get current screener configuration"""
        try:
            configs = self.session.config_manager.list_available_screeners()
            cache_status = self.session.config_manager.get_cache_status()
            return web.json_response({
                "status": "success",
                "screeners": configs,
                "cache": cache_status,
                "active_count": len(configs)
            })
        except Exception as e:
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

async def main():
    """Main entry point"""
    logger.info("Starting TradingView Persistent Screener Service...")
    
    # Create session
    session = TradingViewPersistentSession()
    
    # Initialize browser
    if not await session.initialize():
        logger.error("Failed to initialize browser session")
        return
    
    # Create API server
    server = ScreenerAPIServer(session)
    
    # Start server
    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8765)
    await site.start()
    
    logger.info("Service running on http://localhost:8765")
    logger.info("Endpoints:")
    logger.info("  POST /fetch - Fetch screener data")
    logger.info("  GET /status - Get service status")
    logger.info("  POST /restart - Restart browser session")
    logger.info("  GET /health - Health check")
    logger.info("  POST /refresh_config - Refresh screener configuration")
    logger.info("  GET /config - Get current configuration")
    
    try:
        # Keep running
        while True:
            await asyncio.sleep(60)
            # Periodic health check
            if not session._check_browser_alive():
                logger.warning("Browser unresponsive, restarting...")
                await session.restart_browser()
    
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    
    finally:
        await session.cleanup()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())