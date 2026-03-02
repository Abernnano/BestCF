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

def process_file(filename, summary_set, proxy_ips):
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
                # 排除proxy-ip.txt中的IP和IPDB服务的IPv4地址
                if ip in proxy_ips:
                    continue
                if note.startswith("Global-IPDB") and "V6" not in note:
                    continue
                final = f"{ip}#{get_flag(tag)} {tag} | {note}"
                if tag not in categorized: categorized[tag] = []
                categorized[tag].append(final)
                summary_set.add(final)

    for tag, items in categorized.items():
        tag_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(tag_dir, exist_ok=True)
        with open(os.path.join(tag_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def test_ip_quality(ip_line, blacklist=None):
    """测试IP质量，返回综合评分"""
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    
    # 检查是否在黑名单中
    if blacklist and raw_ip in blacklist:
        return 0.1
    
    # 测试参数
    test_count = 2  # 减少测试次数，提高效率
    success_count = 0
    ipv6_connection_error = False
    
    # 测试指标
    latencies = []
    download_speeds = []
    accessibility_scores = []
    
    # 基础连接测试（合并为一次测试，减少网络请求）
    try:
        start_time = time.time()
        resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
        if resp.status_code == 200:
            latency = (time.time() - start_time) * 1000  # 转换为毫秒
            latencies.append(latency)
            success_count = test_count  # 一次成功视为所有测试通过
            
            # 同时进行下载速度测试
            data_size = len(resp.content)
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                download_speed = (data_size / 1024) / elapsed_time  # KB/s
                download_speeds.append(download_speed)
    except Exception as e:
        error_msg = str(e)
        # 检测IPv6连接错误
        if is_ipv6 and ("unreachable network" in error_msg or "10051" in error_msg):
            ipv6_connection_error = True
    
    # 网页可访问性测试（只测试一个代表性网站）
    accessible_count = 0
    try:
        start_time = time.time()
        resp = session.get(f"http://{trace_ip}", timeout=3, verify=False, headers=headers)
        if resp.status_code == 200:
            load_time = (time.time() - start_time) * 1000
            if load_time < 3000:  # 3秒内加载
                accessible_count = 1
                accessibility_scores.append(100 - (load_time / 30))  # 最高100分
    except:
        pass
    
    # 计算综合评分
    score_components = {}
    
    # 延迟评分（占30%）
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        latency_score = max(0, 100 - (avg_latency / 2))
        score_components['latency'] = latency_score * 0.3
    else:
        score_components['latency'] = 0
    
    # 下载速度评分（占25%）
    if download_speeds:
        avg_download = sum(download_speeds) / len(download_speeds)
        # 假设100KB/s为满分
        download_score = min(100, avg_download)
        score_components['download'] = download_score * 0.25
    else:
        score_components['download'] = 0
    
    # 可访问性评分（占30%）
    if accessibility_scores:
        avg_accessibility = sum(accessibility_scores) / len(accessibility_scores)
        score_components['accessibility'] = avg_accessibility * 0.3
    else:
        score_components['accessibility'] = 0
    
    # 连接稳定性评分（占15%）
    stability_score = (success_count / test_count) * 100
    score_components['stability'] = stability_score * 0.15
    
    # 计算总分
    total_score = sum(score_components.values())
    
    # 对于IPv6连接错误，给予最低评分，但不直接排除
    if ipv6_connection_error and success_count == 0:
        total_score = 0.1  # 给予最低但非零的评分
    
    return total_score

def secondary_filter():
    """二次筛选功能，对all-countries-ip.txt中的IP进行筛选"""
    summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
    if not os.path.exists(summary_path):
        print("[ERROR] Summary file not found.")
        return
    
    print("[*] Starting secondary filter...")
    
    # 读取IP黑名单
    blacklist = set()
    blacklist_path = os.path.join(BASE_DIR, "ip-blacklist.txt")
    if os.path.exists(blacklist_path):
        with open(blacklist_path, 'r', encoding='utf-8') as f:
            for line in f:
                ip = line.strip()
                if ip:
                    blacklist.add(ip)
    
    # 读取所有IP
    with open(summary_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    # 按国家码分组
    country_ips = {}
    for line in lines:
        # 提取国家码
        try:
            # 先按#分割
            parts = line.split('#', 1)
            if len(parts) < 2:
                continue
            
            # 提取#后面的部分
            info_part = parts[1]
            
            # 提取国家码：寻找emoji后面的2-3个大写字母
            match = re.search(r'[\U0001F1E6-\U0001F1FF]\s*([A-Z]{2,3})\s*\|', info_part)
            if not match:
                # 尝试另一种模式：可能没有emoji
                match = re.search(r'\s*([A-Z]{2,3})\s*\|', info_part)
            
            if match:
                country_code = match.group(1)
                if country_code not in country_ips:
                    country_ips[country_code] = []
                country_ips[country_code].append(line)
        except:
            pass
    
    # 对每个国家的IP进行测试和排序
    filtered_ips = []
    new_blacklist = set()
    
    # 使用线程池并行处理不同国家的IP测试
    def process_country(country_code, ips):
        country_filtered = []
        country_blacklist = set()
        
        # 测试每个IP的质量（减少重试次数）
        ip_scores = []
        for ip in ips:
            # 最多重试1次，提高效率
            max_retries = 1
            retry_count = 0
            best_score = 0
            
            while retry_count <= max_retries:
                score = test_ip_quality(ip, blacklist)
                if score > best_score:
                    best_score = score
                # 如果分数足够高，直接结束重试
                if best_score > 60:
                    break
                retry_count += 1
                if retry_count <= max_retries:
                    time.sleep(0.2)  # 减少重试间隔
            
            ip_scores.append((ip, best_score))
            
            # 如果分数过低，添加到黑名单
            if best_score < 10:
                ip_addr = ip.split('#')[0].strip()
                country_blacklist.add(ip_addr)
        
        # 动态计算阈值
        if ip_scores:
            # 按评分排序
            ip_scores.sort(key=lambda x: x[1], reverse=True)
            
            # 计算平均分数，用于动态调整阈值
            avg_score = sum(score for _, score in ip_scores) / len(ip_scores)
            # 根据平均分数动态调整阈值
            min_threshold = max(30, avg_score * 0.6)  # 最低阈值30，或平均分数的60%
            
            # 筛选出符合阈值的IP，最多取前10个
            qualified_ips = [(ip, score) for ip, score in ip_scores if score >= min_threshold]
            top_ips = [ip for ip, score in qualified_ips[:10]]
            country_filtered.extend(top_ips)
        
        return country_filtered, country_blacklist
    
    # 使用线程池并行处理
    if country_ips:
        with ThreadPoolExecutor(max_workers=min(10, len(country_ips))) as executor:
            futures = {executor.submit(process_country, country, ips): country for country, ips in country_ips.items()}
            for future in as_completed(futures):
                country = futures[future]
                try:
                    country_filtered, country_blacklist = future.result()
                    filtered_ips.extend(country_filtered)
                    new_blacklist.update(country_blacklist)
                except Exception as e:
                    print(f"[ERROR] Error processing country {country}: {str(e)}")
    
    # 更新黑名单
    if new_blacklist:
        with open(blacklist_path, 'a', encoding='utf-8') as f:
            for ip in new_blacklist:
                if ip not in blacklist:
                    f.write(ip + '\n')
    
    # 容错机制：如果没有IP通过筛选，使用原始IP
    if not filtered_ips and lines:
        # 按国家码分组，每个国家取前5个
        temp_country_ips = {}
        for line in lines:
            try:
                # 先按#分割
                parts = line.split('#', 1)
                if len(parts) < 2:
                    continue
                
                # 提取#后面的部分
                info_part = parts[1]
                
                # 提取国家码
                match = re.search(r'[\U0001F1E6-\U0001F1FF]\s*([A-Z]{2,3})\s*\|', info_part)
                if not match:
                    match = re.search(r'\s*([A-Z]{2,3})\s*\|', info_part)
                
                if match:
                    country_code = match.group(1)
                    if country_code not in temp_country_ips:
                        temp_country_ips[country_code] = []
                    if len(temp_country_ips[country_code]) < 5:
                        temp_country_ips[country_code].append(line)
            except:
                pass
        
        # 收集所有IP
        for country_code, ips in temp_country_ips.items():
            filtered_ips.extend(ips)
    
    # 最终验证：测试筛选出的IP是否满足要求（简化验证）
    if filtered_ips:
        print("[*] Performing final verification on selected IPs...")
        final_ips = []
        
        # 简化验证：只测试3个代表性网站
        test_websites = [
            "http://example.com",
            "http://google.com",
            "http://baidu.com"
        ]
        
        for ip_line in filtered_ips:
            raw_ip = ip_line.split('#')[0].strip()
            clean_ip = raw_ip.replace('[', '').replace(']', '')
            is_ipv6 = ":" in clean_ip
            trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
            
            success_count = 0
            total_load_time = 0
            
            for website in test_websites:
                try:
                    start_time = time.time()
                    resp = session.get(f"http://{trace_ip}", timeout=3, verify=False, headers=headers)
                    if resp.status_code == 200:
                        load_time = (time.time() - start_time) * 1000
                        total_load_time += load_time
                        if load_time < 3000:  # 3秒内加载
                            success_count += 1
                except:
                    pass
            
            # 计算平均加载时间和成功率
            avg_load_time = total_load_time / len(test_websites) if success_count > 0 else 9999
            success_rate = (success_count / len(test_websites)) * 100
            
            # 只有满足要求的IP才会被保留
            if success_rate >= 66.7 and avg_load_time <= 3000:  # 2/3的成功率
                final_ips.append(ip_line)
            else:
                # 添加到黑名单
                new_blacklist.add(raw_ip)
        
        # 更新黑名单
        if new_blacklist:
            with open(blacklist_path, 'a', encoding='utf-8') as f:
                for ip in new_blacklist:
                    if ip not in blacklist:
                        f.write(ip + '\n')
        
        # 使用最终验证通过的IP
        if final_ips:
            filtered_ips = final_ips
    
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
    # 读取proxy-ip.txt中的IP地址
    proxy_ips = set()
    proxy_path = os.path.join(BASE_DIR, "proxy-ip.txt")
    if os.path.exists(proxy_path):
        with open(proxy_path, 'r', encoding='utf-8') as f:
            for line in f:
                ip = line.split('#')[0].strip()
                if ip:
                    proxy_ips.add(ip)
        print(f"[INFO] Loaded {len(proxy_ips)} proxy IPs from proxy-ip.txt")
    summary = set()
    for f in CLASSIFY_FILES: process_file(f, summary, proxy_ips)
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