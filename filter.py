import requests
import re
import os
import sys
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制禁用 Python 所有的系统代理环境变量
os.environ['no_proxy'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

# 强制输出编码
#if sys.platform.startswith('win'):
    #sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 100 

# 数据中心代码映射 (补充更多常见节点)
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR",
    "TPE": "TW", "LAX": "US", "SJC": "US", "SEA": "US", "FRA": "DE",
    "LHR": "GB", "CDG": "FR", "AMS": "NL", "ARN": "SE", "SFO": "US",
    "IAD": "US", "ORD": "US", "DFW": "US", "EWR": "US", "YVR": "CA"
}

requests.packages.urllib3.disable_warnings()

# 创建一个强制直连的 Session
session = requests.Session()
session.trust_env = False  # 关键：彻底忽略系统代理配置
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def get_flag(country_code):
    if not country_code or len(country_code) != 2:
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip):
    """获取 IP 位置，强制直连"""
    clean_ip = ip.replace('[', '').replace(']', '').strip()
    is_ipv6 = ":" in clean_ip
    
    # 1. 优先尝试 Cloudflare Trace 直连探测
    trace_url = f"http://[{clean_ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{clean_ip}/cdn-cgi/trace"
    try:
        # 使用直连 Session，超时缩短以提高效率
        resp = session.get(trace_url, timeout=2, verify=False, headers=headers)
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                colo = colo_match.group(1)
                return COLO_MAP.get(colo, colo)
    except:
        pass

    # 2. 保底方案：使用 ip-api.com (同样强制直连)
    try:
        api_url = f"http://ip-api.com/json/{clean_ip}?fields=countryCode"
        resp = session.get(api_url, timeout=3)
        if resp.status_code == 200:
            return resp.json().get("countryCode")
    except:
        pass

    return None

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path):
        return

    print(f"[*] Classifying: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_info = {executor.submit(get_ip_location, line.split('#')[0].strip()): line for line in lines}
        
        for future in as_completed(future_to_info):
            original_line = future_to_info[future]
            country_tag = future.result()
            
            if country_tag:
                ip = original_line.split('#')[0].strip()
                old_comment = original_line.split('#')[1].strip() if '#' in original_line else ""
                flag = get_flag(country_tag)
                new_line = f"{ip}#{flag} {country_tag} | {old_comment}"
                
                if country_tag not in categorized_data:
                    categorized_data[country_tag] = []
                categorized_data[country_tag].append(new_line)
                summary_set.add(new_line)

    for tag, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(country_dir, exist_ok=True)
        with open(os.path.join(country_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    
    summary_ips = set()
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)

    if summary_ips:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
        print(f"[SUCCESS] Classification finished.")

if __name__ == "__main__":
    main()
