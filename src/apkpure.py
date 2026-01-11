import json
import logging 

from src import session 
from bs4 import BeautifulSoup
      
def get_latest_version(app_name: str, config: str) -> str: 
    url = f"https://apkpure.net/{config['name']}/{config['package']}/versions"

    response = session.get(url)
    response.raise_for_status()
    content_size = len(response.content)
    logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> \"-\" [1]")
    soup = BeautifulSoup(response.content, "html.parser")
    version_info = soup.find('div', class_='ver-top-down')

    if version_info:
        version = version_info['data-dt-version']
        if version:
            return version
            
    return None

def get_download_link(version: str, app_name: str, config: str) ->str:
    url = f"https://apkpure.net/{config['name']}/{config['package']}/download/{version}"

    response = session.get(url)
    response.raise_for_status()
    content_size = len(response.content)
    logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> \"-\" [1]")
    soup = BeautifulSoup(response.content, "html.parser")
    download_link = soup.find('a', id='download_link')
    if download_link:
        return download_link['href']
    
    return None
