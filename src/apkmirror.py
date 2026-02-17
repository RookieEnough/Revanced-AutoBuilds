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

    # === 1. DIRECT EXACT PAGE (fastest) ===
    release_name = config.get('release_prefix', config['name'])
    direct_url = f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{release_name}-{version_dash}-release/"
    logging.info(f"Trying direct exact release page: {direct_url}")
    time.sleep(2 + random.random())

    try:
        response = scraper.get(direct_url)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.find('title').get_text().lower() if soup.find('title') else ""
            if version.lower() in title or version_dash in title:
                logging.info(f"✓ Loaded exact release page: {direct_url}")
                found_soup = soup
                correct = True
            else:
                found_soup = None
                correct = False
        else:
            found_soup = None
            correct = False
    except:
        found_soup = None
        correct = False

    # === 2. PATTERN FALLBACK (only if direct failed) ===
    if not correct:
        logging.info("Direct page failed → using pattern fallback")
        version_parts = version.split('.')
        found_soup = None
        correct = False
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
                logging.info(f"Checking: {url}")
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
                            correct = True
                            break
                except:
                    pass
            if correct:
                break

    if not found_soup:
        logging.error("No release page found")
        return None

    # === VARIANT FINDER - Link-based (current APKMirror structure) ===
    download_page_url = None
    logging.info(f"Searching links for {target_arch} + {dpi} on exact page...")

    for a in found_soup.find_all('a', href=True):
        href = a['href'].lower()
        text = a.get_text().lower()
        if 'apk-download' in href and (version.lower() in text or version_dash in href):
            if target_arch in href or target_arch in text:
                if dpi in href or dpi in text:
                    download_page_url = APKMIRROR_BASE + a['href']
                    logging.info(f"✓ Found matching variant link: {download_page_url}")
                    break

    # Ultra-fallback: any link with version + arch
    if not download_page_url:
        for a in found_soup.find_all('a', href=True):
            href = a['href'].lower()
            if version_dash in href and target_arch in href and 'apk-download' in href:
                download_page_url = APKMIRROR_BASE + a['href']
                logging.info(f"✓ Fallback variant link: {download_page_url}")
                break

    if not download_page_url:
        logging.error("No variant link found (even after full link scan)")
        for a in found_soup.find_all('a', href=True)[:20]:
            logging.debug(f"Link: {a.get('href')}")
        return None

    # === FINAL DOWNLOAD STEPS ===
    try:
        time.sleep(2 + random.random())
        r = scraper.get(download_page_url)
        r.encoding = 'utf-8'
        r.raise_for_status()
        s = BeautifulSoup(r.text, "html.parser")
        btn = s.find('a', class_='downloadButton') or s.find('a', href=lambda h: h and 'forcebaseapk' in h)
        if btn:
            final = APKMIRROR_BASE + btn['href']
            logging.info(f"Final APK download URL: {final}")
            return final
    except Exception as e:
        logging.error(f"Download step failed: {e}")

    return None

def get_architecture_criteria(arch: str) -> dict:
    return {"arm64-v8a": "arm64-v8a", "armeabi-v7a": "armeabi-v7a", "universal": "universal"}.get(arch, "universal")

def get_latest_version(app_name: str, config: dict, scraper=None) -> str:
    if scraper is None:
        scraper = create_scraper_session()
    url = f"{APKMIRROR_BASE}/uploads/?appcategory={config['name']}"
    time.sleep(2 + random.random())
    r = scraper.get(url)
    r.encoding = 'utf-8'
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for row in soup.find_all("div", class_="appRow"):
        txt = row.find("h5", class_="appRowTitle").a.text.strip()
        if "alpha" not in txt.lower() and "beta" not in txt.lower():
            m = re.search(r'\d+(\.\d+)+', txt)
            if m:
                return m.group()
    return None
