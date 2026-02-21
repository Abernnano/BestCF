import requests
import re
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# 恢复：不再屏蔽代理，开启环境信任
session = requests.Session()
session.trust_env = True 
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# --- 完整配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 80 

COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR", "TPE": "TW",
    "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US", "FRA": "DE", "LHR": "GB",
    "CDG": "FR", "AMS": "NL", "IAD": "US", "ORD": "US", "DFW": "US", "EWR": "US"
}

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip_line):
    raw_ip = ip_line.split('#')[0].strip().replace('[', '').replace(']', '')
    
    # 优先：直连/探测 CF 节点
    try:
        resp = session.get(f"http://{raw_ip}/cdn-cgi/trace", timeout=2)
        if resp.status_code == 200:
            colo = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo:
                code = colo.group(1)
                return COLO_MAP.get(code, code)
    except: pass

    # 保底：在线 API (自动走代理)
    try:
        resp = session.get(f"http://ip-api.com/json/{raw_ip}?fields=countryCode", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("countryCode")
    except: pass
    return None

def process_file(filename, summary_set):
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path): return
    print(f"[*] Processing: {filename}")
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
                note = line.split('#')[1].strip() if '#' in line else "Node"
                final = f"{ip}#{get_flag(tag)} {tag} | {note}"
                categorized.setdefault(tag, []).append(final)
                summary_set.add(final)

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
    print("[SUCCESS] Classification complete.")

if __name__ == "__main__":
    main()
