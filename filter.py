import requests
import re
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. 解决 Windows 输出乱码
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 80 

COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR", "TPE": "TW",
    "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US", "FRA": "DE", "LHR": "GB",
    "CDG": "FR", "AMS": "NL", "IAD": "US", "ORD": "US", "DFW": "US", "EWR": "US"
}

# 创建一个显式【禁用代理】的 Session，用于测试 Cloudflare IP
direct_session = requests.Session()
direct_session.trust_env = False
direct_session.proxies = {'http': None, 'https': None}

# 创建一个【遵循系统/路由器代理】的 Session，用于访问 ip-api.com
api_session = requests.Session()

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip_line):
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    
    # 优先：直连探测 (必须 direct_session)
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    try:
        resp = direct_session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, headers=headers)
        if resp.status_code == 200:
            colo = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo:
                return COLO_MAP.get(colo.group(1), colo.group(1))
    except:
        pass

    # 保底：在线 API (可以走路由器代理，使用 api_session)
    try:
        resp = api_session.get(f"http://ip-api.com/json/{clean_ip}?fields=countryCode", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("countryCode")
    except:
        pass
    return None

# ... 后续 process_file 和 main 函数逻辑保持不变 ...
