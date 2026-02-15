import re
import json
import logging
from bs4 import BeautifulSoup
from src import session

base_url = "https://www.apkmirror.com"

def get_download_link(version: str, app_name: str, config: dict, arch: str = None) -> str: 
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
        url_patterns.append(f"{base_url}/apk/{config['org']}/{config['name']}/{release_name}-{current_ver_str}-release/")
        
        # Priority 2: With app name and -release suffix
        if release_name != config['name']:
            url_patterns.append(f"{base_url}/apk/{config['org']}/{config['name']}/{config['name']}-{current_ver_str}-release/")
        
        # Priority 3: With release_name without -release
        url_patterns.append(f"{base_url}/apk/{config['org']}/{config['name']}/{release_name}-{current_ver_str}/")
        
        # Priority 4: With app name without -release
        if release_name != config['name']:
            url_patterns.append(f"{base_url}/apk/{config['org']}/{config['name']}/{config['name']}-{current_ver_str}/")
        
        # Remove duplicate patterns
        url_patterns = list(dict.fromkeys(url_patterns))
        
        for url in url_patterns:
            logging.info(f"Checking potential release URL: {url}")
            
            try:
                response = session.get(url)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")
                    page_text = soup.get_text()
                    
                    # VALIDATION: Check if this page is for our EXACT version
                    # Check multiple possible version formats
                    version_checks = [
                        version,  # 26.1.2.0
                        version.replace('.', '-'),  # 26-1-2-0
                        current_ver_str,  # 26-1-2 (if stripped)
                        ".".join(version_parts[:i])  # 26.1.2 (if stripped)
                    ]
                    
                    # Also check page title and headings for version
                    title_tag = soup.find('title')
                    headings = soup.find_all(['h1', 'h2', 'h3'])
                    
                    is_correct_page = False
                    
                    # Check in page text
                    for check in version_checks:
                        if check and check in page_text:
                            # Additional check: make sure it's not just in a list of other versions
                            # Look for the version in a context that suggests it's the main version
                            if check == version or check == version.replace('.', '-'):
                                is_correct_page = True
                                break
                    
                    # Check in title and headings
                    if not is_correct_page:
                        for heading in headings:
                            heading_text = heading.get_text()
                            for check in version_checks:
                                if check and check in heading_text:
                                    is_correct_page = True
                                    break
                            if is_correct_page:
                                break
                    
                    if not is_correct_page and title_tag:
                        title_text = title_tag.get_text()
                        for check in version_checks:
                            if check and check in title_text:
                                is_correct_page = True
                                break
                    
                    if is_correct_page:
                        content_size = len(response.content)
                        logging.info(f"✓ Correct version page found: {response.url}")
                        found_soup = soup
                        correct_version_page = True
                        break  # Found correct page!
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
            break  # Found correct page for this version part
    
    # If we didn't find the exact version page but found a fallback
    if not correct_version_page and found_soup:
        logging.warning(f"Using fallback page for {app_name} {version} (may contain multiple versions)")
    
    if not found_soup:
        logging.error(f"Could not find any release page for {app_name} {version}")
        return None
    
    # --- VARIANT FINDER (works with both exact pages and fallback pages) ---
    rows = found_soup.find_all('div', class_='table-row headerFont')
    download_page_url = None
    
    # Try to find exact version match first
    for row in rows:
        row_text = row.get_text()
        
        # Check if row contains our exact version
        if version in row_text or version.replace('.', '-') in row_text:
            # Check criteria
            if all(criterion in row_text for criterion in criteria):
                sub_url = row.find('a', class_='accent_color')
                if sub_url:
                    download_page_url = base_url + sub_url['href']
                    break
    
    # If exact version not found, try to find any variant matching criteria
    if not download_page_url:
        for row in rows:
            row_text = row.get_text()
            if all(criterion in row_text for criterion in criteria):
                # Check if this looks like a variant row (has version numbers)
                if re.search(r'\d+(\.\d+)+', row_text):
                    sub_url = row.find('a', class_='accent_color')
                    if sub_url:
                        download_page_url = base_url + sub_url['href']
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
        for idx, row in enumerate(rows[:5]):  # First 5 rows
            logging.debug(f"Row {idx}: {row.get_text()[:100]}...")
        return None
    
    # --- STANDARD DOWNLOAD FLOW ---
    try:
        response = session.get(download_page_url)
        response.raise_for_status()
        content_size = len(response.content)
        logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> Variant Page")
        soup = BeautifulSoup(response.content, "html.parser")

        sub_url = soup.find('a', class_='downloadButton')
        if sub_url:
            final_download_page_url = base_url + sub_url['href']
            response = session.get(final_download_page_url)
            response.raise_for_status()
            content_size = len(response.content)
            logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> Download Page")
            soup = BeautifulSoup(response.content, "html.parser")

            button = soup.find('a', id='download-link')
            if button:
                return base_url + button['href']
    except Exception as e:
        logging.error(f"Error in download flow: {e}")
    
    return None

    # --- STANDARD DOWNLOAD FLOW (Page 2 -> Page 3 -> Link) ---
    response = session.get(download_page_url)
    response.raise_for_status()
    content_size = len(response.content)
    logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> Variant Page")
    soup = BeautifulSoup(response.content, "html.parser")

    sub_url = soup.find('a', class_='downloadButton')
    if sub_url:
        final_download_page_url = base_url + sub_url['href']
        response = session.get(final_download_page_url)
        response.raise_for_status()
        content_size = len(response.content)
        logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> Download Page")
        soup = BeautifulSoup(response.content, "html.parser")

        button = soup.find('a', id='download-link')
        if button:
            return base_url + button['href']

    return None

def get_architecture_criteria(arch: str) -> dict:
    """Map architecture names to APKMirror criteria"""
    arch_mapping = {
        "arm64-v8a": "arm64-v8a",
        "armeabi-v7a": "armeabi-v7a", 
        "universal": "universal"
    }
    return arch_mapping.get(arch, "universal")
    
def get_latest_version(app_name: str, config: dict) -> str:
    # First try: get from main app page
    try:
        main_url = f"{base_url}/apk/{config['org']}/{config['name']}/"
        response = session.get(main_url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            # Try to find version in the page
            version_elem = soup.find('span', string=re.compile(r'\d+\.\d+'))
            if version_elem:
                version_text = version_elem.text.strip()
                match = re.search(r'(\d+(\.\d+)+)', version_text)
                if match:
                    return match.group(1)
    except:
        pass  # If fails, continue to original method
    
    # Original method (keep exactly as you had it)
    url = f"{base_url}/uploads/?appcategory={config['name']}"
    
    response = session.get(url)
    response.raise_for_status()
    content_size = len(response.content)
    logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> \"-\" [1]")
    soup = BeautifulSoup(response.content, "html.parser")

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
