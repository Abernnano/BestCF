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
    success_count = 0
    ipv6_connection_error = False
    
    for i in range(test_count):
        try:
            start_time = time.time()
            resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
            if resp.status_code == 200:
                latency = (time.time() - start_time) * 1000  # 转换为毫秒
                # 响应时间评分：越短越好，最高100分
                time_score = max(0, 100 - (latency / 2))
                total_score += time_score
                success_count += 1
                print(f"[DEBUG] Test {i+1} for {raw_ip}: success, latency = {latency:.2f}ms, score = {time_score:.2f}")
            else:
                print(f"[DEBUG] Test {i+1} for {raw_ip}: failed with status code {resp.status_code}")
        except Exception as e:
            error_msg = str(e)
            print(f"[DEBUG] Test {i+1} for {raw_ip}: exception - {error_msg}")
            # 检测IPv6连接错误
            if is_ipv6 and ("unreachable network" in error_msg or "10051" in error_msg):
                ipv6_connection_error = True
                print(f"[DEBUG] IPv6 connection error detected for {raw_ip}")
    
    # 计算平均评分
    avg_score = total_score / test_count if test_count > 0 else 0
    
    # 对于IPv6连接错误，给予最低评分，但不直接排除
    if ipv6_connection_error and success_count == 0:
        print(f"[DEBUG] {raw_ip}: IPv6 connection error, assigning minimum score")
        avg_score = 0.1  # 给予最低但非零的评分
    
    print(f"[DEBUG] {raw_ip}: {success_count}/{test_count} tests passed, average score = {avg_score:.2f}")
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
    
    print(f"[DEBUG] Read {len(lines)} lines from {SUMMARY_FILE}")
    
    # 按国家码分组
    country_ips = {}
    no_match_count = 0
    for line in lines:
        # 提取国家码
        try:
            # 先按#分割
            parts = line.split('#', 1)
            if len(parts) < 2:
                no_match_count += 1
                print(f"[DEBUG] No # found in line: {line}")
                continue
            
            # 提取#后面的部分
            info_part = parts[1]
            
            # 提取国家码：寻找emoji后面的2-3个大写字母
            # 匹配模式：emoji + 空格 + 2-3个大写字母 + 空格 + |
            match = re.search(r'[\U0001F1E6-\U0001F1FF]\s*([A-Z]{2,3})\s*\|', info_part)
            if not match:
                # 尝试另一种模式：可能没有emoji
                match = re.search(r'\s*([A-Z]{2,3})\s*\|', info_part)
            
            if match:
                country_code = match.group(1)
                if country_code not in country_ips:
                    country_ips[country_code] = []
                country_ips[country_code].append(line)
                print(f"[DEBUG] Successfully extracted country code {country_code} from line: {line}")
            else:
                no_match_count += 1
                print(f"[DEBUG] No country code found in line: {line}")
        except Exception as e:
            no_match_count += 1
            print(f"[DEBUG] Error processing line {line}: {str(e)}")
    
    print(f"[DEBUG] Found {len(country_ips)} countries, {no_match_count} lines without country code")
    
    # 对每个国家的IP进行测试和排序
    filtered_ips = []
    for country_code, ips in country_ips.items():
        print(f"[DEBUG] Testing {len(ips)} IPs for country {country_code}")
        # 测试每个IP的质量
        ip_scores = []
        for ip in ips:
            score = test_ip_quality(ip)
            ip_scores.append((ip, score))
            print(f"[DEBUG] IP {ip.split('#')[0].strip()} scored {score:.2f}")
        
        # 按评分排序，取前5个
        ip_scores.sort(key=lambda x: x[1], reverse=True)
        top_ips = [ip for ip, score in ip_scores[:5]]
        filtered_ips.extend(top_ips)
        print(f"[DEBUG] Selected {len(top_ips)} IPs for country {country_code}")
    
    # 容错机制：如果没有IP通过筛选，使用原始IP
    if not filtered_ips and lines:
        print("[WARNING] No IPs passed quality test, using original IPs")
        # 按国家码分组，每个国家取前5个
        temp_country_ips = {}
        fallback_no_match_count = 0
        for line in lines:
            try:
                # 先按#分割
                parts = line.split('#', 1)
                if len(parts) < 2:
                    fallback_no_match_count += 1
                    print(f"[DEBUG] Fallback: No # found in line: {line}")
                    continue
                
                # 提取#后面的部分
                info_part = parts[1]
                
                # 提取国家码：寻找emoji后面的2-3个大写字母
                # 匹配模式：emoji + 空格 + 2-3个大写字母 + 空格 + |
                match = re.search(r'[\U0001F1E6-\U0001F1FF]\s*([A-Z]{2,3})\s*\|', info_part)
                if not match:
                    # 尝试另一种模式：可能没有emoji
                    match = re.search(r'\s*([A-Z]{2,3})\s*\|', info_part)
                
                if match:
                    country_code = match.group(1)
                    if country_code not in temp_country_ips:
                        temp_country_ips[country_code] = []
                    if len(temp_country_ips[country_code]) < 5:
                        temp_country_ips[country_code].append(line)
                        print(f"[DEBUG] Fallback: Successfully extracted country code {country_code} from line: {line}")
                else:
                    fallback_no_match_count += 1
                    print(f"[DEBUG] Fallback: No country code found in line: {line}")
            except Exception as e:
                fallback_no_match_count += 1
                print(f"[DEBUG] Fallback: Error processing line {line}: {str(e)}")
        
        # 收集所有IP
        for country_code, ips in temp_country_ips.items():
            filtered_ips.extend(ips)
        print(f"[DEBUG] Fallback: Selected {len(filtered_ips)} IPs, {fallback_no_match_count} lines without country code")
    
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
    elif os.path.exists(os.path.join(BASE_DIR, SUMMARY_FILE)):
        # 如果已经存在SUMMARY_FILE，直接执行二次筛选
        print("[INFO] Using existing summary file for secondary filter")
        secondary_filter()
    else:
        print("[ERROR] No summary file found and no files to process")
    print("[SUCCESS] Classification done.")

if __name__ == "__main__":
    main()