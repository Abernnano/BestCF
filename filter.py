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
MAX_WORKERS = 15  # 降低并发，确保每个请求都能拿到结果

# 增强型机房映射表：{三字码: (国家码, 城市名)}
COLO_INFO = {
    "HKG": ("HK", "Hong Kong"), "SIN": ("SG", "Singapore"), "NRT": ("JP", "Tokyo"),
    "HND": ("JP", "Tokyo"), "KIX": ("JP", "Osaka"), "ICN": ("KR", "Seoul"),
    "TPE": ("TW", "Taipei"), "LAX": ("US", "Los Angeles"), "SJC": ("US", "San Jose"),
    "SEA": ("US", "Seattle"), "SFO": ("US", "San Francisco"), "ORD": ("US", "Chicago"),
    "DFW": ("US", "Dallas"), "IAD": ("US", "Ashburn"), "JFK": ("US", "New York"),
    "FRA": ("DE", "Frankfurt"), "LHR": ("GB", "London"), "CDG": ("FR", "Paris"),
    "AMS": ("NL", "Amsterdam"), "CAN": ("CN", "Guangzhou"), "SZX": ("CN", "Shenzhen"),
    "SHA": ("CN", "Shanghai"), "PVG": ("CN", "Shanghai"), "BJS": ("CN", "Beijing"),
    "PEK": ("CN", "Beijing"), "CTU": ("CN", "Chengdu"), "SIA": ("CN", "Xi'an"),
    "CKG": ("CN", "Chongqing"), "NKG": ("CN", "Nanjing"), "HGH": ("CN", "Hangzhou"),
    "MFM": ("MO", "Macao"), "BKK": ("TH", "Bangkok"), "KUL": ("MY", "Kuala Lumpur"),
    "MNL": ("PH", "Manila"), "SGN": ("VN", "Ho Chi Minh City"), "JKT": ("ID", "Jakarta"),
    "SYD": ("AU", "Sydney"), "MEL": ("AU", "Melbourne"), "YVR": ("CA", "Vancouver"),
    "YYZ": ("CA", "Toronto"), "MXP": ("IT", "Milan"), "MAD": ("ES", "Madrid")
}

requests.packages.urllib3.disable_warnings()

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip_full):
    """三级探测：Trace -> API -> Unknown"""
    # 剥离端口号和中括号
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    is_ipv6 = ":" in ip
    trace_url = f"http://[{ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{ip}/cdn-cgi/trace"
    
    # 1. 尝试直连 Cloudflare Trace
    try:
        resp = requests.get(trace_url, timeout=2.5, verify=False, proxies={'http': None, 'https': None})
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                code = colo_match.group(1)
                if code in COLO_INFO:
                    country, city = COLO_INFO[code]
                    return f"{country}_{city}"
                return f"{code[:2]}_{code}" # 找不到机房则显示机房代号
    except:
        pass

    # 2. 保底：在线 API (请求国家和城市)
    try:
        api_url = f"http://ip-api.com/json/{ip}?fields=countryCode,city"
        resp = requests.get(api_url, timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            country = data.get("countryCode", "UN")
            city = data.get("city", "Unknown").replace(" ", "")
            return f"{country}_{city}"
    except:
        pass
            
    return "UN_Unknown"

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path): return

    print(f"[*] Analyzing: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_info = {executor.submit(get_ip_location, line.split('#')[0].strip()): line for line in lines}
        for future in as_completed(future_to_info):
            original_line = future_to_info[future]
            loc_info = future.result() # 格式为 "国家码_城市"
            
            ip_part = original_line.split('#')[0].strip()
            # 格式化 IPv6 补全中括号
            clean_ip = re.sub(r'\[|\]', '', ip_part.split(':')[0] if ":" in ip_part else ip_part)
            if ":" in clean_ip and not ip_part.startswith("["):
                ip_part = f"[{ip_part}]"
                
            old_comment = original_line.split('#')[1].strip() if '#' in original_line else ""
            
            country_code = loc_info.split('_')[0]
            flag = get_flag(country_code)
            new_line = f"{ip_part}#{flag} {loc_info} | {old_comment}"
            
            if country_code not in categorized_data: categorized_data[country_code] = []
            categorized_data[country_code].append(new_line)
            summary_set.add(new_line)
            time.sleep(0.05)

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
    print("[SUCCESS] Classification complete.")

if __name__ == "__main__":
    main()
