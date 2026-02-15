import base64
from typing import Dict
from src import session

BASE_URL = "https://ws75.aptoide.com/api/7/"

def get_latest_version(app_name: str, config: Dict) -> str:
    package = config['package']
    arch = config.get('arch', 'universal')
    q = _get_q_param(arch)
    url = f"{BASE_URL}apps/search?query={package}&limit=1&trusted=true{q}"
    res = session.get(url).json()
    if res['datalist']['list']:
        return res['datalist']['list'][0]['file']['vername']
    raise ValueError(f"No version found for {package}")

def get_download_link(version: str, app_name: str, config: Dict) -> str:
    package = config['package']
    arch = config.get('arch', 'universal')
    q = _get_q_param(arch)

    if version.lower() == "latest":
        url = f"{BASE_URL}apps/search?query={package}&limit=1&trusted=true{q}"
        res = session.get(url).json()
        return res['datalist']['list'][0]['file']['path']

    # Find vercode for specific version
    url_versions = f"{BASE_URL}listAppVersions?package_name={package}&limit=50{q}"
    res_v = session.get(url_versions).json()
    vercode = None
    for app in res_v['datalist']['list']:
        if app['file']['vername'] == version:
            vercode = app['file']['vercode']
            break
    if not vercode:
        raise ValueError(f"Version {version} not found for {package}")

    # Get meta with download path
    url_meta = f"{BASE_URL}getAppMeta?package_name={package}&vercode={vercode}{q}"
    res_meta = session.get(url_meta).json()
    return res_meta['data']['file']['path']

def _get_q_param(arch: str) -> str:
    if arch == 'universal':
        return ''
    cpu_map = {
        'arm64-v8a': 'arm64-v8a,armeabi-v7a,armeabi',
        'armeabi-v7a': 'armeabi-v7a,armeabi',
        # Add others as needed
    }
    cpu = cpu_map.get(arch, '')
    if cpu:
        q_str = f"myCPU={cpu}&leanback=0"
        return f"&q={base64.b64encode(q_str.encode('utf-8')).decode('utf-8')}"
    return ''
