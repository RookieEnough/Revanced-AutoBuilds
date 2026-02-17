import re
import logging
import time
import random
import cloudscraper
from bs4 import BeautifulSoup

APKMIRROR_BASE = "https://www.apkmirror.com"

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")

def create_scraper_session(proxy_url=None):
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
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
    if scraper is None:
        scraper = create_scraper_session()

    target_arch = (arch or config.get('arch', 'universal')).lower()
    dpi = config.get('dpi', 'nodpi').lower()
    version_dash = version.replace('.', '-').lower()

    # 1. Try the exact release page URL first (the one you manually open)
    release_name = config.get('release_prefix', config['name'])
    exact_url = f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{release_name}-{version_dash}-release/"
    logging.info(f"Trying exact release page: {exact_url}")
    time.sleep(2 + random.random())

    found_soup = None
    try:
        response = scraper.get(exact_url)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.find('title').get_text().lower() if soup.find('title') else ""
            if version.lower() in title or version_dash in title:
                logging.info(f"✓ Loaded exact release page: {exact_url}")
                found_soup = soup
    except Exception as e:
        logging.warning(f"Direct exact page failed: {e}")

    # 2. Fallback to pattern search only if direct failed
    if not found_soup:
        logging.info("Direct page failed, falling back to pattern search")
        version_parts = version.split('.')
        release_name = config.get('release_prefix', config['name'])
        
        for i in range(len(version_parts), 0, -1):
            cur = "-".join(version_parts[:i])
            patterns = [
                f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{release_name}-{cur}-release/",
                f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{config['name']}-{cur}-release/" if release_name != config['name'] else None,
                f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{release_name}-{cur}/",
                f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{config['name']}-{cur}/" if release_name != config['name'] else None,
            ]
            patterns = [p for p in patterns if p]
            patterns = list(dict.fromkeys(patterns))
            
            for url in patterns:
                logging.info(f"Checking pattern: {url}")
                time.sleep(2 + random.random())
                try:
                    r = scraper.get(url)
                    r.encoding = 'utf-8'
                    if r.status_code == 200:
                        s = BeautifulSoup(r.text, "html.parser")
                        title = s.find('title').get_text().lower() if s.find('title') else ""
                        if version.lower() in title or version_dash in title or version_dash in url.lower():
                            logging.info(f"✓ Found correct page via pattern: {url}")
                            found_soup = s
                            break
                except:
                    pass
            if found_soup:
                break

    if not found_soup:
        logging.error(f"Could not find release page for {app_name} {version}")
        return None

    # 3. VARIANT FINDER - Robust link + parent text search (matches current APKMirror HTML)
    download_page_url = None
    logging.info(f"Searching ALL links on page for {target_arch} + {dpi}...")

    for a in found_soup.find_all('a', href=True):
        href = a['href'].lower()
        if 'apk-download' in href and version_dash in href:
            # Get full context (the row that contains architecture and DPI)
            parent = a.find_parent()
            row_text = parent.get_text().lower() if parent else a.get_text().lower()
            logging.debug(f"Link {href} → row text: {row_text[:150]}")
            
            if target_arch in row_text and dpi in row_text:
                download_page_url = APKMIRROR_BASE + a['href']
                logging.info(f"✓ Found exact variant link: {download_page_url}")
                break

    if not download_page_url:
        logging.error("No variant link found even after full link + parent-text scan")
        for a in found_soup.find_all('a', href=True)[:30]:
            logging.debug(f"Link: {a.get('href')}")
        return None

    # 4. FINAL DOWNLOAD PAGE → ACTUAL APK
    try:
        time.sleep(2 + random.random())
        response = scraper.get(download_page_url)
        response.encoding = 'utf-8'
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Current APKMirror button structure
        btn = soup.find('a', href=lambda h: h and 'forcebaseapk=true' in h)
        if not btn:
            btn = soup.find('a', class_='downloadButton')
        if btn:
            final_url = APKMIRROR_BASE + btn['href']
            logging.info(f"Final APK download URL: {final_url}")
            return final_url
    except Exception as e:
        logging.error(f"Download flow failed: {e}")

    return None

def get_architecture_criteria(arch: str) -> dict:
    return {"arm64-v8a": "arm64-v8a", "armeabi-v7a": "armeabi-v7a", "universal": "universal"}.get(arch, "universal")

def get_latest_version(app_name: str, config: dict, scraper=None) -> str:
    if scraper is None:
        scraper = create_scraper_session()
    url = f"{APKMIRROR_BASE}/uploads/?appcategory={config['name']}"
    time.sleep(2 + random.random())
    response = scraper.get(url)
    response.encoding = 'utf-8'
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for row in soup.find_all("div", class_="appRow"):
        txt = row.find("h5", class_="appRowTitle").a.text.strip()
        if "alpha" not in txt.lower() and "beta" not in txt.lower():
            m = re.search(r'\d+(\.\d+)+', txt)
            if m:
                return m.group()
    return None
