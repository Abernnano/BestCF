import requests
import re
import os
import sys
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 25  # 降低并发以保护 API 频率限制

# 扩充数据中心(Colo)映射，包含大量中国及亚太机房
COLO_MAP = {
    "HKG": "HK", "MFM": "MO", "TPE": "TW", "CAN": "CN", "SZX": "CN", "SHA": "CN", "PVG": "CN", "BJS": "CN", "PEK": "CN",
    "CTU": "CN", "SIA": "CN", "CKG": "CN", "CSX": "CN", "HGH": "CN", "NKG": "CN", "TAO": "CN", "TSN": "CN", "CGO": "CN",
    "SIN": "SG", "BKK": "TH", "KUL": "MY", "MNL": "PH", "SGN": "VN", "JKT": "ID", "NRT": "JP", "HND": "JP", "KIX": "JP",
    "ICN": "KR", "SYD": "AU", "LAX": "US", "SJC": "US", "SEA": "US", "FRA": "DE", "LHR": "GB", "CDG": "FR", "AMS": "NL"
}

requests.packages.urllib3.disable_warnings()

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip):
    clean_ip = ip.replace('[', '').replace(']', '').strip()
    is_ipv6 = ":" in clean_ip
    trace_url = f"http://[{clean_ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{clean_ip}/cdn-cgi/trace"
    
    # 1. 优先直连探测 Cloudflare Colo
    try:
        resp = requests.get(trace_url, timeout=2.5, verify=False, proxies={'http': None, 'https': None})
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                colo = colo_match.group(1)
                return COLO_MAP.get(colo, colo[:2]) # 找不到就返回机房前两位
    except:
        pass

    # 2. 保底：在线 API (处理 IPv6 无法直连或机房未知的情况)
    try:
        api_url = f"http://ip-api.com/json/{clean_ip}?fields=countryCode"
        resp = requests.get(api_url, timeout=3.0)
        if resp.status_code == 200:
            return resp.json().get("countryCode")
    except:
        pass
            
    return "UNKNOWN"

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path): return

    print(f"[*] Processing: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_info = {executor.submit(get_ip_location, line.split('#')[0].strip()): line for line in lines}
        for future in as_completed(future_to_info):
            original_line = future_to_info[future]
            country_tag = future.result() or "UNKNOWN"
            
            ip = original_line.split('#')[0].strip()
            if ":" in ip and not ip.startswith("["): ip = f"[{ip}]"
                
            old_comment = original_line.split('#')[1].strip() if '#' in original_line else ""
            flag = get_flag(country_tag)
            new_line = f"{ip}#{flag} {country_tag} | {old_comment}"
            
            if country_tag not in categorized_data: categorized_data[country_tag] = []
            categorized_data[country_tag].append(new_line)
            summary_set.add(new_line)
            time.sleep(0.02) # 微小停顿保护 API

    for tag, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(country_dir, exist_ok=True)
        with open(os.path.join(country_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def main():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    summary_ips = set()
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)
    if summary_ips:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
    print("[SUCCESS] Processing finished.")

if __name__ == "__main__":
    main()
