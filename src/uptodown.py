import logging 
from src import session 
from bs4 import BeautifulSoup

def get_latest_version(app_name: str, config: dict) -> str:
    # Generate all possible Uptodown names
    possible_names = generate_possible_uptodown_names(config)
    
    logging.info(f"Trying {len(possible_names)} possible Uptodown names for {app_name}")
    
    for uptodown_name in possible_names:
        url = f"https://{uptodown_name}.en.uptodown.com/android/versions"
        try:
            response = session.get(url)
            if response.status_code == 200:
                content_size = len(response.content)
                logging.info(f"✓ Found: {response.url}")
                soup = BeautifulSoup(response.content, "html.parser")
                version_spans = soup.select('#versions-items-list .version')
                versions = [span.text for span in version_spans]
                
                if versions:
                    highest_version = max(versions)
                    logging.info(f"Found version {highest_version} for {app_name}")
                    return highest_version
            elif response.status_code == 404:
                logging.debug(f"✗ Not found: {url}")
                continue
            else:
                response.raise_for_status()
        except Exception as e:
            logging.debug(f"Failed for {url}: {str(e)[:50]}...")
            continue
    
    raise Exception(f"Could not find Uptodown page for {app_name}")

def get_download_link(version: str, app_name: str, config: dict) -> str:
    # Generate all possible Uptodown names
    possible_names = generate_possible_uptodown_names(config)
    
    logging.info(f"Searching {len(possible_names)} possible Uptodown names for {app_name} v{version}")
    
    for uptodown_name in possible_names:
        base_url = f"https://{uptodown_name}.en.uptodown.com/android"
        try:
            response = session.get(f"{base_url}/versions")
            if response.status_code != 200:
                continue
                
            soup = BeautifulSoup(response.content, "html.parser")
            data_code = soup.find('h1', id='detail-app-name')['data-code']

            page = 1
            while True:
                response = session.get(f"{base_url}/apps/{data_code}/versions/{page}")
                response.raise_for_status()
                version_data = response.json().get('data', [])
                
                if not version_data:
                    break
                    
                for entry in version_data:
                    if entry["version"] == version:
                        version_url_parts = entry["versionURL"]
                        version_url = f"{version_url_parts['url']}/{version_url_parts['extraURL']}/{version_url_parts['versionID']}"
                        version_page = session.get(version_url)
                        version_page.raise_for_status()
                        soup = BeautifulSoup(version_page.content, "html.parser")
                        
                        button = soup.find('button', id='detail-download-button')
                        if not button:
                            continue
                            
                        onclick = button.get('onclick', '')
                        if onclick and "download-link-deeplink" in onclick:
                            version_url += '-x'
                            version_page = session.get(version_url)
                            version_page.raise_for_status()
                            soup = BeautifulSoup(version_page.content, "html.parser")
                            button = soup.find('button', id='detail-download-button')
                        
                        if button and 'data-url' in button.attrs:
                            download_url = button['data-url']
                            return f"https://dw.uptodown.com/dwn/{download_url}"
                
                if all(entry["version"] < version for entry in version_data):
                    break
                page += 1
        except Exception as e:
            logging.debug(f"Pattern {uptodown_name} failed: {str(e)[:50]}...")
            continue
    
    logging.error(f"Version {version} not found for {app_name}")
    return None

def generate_possible_uptodown_names(config: dict) -> list:
    """Generate all possible Uptodown URL patterns from config data"""
    app_name = config.get('name', '')
    package = config.get('package', '')
    
    possible_names = set()
    
    # 1. Basic variations
    possible_names.add(app_name)
    possible_names.add(app_name.replace('-', ''))
    possible_names.add(app_name.replace('-plus', 'plus'))
    possible_names.add(app_name.replace('-', '_'))
    
    # 2. Package name variations
    package_dash = package.replace('.', '-')
    possible_names.add(package_dash)
    
    # Common TLD patterns (com-, org-, net-)
    if package.startswith('com.'):
        possible_names.add(package_dash)
        possible_names.add(package_dash.replace('com-', ''))
        
        # com-package variations
        parts = package.split('.')
        if len(parts) >= 2:
            # com-appname
            possible_names.add(f"com-{parts[1]}")
            # com-appname-lastpart
            possible_names.add(f"com-{parts[1]}-{parts[-1]}")
            # appname only
            possible_names.add(parts[1])
            possible_names.add(parts[-1])
            
            # For multi-part packages like com.disney.disneyplus
            if len(parts) >= 3:
                possible_names.add(f"com-{parts[1]}{parts[2]}")
                possible_names.add(f"com-{parts[1]}{parts[2]}-mea")
                possible_names.add(f"com-{'-'.join(parts[1:])}")
    
    # 3. Common suffixes (these cover 99% of cases)
    suffixes = ['', '-android', '-mobile', '-mea', '-plus', '-pro', '-lite', '-hd', '-apk']
    for suffix in suffixes:
        possible_names.add(app_name + suffix)
        possible_names.add(package_dash + suffix)
    
    # 4. Company/app combinations
    # Extract company name from package (first meaningful part after TLD)
    parts = package.split('.')
    if len(parts) >= 2:
        company = parts[1]
        app_basename = parts[-1]
        possible_names.add(f"{company}-{app_basename}")
        possible_names.add(f"{company}-{app_name}")
        
        # For apps like Adobe
        if 'adobe' in package.lower():
            possible_names.add(f"adobe-{app_basename}")
            possible_names.add(f"adobe-{app_basename}-mobile")
    
    # 5. Remove common words and try variations
    clean_name = app_name
    for word in ['plus', 'pro', 'lite', 'free', 'paid', 'mod']:
        if word in clean_name:
            clean = clean_name.replace(f'-{word}', '').replace(word, '')
            possible_names.add(clean)
            possible_names.add(f"{clean}-{word}")
    
    # 6. All lowercase
    lowercase_names = {name.lower() for name in possible_names}
    possible_names.update(lowercase_names)
    
    # Clean up: remove None/empty, deduplicate
    return [name for name in possible_names if name and len(name) > 1]
