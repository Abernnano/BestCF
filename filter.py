import requests
import re
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# 解决 Windows 环境下的编码问题
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 80 

# Cloudflare 节点与国家代码映射
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR", "TPE": "TW",
    "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US", "FRA": "DE", "LHR": "GB",
    "CDG": "FR", "AMS": "NL", "IAD": "US", "ORD": "US", "DFW": "US", "EWR": "US"
}

# [重要] 1. 强制直连 Session：用于探测 CF 节点信息，必须绕过所有代理
direct_session = requests.Session()
direct_session.trust_env = False  # 禁用环境变量代理
direct_session.proxies = {'http': None, 'https': None} # 显式设为空

# [重要] 2. 正常 API Session：用于请求 ip-api.com，跟随系统/路由器代理
api_session = requests.Session()
api_session.trust_env = True 

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip_line):
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    
    # 步骤 A：直连探测（通过访问 CF 自身的 trace 接口获取 colo）
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    try:
        # 使用 direct_session 确保测到的是真实连接情况
        resp = direct_session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, headers=headers)
        if resp.status_code == 200:
            colo = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo:
                return COLO_MAP.get(colo.group(1), colo.group(1))
    except:
        pass

    # 步骤 B：保底 API（如果直连探测失败，使用第三方 API 查找）
    try:
        # 使用 api_session，如果路由器有代理，这里会自动走代理
        resp = api_session.get(f"http://ip-api.com/json/{clean_ip}?fields=countryCode", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("countryCode")
    except:
        pass
    return None

def process_file(filename, summary_set):
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path): return
    print(f"[*] Analyzing: {filename}")
    with open(path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(get_ip_location, l): l for l in lines}
        for f in as_completed(futures):
            line = futures[f]
            tag = f.result()
            if tag:
                ip = line.split('#')[0].strip()
                note = line.split('#')[1].strip() if '#' in line else "Worker"
                final = f"{ip}#{get_flag(tag)} {tag} | {note}"
                if tag not in categorized: categorized[tag] = []
                categorized[tag].append(final)
                summary_set.add(final)

    # 写入分国家文件夹
    for tag, items in categorized.items():
        tag_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(tag_dir, exist_ok=True)
        with open(os.path.join(tag_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def main():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    summary = set()
    for f in CLASSIFY_FILES: process_file(f, summary)
    if summary:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary))) + '\n')
    print("[SUCCESS] All IP filtered and categorized.")

if __name__ == "__main__":
    main()
