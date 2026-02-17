import re
import logging
import time
import random
import cloudscraper
from bs4 import BeautifulSoup

# Base URL for APKMirror
APKMIRROR_BASE = "https://www.apkmirror.com"

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

def create_scraper_session(proxy_url=None):
    """Create a cloudscraper session with browser-like headers and optional proxy."""
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.apkmirror.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    })
    if proxy_url:
        scraper.proxies = {"http": proxy_url, "https": proxy_url}
    return scraper

def get_download_link(version: str, app_name: str, config: dict, arch: str = None, scraper=None) -> str:
    """Fetch the direct download URL for the specified app version and architecture."""
    if scraper is None:
        scraper = create_scraper_session()
    
    target_arch = arch if arch else config.get('arch', 'universal')
    criteria = [config['type'], target_arch, config['dpi']]
    
    # --- UNIVERSAL URL FINDER WITH VALIDATION ---
    version_parts = version.split('.')
    found_soup = None
    correct_version_page = False
    
    # Use release_prefix if available, otherwise use app name
    release_name = config.get('release_prefix', config['name'])
    
    # Loop backwards: Try full version, then strip parts
    for i in range(len(version_parts), 0, -1):
        current_ver_str = "-".join(version_parts[:i])
        
        # Generate ALL possible URL patterns in priority order
        url_patterns = []
        
        # Priority 1: With release_name and -release suffix (most specific)
        url_patterns.append(f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{release_name}-{current_ver_str}-release/")
        
        # Priority 2: With app name and -release suffix
        if release_name != config['name']:
            url_patterns.append(f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{config['name']}-{current_ver_str}-release/")
        
        # Priority 3: With release_name without -release
        url_patterns.append(f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{release_name}-{current_ver_str}/")
        
        # Priority 4: With app name without -release
        if release_name != config['name']:
            url_patterns.append(f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{config['name']}-{current_ver_str}/")
        
        # Remove duplicate patterns
        url_patterns = list(dict.fromkeys(url_patterns))
        
        for url in url_patterns:
            logging.info(f"Checking potential release URL: {url}")
            
            # Add randomized delay to avoid rate-limiting
            time.sleep(1 + random.random())  # 1-2 seconds
            
            try:
                response = scraper.get(url)
                response.encoding = 'utf-8'  # Force UTF-8 encoding
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")  # Use response.text for proper decoding
                    page_text = soup.get_text()
                    
                    # VALIDATION: Check if this page is for our EXACT version
                    # Prioritize full version matches
                    full_version_checks = [version, version.replace('.', '-')]
                    
                    # Also check page title and headings for version
                    title_tag = soup.find('title')
                    headings = soup.find_all(['h1', 'h2', 'h3'])
                    
                    title_text = title_tag.get_text() if title_tag else ""
                    
                    # Stricter check: Require full version in title or headings
                    is_correct_page = any(
                        any(check in src for check in full_version_checks)
                        for src in [title_text] + [h.get_text() for h in headings]
                    )
                    
                    # Fallback to partial if no full match, but log
                    if not is_correct_page:
                        partial_checks = [current_ver_str, ".".join(version_parts[:i])]
                        is_correct_page = any(
                            any(check in src for check in partial_checks if check)
                            for src in [page_text, title_text] + [h.get_text() for h in headings]
                        )
                        if is_correct_page:
                            logging.warning("Fallback to partial version match")
                    
                    if is_correct_page:
                        content_size = len(response.content)
                        logging.info(f"✓ Correct version page found: {response.url}")
                        found_soup = soup
                        correct_version_page = True
                        break # Found correct page!
                    else:
                        # Page exists but doesn't have our version as primary
                        logging.warning(f"Page found but not for version {version}: {url}")
                        # Save as fallback ONLY if we haven't found any page yet
                        if found_soup is None:
                            found_soup = soup
                            logging.warning(f"Saved as fallback page (may list multiple versions)")
                        continue
                        
                elif response.status_code == 404:
                    continue
                else:
                    logging.warning(f"URL {url} returned status {response.status_code}")
                    continue
                    
            except Exception as e:
                logging.warning(f"Error checking {url}: {str(e)[:50]}")
                continue
        
        if correct_version_page:
            break # Found correct page for this version part
    
    # If we didn't find the exact version page but found a fallback
    if not correct_version_page and found_soup:
        logging.warning(f"Using fallback page for {app_name} {version} (may contain multiple versions)")
    
    if not found_soup:
        logging.error(f"Could not find any release page for {app_name} {version}")
        return None
    
    # --- VARIANT FINDER (works with both exact pages and fallback pages) ---
    rows = found_soup.find_all('div', class_='table-row')[1:] # Skip header row
    download_page_url = None
    
    # Try to find exact version match first
    for row in rows:
        row_text = row.get_text().strip()
        
        # Check if row contains our exact version
        if version in row_text or version.replace('.', '-') in row_text:
            # Check criteria
            if all(criterion in row_text for criterion in criteria):
                sub_url = row.find('a', class_='accent_color')
                if sub_url:
                    download_page_url = APKMIRROR_BASE + sub_url['href']
                    break
    
    # If exact version not found, try to find any variant matching criteria
    if not download_page_url:
        for row in rows:
            row_text = row.get_text().strip()
            if all(criterion in row_text for criterion in criteria):
                # Check if this looks like a variant row (has version numbers)
                if re.search(r'\d+(\.\d+)+', row_text):
                    sub_url = row.find('a', class_='accent_color')
                    if sub_url:
                        download_page_url = APKMIRROR_BASE + sub_url['href']
                        # Extract version for logging
                        match = re.search(r'(\d+(\.\d+)+(\.\w+)*)', row_text)
                        if match:
                            actual_version = match.group(1)
                            logging.warning(f"Using variant {actual_version} (criteria match)")
                        break
    
    if not download_page_url:
        logging.error(f"No variant found for {app_name} {version} with criteria {criteria}")
        # Debug: log what rows we found
        logging.debug(f"Found {len(rows)} rows total")
        for idx, row in enumerate(rows[:5]): # First 5 rows
            logging.debug(f"Row {idx}: {row.get_text()[:100]}...")
        return None
    
    # --- STANDARD DOWNLOAD FLOW ---
    try:
        # Add delay before next request
        time.sleep(1 + random.random())
        
        response = scraper.get(download_page_url)
        response.encoding = 'utf-8'
        response.raise_for_status()
        content_size = len(response.content)
        logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> Variant Page")
        soup = BeautifulSoup(response.text, "html.parser")
        sub_url = soup.find('a', class_='downloadButton')
        if sub_url:
            final_download_page_url = APKMIRROR_BASE + sub_url['href']
            
            # Add delay before final request
            time.sleep(1 + random.random())
            
            response = scraper.get(final_download_page_url)
            response.encoding = 'utf-8'
            response.raise_for_status()
            content_size = len(response.content)
            logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> Download Page")
            soup = BeautifulSoup(response.text, "html.parser")
            button = soup.find('a', id='download-link')
            if not button:
                button = soup.find('a', href=lambda h: h and 'download/' in h and 'forcebaseapk' in h)
            if button:
                return APKMIRROR_BASE + button['href']
    except Exception as e:
        logging.error(f"Error in download flow: {e}")
    
    return None

def get_architecture_criteria(arch: str) -> dict:
    """Map architecture names to APKMirror criteria"""
    arch_mapping = {
        "arm64-v8a": "arm64-v8a",
        "armeabi-v7a": "armeabi-v7a",
        "universal": "universal"
    }
    return arch_mapping.get(arch, "universal")

def get_latest_version(app_name: str, config: dict, scraper=None) -> str:
    """Retrieve the latest stable version for the app, skipping alphas/betas."""
    if scraper is None:
        scraper = create_scraper_session()
    
    # First try: get from main app page
    try:
        main_url = f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/"
        
        # Add delay
        time.sleep(1 + random.random())
        
        response = scraper.get(main_url)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            # Try to find version in the page
            version_elem = soup.find('span', string=re.compile(r'\d+\.\d+'))
            if version_elem:
                version_text = version_elem.text.strip()
                match = re.search(r'(\d+(\.\d+)+)', version_text)
                if match:
                    return match.group(1)
    except:
        pass # If fails, continue to original method
    
    # Original method (keep exactly as you had it)
    url = f"{APKMIRROR_BASE}/uploads/?appcategory={config['name']}"
    
    # Add delay
    time.sleep(1 + random.random())
    
    response = scraper.get(url)
    response.encoding = 'utf-8'
    response.raise_for_status()
    content_size = len(response.content)
    logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> \"-\" [1]")
    soup = BeautifulSoup(response.text, "html.parser")
    app_rows = soup.find_all("div", class_="appRow")
    version_pattern = re.compile(r'\d+(\.\d+)*(-[a-zA-Z0-9]+(\.\d+)*)*')
    for row in app_rows:
        version_text = row.find("h5", class_="appRowTitle").a.text.strip()
        if "alpha" not in version_text.lower() and "beta" not in version_text.lower():
            match = version_pattern.search(version_text)
            if match:
                version = match.group()
                version_parts = version.split('.')
                base_version_parts = []
                for part in version_parts:
                    if part.isdigit():
                        base_version_parts.append(part)
                    else:
                        break
                if base_version_parts:
                    return '.'.join(base_version_parts)
    return None
