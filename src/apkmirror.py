import re
import logging
import time
import random
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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
    version_dash = version.replace('.', '-').lower()
    release_name = config.get('release_prefix', config['name'])

    # 1. Release page (base URL)
    release_url = f"{APKMIRROR_BASE}/apk/{config['org']}/{config['name']}/{release_name}-{version_dash}-release/"
    
    # 2. Variant Page Construction
    # NOTE: Hardcoding suffix IDs (3, 4, 5...) is risky as they can change based on upload order.
    # ideally, you should scrape the release_url to find the correct variant link for your arch.
    # keeping your logic for now:
    variant_map = {
        "arm64-v8a": "3",
        "armeabi-v7a": "4",
        "x86": "5",
        "x86_64": "6"
    }
    suffix = variant_map.get(target_arch, "3")
    variant_url = f"{release_url.rstrip('/')}/{release_name}-{version_dash}-{suffix}-android-apk-download/"
    
    # 3. SCRAPE THE DOWNLOAD PAGE (The Missing Step)
    # We must visit the page that says "Your download will start immediately..." to get the key.
    download_landing_url = f"{variant_url.rstrip('/')}/download/"
    logging.info(f"Loading download landing page: {download_landing_url}")
    time.sleep(3 + random.random()) # Be gentle

    try:
        response = scraper.get(download_landing_url)
        response.encoding = 'utf-8'
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Look for the anchor tag that contains the download key
        # Usually inside a paragraph saying "If not, please click here"
        # The link usually looks like: /apk/.../download/?key=...
        download_link_tag = soup.find("a", href=lambda h: h and "key=" in h)

        if download_link_tag:
            href = download_link_tag['href']
            final_url = urljoin(APKMIRROR_BASE, href)
            
            # Ensure forcebaseapk is present if you specifically need it
            if "forcebaseapk=true" not in final_url:
                final_url += "&forcebaseapk=true"
                
            logging.info(f"✅ Found secure download link: {final_url}")
            return final_url
        else:
            logging.error("Could not find the secure link (key) in the response.")
            # Debugging: Save html to inspect if needed
            # with open("debug_fail.html", "w", encoding="utf-8") as f: f.write(response.text)
            return None

    except Exception as e:
        logging.error(f"Failed to get download key: {e}")
        return None

    # Generate variant page
    variant_map = {
        "arm64-v8a": "3",
        "armeabi-v7a": "4",
        "x86": "5",
        "x86_64": "6"
    }
    suffix = variant_map.get(target_arch, "3")
    variant_url = f"{release_url.rstrip('/')}/{release_name}-{version_dash}-{suffix}-android-apk-download/"
    logging.info(f"Generated variant page for {target_arch}: {variant_url}")

    # Load variant page and extract the REAL button with forcebaseapk=true (your copied link)
    try:
        time.sleep(3 + random.random())
        response = scraper.get(variant_url)
        response.encoding = 'utf-8'
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        logging.debug(f"Variant page title: {soup.find('title').get_text() if soup.find('title') else 'No title'}")

        # GOD-CODER BUTTON FINDER - finds the exact button in your screenshot
        btn = None
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            text = a.get_text().strip().upper()
            if 'forcebaseapk=true' in href or 'download/?key=' in href or 'download apk' in text:
                btn = a
                logging.info(f"Found download button (text: '{text[:50]}', href contains forcebaseapk=true)")
                break

        if btn and btn.get('href'):
            final_url = APKMIRROR_BASE + btn['href']
            logging.info(f"✅ SUCCESS - Final APK download URL: {final_url}")
            return final_url
        else:
            logging.error("Button not found. Dumping all links on variant page:")
            for a in soup.find_all('a', href=True)[:30]:
                logging.debug(f"Link: {a.get('href')} | Text: {a.get_text().strip()[:80]}")

    except Exception as e:
        logging.error(f"Variant page failed: {e}")

    logging.error("All methods failed")
    return None

def get_architecture_criteria(arch: str) -> dict:
    return {"arm64-v8a": "arm64-v8a", "armeabi-v7a": "armeabi-v7a", "universal": "universal"}.get(arch, "universal")

def get_latest_version(app_name: str, config: dict, scraper=None) -> str:
    if scraper is None:
        scraper = create_scraper_session()
    url = f"{APKMIRROR_BASE}/uploads/?appcategory={config['name']}"
    time.sleep(3 + random.random())
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
