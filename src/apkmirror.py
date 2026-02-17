import re
import logging
import time
import random
import cloudscraper
from bs4 import BeautifulSoup

# Base URL for APKMirror
APKMIRROR_BASE = "https://www.apkmirror.com"

# Configure logging (your style)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

def get_download_link(version: str, app_name: str, config: dict, arch: str = None) -> str:
    scraper = cloudscraper.create_scraper()
    target_arch = arch if arch else config.get('arch', 'universal')

    # Step 1: Find release page via uploads search (new approach from project)
    uploads_url = f"{APKMIRROR_BASE}/uploads/?appcategory={app_name}"
    logging.info(f"Searching uploads for version {version}")
    time.sleep(2 + random.random())
    response = scraper.get(uploads_url)
    response.encoding = 'utf-8'
    if response.status_code != 200:
        logging.error(f"Uploads page failed: {response.status_code}")
        return None
    soup = BeautifulSoup(response.text, "html.parser")

    release_url = None
    for row in soup.find_all("div", class_="appRow"):
        title = row.find("h5", class_="appRowTitle").a.text.strip()
        if version in title or version.replace('.', '-') in title:
            link = row.find("a", href=True)
            if link:
                release_url = APKMIRROR_BASE + link['href']
                logging.info(f"✓ Found release page: {release_url}")
                break
    if not release_url:
        logging.error("No release page found")
        return None

    # Step 2: Load release page and find variant for arch
    time.sleep(2 + random.random())
    response = scraper.get(release_url)
    response.encoding = 'utf-8'
    if response.status_code != 200:
        logging.error(f"Release page failed: {response.status_code}")
        return None
    soup = BeautifulSoup(response.text, "html.parser")

    variant_url = None
    for a in soup.find_all("a", href=True):
        href = a['href']
        text = a.get_text().strip()
        if 'apk-download' in href and target_arch in text.lower():
            variant_url = APKMIRROR_BASE + href
            logging.info(f"✓ Found variant: {variant_url}")
            break
    if not variant_url:
        logging.error("No variant found")
        return None

    # Step 3: Load variant page and extract final link with key
    time.sleep(2 + random.random())
    response = scraper.get(variant_url)
    response.encoding = 'utf-8'
    if response.status_code != 200:
        logging.error(f"Variant page failed: {response.status_code}")
        return None
    soup = BeautifulSoup(response.text, "html.parser")

    final_url = None
    for a in soup.find_all("a", href=True):
        href = a['href']
        if 'forcebaseapk=true' in href and 'key=' in href:
            final_url = APKMIRROR_BASE + href
            logging.info(f"✓ Found final download URL: {final_url}")
            break
    if not final_url:
        logging.error("No final link found")
        return None

    return final_url

def get_architecture_criteria(arch: str) -> dict:
    arch_mapping = {
        "arm64-v8a": "arm64-v8a",
        "armeabi-v7a": "armeabi-v7a",
        "universal": "universal"
    }
    return arch_mapping.get(arch, "universal")

def get_latest_version(app_name: str, config: dict) -> str:
    scraper = cloudscraper.create_scraper()
    url = f"{APKMIRROR_BASE}/uploads/?appcategory={config['name']}"
    time.sleep(2 + random.random())
    response = scraper.get(url)
    response.encoding = 'utf-8'
    if response.status_code != 200:
        logging.error(f"Latest version URL failed: {response.status_code}")
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    app_rows = soup.find_all("div", class_="appRow")
    version_pattern = re.compile(r'\d+(\.\d+)+')
    for row in app_rows:
        title = row.find("h5", class_="appRowTitle").a.text.strip()
        if "alpha" not in title.lower() and "beta" not in title.lower():
            match = version_pattern.search(title)
            if match:
                return match.group()
    return None
