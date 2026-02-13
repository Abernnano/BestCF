import requests
import re
import os
import sys
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制输出编码为 UTF-8，防止 Windows 乱码
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 40  # 适当降低并发以适配路由器连接数

COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR",
    "TPE": "TW", "LAX": "US", "SJC": "US", "SEA": "US", "FRA": "DE",
    "LHR": "GB", "CDG": "FR", "AMS": "NL", "ARN": "SE", "SFO": "US"
}

requests.packages.urllib3.disable_warnings()

def get_flag(country_code):
    """国家码转 Emoji"""
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip):
    """
    三级位置探测逻辑
    """
    clean_ip = ip.replace('[', '').replace(']', '').strip()
    is_ipv6 = ":" in clean_ip
    
    # 1. 优先：Cloudflare 直连探测 (Anycast 路径最真实)
    url = f"http://[{clean_ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{clean_ip}/cdn-cgi/trace"
    try:
        resp = requests.get(url, timeout=2.5, verify=False, proxies={'http': None, 'https': None})
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                colo = colo_match.group(1)
                return COLO_MAP.get(colo, colo)
    except:
        pass

    # 2. 次选：在线 GeoIP API (解决本地无 IPv6 环境或被代理拦截)
    try:
        api_url = f"http://ip-api.com/json/{clean_ip}?fields=countryCode"
        resp = requests.get(api_url, timeout=3.0)
        country = resp.json().get("countryCode")
        if country: return country
    except:
        pass

    # 3. 垫底：标记为未知 (确保 IP 不会被直接从列表中丢弃)
    return "UNKNOWN"

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path): return

    print(f"[*] Analyzing: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交任务
        future_to_info = {executor.submit(get_ip_location, line.split('#')[0].strip()): line for line in lines}
        
        for future in as_completed(future_to_info):
            original_line = future_to_info[future]
            country_tag = future.result() or "UNKNOWN"
            
            ip = original_line.split('#')[0].strip()
            # 统一 IPv6 输出格式
            if ":" in ip and not ip.startswith("["):
                ip = f"[{ip}]"
            
            old_comment = original_line.split('#')[1].strip() if '#' in original_line else "Optimized"
            flag = get_flag(country_tag)
            new_line = f"{ip}#{flag} {country_tag} | {old_comment}"
            
            if country_tag not in categorized_data: categorized_data[country_tag] = []
            categorized_data[country_tag].append(new_line)
            summary_set.add(new_line)

    # 写入分类文件
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
    print("[SUCCESS] Multi-stack IP classification complete.")

if __name__ == "__main__":
    main()
