import requests
import re
import os
import sys
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制禁用代理，确保直连
os.environ['no_proxy'] = '*'
session = requests.Session()
session.trust_env = False 

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 50 

# 扩展节点映射
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR",
    "TPE": "TW", "LAX": "US", "SJC": "US", "SEA": "US", "FRA": "DE",
    "LHR": "GB", "CDG": "FR", "AMS": "NL", "SFO": "US", "IAD": "US"
}

def get_ip_location(ip):
    """
    核心改进：强制处理 IPv6 格式
    """
    # 移除可能存在的注释和空格，提取纯净 IP
    clean_ip = ip.split('#')[0].strip().replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    
    # 1. 尝试 Cloudflare Trace 直连探测
    # IPv6 URL 必须包裹在 [] 中
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    try:
        url = f"http://{trace_ip}/cdn-cgi/trace"
        resp = session.get(url, timeout=1.5, verify=False)
        if resp.status_code == 200:
            colo = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo:
                return COLO_MAP.get(colo.group(1), colo.group(1))
    except:
        pass

    # 2. 保底方案：使用支持 IPv6 的在线 API
    # 即使运行器本地没 IPv6，只要能上外网，这个 API 就能返回该 IPv6 的归属地
    try:
        # 使用提供了更好 IPv6 支持的 API
        api_url = f"https://api.iplocation.net/?ip={clean_ip}"
        resp = session.get(api_url, timeout=2.5)
        if resp.status_code == 200:
            code = resp.json().get("country_code2")
            if code and code != "-": return code
    except:
        pass

    return None

# ... 其余 process_file 和 main 逻辑保持不变 ...
