import requests
import re
import os
import sys
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. 强制直连：屏蔽系统代理
os.environ['no_proxy'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

if sys.platform.startswith('win'):
    # 推荐改用这种方式，它能更好地处理现有的缓冲区
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')

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

session = requests.Session()
session.trust_env = False 
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip_line):
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    
    # 优先：直连探测
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    try:
        resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
        if resp.status_code == 200:
            colo = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo:
                return COLO_MAP.get(colo.group(1), colo.group(1))
    except:
        pass

    # 保底：在线 API (处理本地无 v6 环境)
    try:
        resp = session.get(f"http://ip-api.com/json/{clean_ip}?fields=countryCode", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("countryCode")
    except:
        pass
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
                note = line.split('#')[1].strip() if '#' in line else "Worker"
                final = f"{ip}#{get_flag(tag)} {tag} | {note}"
                if tag not in categorized: categorized[tag] = []
                categorized[tag].append(final)
                summary_set.add(final)

    for tag, items in categorized.items():
        tag_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(tag_dir, exist_ok=True)
        with open(os.path.join(tag_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def test_ip_quality(ip_line):
    """测试IP质量，返回综合评分"""
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    
    total_score = 0
    test_count = 3  # 测试次数
    
    for _ in range(test_count):
        try:
            start_time = time.time()
            resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
            if resp.status_code == 200:
                latency = (time.time() - start_time) * 1000  # 转换为毫秒
                # 响应时间评分：越短越好，最高100分
                time_score = max(0, 100 - (latency / 2))
                total_score += time_score
        except:
            pass
    
    # 计算平均评分
    avg_score = total_score / test_count if test_count > 0 else 0
    return avg_score

def secondary_filter():
    """二次筛选功能，对all-countries-ip.txt中的IP进行筛选"""
    summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
    if not os.path.exists(summary_path):
        print("[ERROR] Summary file not found.")
        return
    
    print("[*] Starting secondary filter...")
    
    # 读取所有IP
    with open(summary_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    # 按国家码分组
    country_ips = {}
    for line in lines:
        # 提取国家码
        match = re.search(r'#🌐?\s*([A-Z]{2,3})\s*\|', line)
        if match:
            country_code = match.group(1)
            if country_code not in country_ips:
                country_ips[country_code] = []
            country_ips[country_code].append(line)
    
    # 对每个国家的IP进行测试和排序
    filtered_ips = []
    for country_code, ips in country_ips.items():
        # 测试每个IP的质量
        ip_scores = []
        for ip in ips:
            score = test_ip_quality(ip)
            ip_scores.append((ip, score))
        
        # 按评分排序，取前5个
        ip_scores.sort(key=lambda x: x[1], reverse=True)
        top_ips = [ip for ip, score in ip_scores[:5]]
        filtered_ips.extend(top_ips)
    
    # 生成新的TXT文件
    best_ip_file = os.path.join(BASE_DIR, "best-ip.txt")
    if filtered_ips:
        with open(best_ip_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(filtered_ips)) + '\n')
        print(f"[SUCCESS] Secondary filter completed. Kept {len(filtered_ips)} IPs in best-ip.txt.")
    else:
        print("[ERROR] No IPs passed the secondary filter.")

def main():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    summary = set()
    for f in CLASSIFY_FILES: process_file(f, summary)
    if summary:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary))) + '\n')
        # 执行二次筛选
        secondary_filter()
    print("[SUCCESS] Classification done.")

if __name__ == "__main__":
    main()