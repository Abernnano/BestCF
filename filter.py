import requests
import re
import os
import sys
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. 彻底屏蔽环境代理，强制直连
os.environ['no_proxy'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
# 包含所有生成的文本文件
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt", "proxy-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 60 

# 数据中心映射 (Cloudflare Colo -> 国家码)
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR", "TPE": "TW",
    "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US", "FRA": "DE", "LHR": "GB",
    "CDG": "FR", "AMS": "NL", "ARN": "SE", "IAD": "US", "ORD": "US", "DFW": "US"
}

# 强制直连的 Session
session = requests.Session()
session.trust_env = False 
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip_line):
    """提取 IP 并获取位置"""
    raw_ip = ip_line.split('#')[0].strip()
    # 清洗 IP 格式：去除中括号
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    
    # 方式 A：直连 Cloudflare Trace 探测 (最准)
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    try:
        url = f"http://{trace_ip}/cdn-cgi/trace"
        resp = session.get(url, timeout=2, verify=False, headers=headers)
        if resp.status_code == 200:
            colo = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo:
                code = COLO_MAP.get(colo.group(1), colo.group(1))
                return code
    except:
        pass

    # 方式 B：保底在线 API (强制直连)
    try:
        # 使用更友好的 API 处理 IPv6 归属
        api_url = f"http://ip-api.com/json/{clean_ip}?fields=countryCode"
        resp = session.get(api_url, timeout=3)
        if resp.status_code == 200:
            return resp.json().get("countryCode")
    except:
        pass
    return None

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path): return

    print(f"[*] 分类处理中: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_line = {executor.submit(get_ip_location, l): l for l in lines}
        
        for future in as_completed(future_to_line):
            original_line = future_to_line[future]
            country_tag = future.result()
            
            if country_tag:
                ip_part = original_line.split('#')[0].strip()
                old_note = original_line.split('#')[1].strip() if '#' in original_line else "Worker"
                flag = get_flag(country_tag)
                
                # 统一输出格式: IP#国旗 国家码 | 原注释
                final_line = f"{ip_part}#{flag} {country_tag} | {old_note}"
                
                if country_tag not in categorized_data: categorized_data[country_tag] = []
                categorized_data[country_tag].append(final_line)
                summary_set.add(final_line)

    # 写入国家分类子目录
    for tag, items in categorized_data.items():
        tag_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(tag_dir, exist_ok=True)
        with open(os.path.join(tag_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def main():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    summary_ips = set()
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)
    
    if summary_ips:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
    print("[OK] 分类任务全部完成。")

if __name__ == "__main__":
    main()
