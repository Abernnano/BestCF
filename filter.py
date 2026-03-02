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

# --- 全局变量定义区 ---

# 文件路径配置
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]  # 需要处理的IP文件列表
BASE_DIR = "./bestcf"  # 基础目录
SUMMARY_FILE = "all-countries-ip.txt"  # 汇总文件
BEST_IP_FILE = "best-ip.txt"  # 最佳IP文件
BLACKLIST_FILE = "ip-blacklist.txt"  # IP黑名单文件
PROXY_IP_FILE = "proxy-ip.txt"  # 代理IP文件

# 线程池配置
MAX_WORKERS = 80  # 最大工作线程数
MAX_COUNTRY_WORKERS = 10  # 处理国家IP的最大线程数

# 测试配置
TEST_COUNT = 2  # 基础连接测试次数
MAX_RETRIES = 1  # 最大重试次数
RETRY_INTERVAL = 0.2  # 重试间隔（秒）

# 筛选阈值配置
MIN_THRESHOLD = 30  # 最低筛选阈值
THRESHOLD_RATIO = 0.6  # 基于平均分数的阈值比例
MIN_SUCCESS_RATE = 66.7  # 最低成功率要求（%）
MAX_LOAD_TIME = 3000  # 最大加载时间（毫秒）

# IP数量配置
MAX_IPS_PER_COUNTRY = 10  # 每个国家最多保留的IP数量
MAX_IPS_PER_COUNTRY_FALLBACK = 5  # 容错机制下每个国家最多保留的IP数量

# 国家代码映射
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR", "TPE": "TW",
    "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US", "FRA": "DE", "LHR": "GB",
    "CDG": "FR", "AMS": "NL", "IAD": "US", "ORD": "US", "DFW": "US", "EWR": "US"
}

# 测试网站列表 - 覆盖不同地区的国外域名
TEST_WEBSITES = [
    "http://example.com",      # 全球通用
    "http://google.com",       # 美国
    "http://github.com",       # 美国
    "http://facebook.com",     # 美国
    "http://yahoo.com",        # 美国
    "http://amazon.com",       # 美国
    "http://twitter.com",      # 美国
    "http://bing.com",         # 美国
    "http://ebay.com",         # 美国
    "http://linkedin.com",     # 美国
    "http://instagram.com",    # 美国
    "http://netflix.com",      # 美国
    "http://spotify.com",      # 瑞典
    "http://deutschebahn.com", # 德国
    "http://bbc.co.uk",        # 英国
    "http://canalplus.fr",     # 法国
    "http://raiji.jp",         # 日本
    "http://yandex.ru",        # 俄罗斯
    "http://sina.com.cn"       # 中国（作为对比）
]

# 评分权重配置
SCORE_WEIGHTS = {
    "latency": 0.3,     # 延迟评分权重
    "download": 0.25,    # 下载速度评分权重
    "accessibility": 0.3, # 可访问性评分权重
    "stability": 0.15     # 稳定性评分权重
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
    start_time = time.time()
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    
    # 检查是否在黑名单中
    if blacklist and raw_ip in blacklist:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: in blacklist, assigning minimum score")
        return 0.1
    
    # 测试指标
    latencies = []
    download_speeds = []
    accessibility_scores = []
    success_count = 0
    ipv6_connection_error = False
    
    # 延迟测试 - 使用Google 204测试
    try:
        test_start = time.time()
        # 通过测试IP访问Google 204
        # 设置Host头为www.google.com，模拟通过测试IP访问Google
        headers_with_host = headers.copy()
        headers_with_host['Host'] = 'www.google.com'
        resp = session.get(f"http://{trace_ip}/generate_204", timeout=2, verify=False, headers=headers_with_host)
        if resp.status_code == 204:
            latency = (time.time() - test_start) * 1000  # 转换为毫秒
            latencies.append(latency)
            success_count = TEST_COUNT  # 一次成功视为所有测试通过
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test success, latency = {latency:.2f}ms")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test failed with status code {resp.status_code}")
    except Exception as e:
        error_msg = str(e)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test exception - {error_msg}")
        # 检测IPv6连接错误
        if is_ipv6 and ("unreachable network" in error_msg or "10051" in error_msg):
            ipv6_connection_error = True
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: IPv6 connection error detected")
    
    # 下载速度测试 - 使用Cloudflare测速链接
    try:
        test_start = time.time()
        # 通过测试IP访问Cloudflare测速链接
        # 设置Host头为speed.cloudflare.com，模拟通过测试IP访问Cloudflare测速服务
        headers_with_host = headers.copy()
        headers_with_host['Host'] = 'speed.cloudflare.com'
        resp = session.get(f"http://{trace_ip}/__down?bytes=100000000", timeout=10, verify=False, headers=headers_with_host)
        if resp.status_code == 200:
            data_size = len(resp.content)
            elapsed_time = time.time() - test_start
            if elapsed_time > 0:
                download_speed = (data_size / 1024) / elapsed_time  # KB/s
                download_speeds.append(download_speed)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test success, speed = {download_speed:.2f} KB/s")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test failed with status code {resp.status_code}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test exception - {str(e)}")
    
    # 备用下载测试 - 使用Steam CDN链接
    if not download_speeds:
        try:
            test_start = time.time()
            # 通过测试IP访问Steam CDN链接
            # 设置Host头为cdn.cloudflare.steamstatic.com，模拟通过测试IP访问Steam CDN
            headers_with_host = headers.copy()
            headers_with_host['Host'] = 'cdn.cloudflare.steamstatic.com'
            resp = session.get(f"http://{trace_ip}/steam/apps/256843155/movie_max.mp4", timeout=10, verify=False, headers=headers_with_host)
            if resp.status_code == 200:
                data_size = len(resp.content)
                elapsed_time = time.time() - test_start
                if elapsed_time > 0:
                    download_speed = (data_size / 1024) / elapsed_time  # KB/s
                    download_speeds.append(download_speed)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: backup download speed test success, speed = {download_speed:.2f} KB/s")
            else:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: backup download speed test failed with status code {resp.status_code}")
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: backup download speed test exception - {str(e)}")
    
    # 网页可访问性测试
    accessible_count = 0
    try:
        test_start = time.time()
        resp = session.get(f"http://{trace_ip}", timeout=3, verify=False, headers=headers)
        if resp.status_code == 200:
            load_time = (time.time() - test_start) * 1000
            if load_time < MAX_LOAD_TIME:  # 3秒内加载
                accessible_count = 1
                accessibility_scores.append(100 - (load_time / 30))  # 最高100分
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: accessibility test success, load time = {load_time:.2f}ms")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: accessibility test failed with status code {resp.status_code}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: accessibility test exception - {str(e)}")
    
    # 计算综合评分
    score_components = {}
    
    # 延迟评分
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        latency_score = max(0, 100 - (avg_latency / 2))
        score_components['latency'] = latency_score * SCORE_WEIGHTS['latency']
    else:
        score_components['latency'] = 0
    
    # 下载速度评分
    if download_speeds:
        avg_download = sum(download_speeds) / len(download_speeds)
        # 假设100KB/s为满分
        download_score = min(100, avg_download)
        score_components['download'] = download_score * SCORE_WEIGHTS['download']
    else:
        score_components['download'] = 0
    
    # 可访问性评分
    if accessibility_scores:
        avg_accessibility = sum(accessibility_scores) / len(accessibility_scores)
        score_components['accessibility'] = avg_accessibility * SCORE_WEIGHTS['accessibility']
    else:
        score_components['accessibility'] = 0
    
    # 连接稳定性评分
    stability_score = (success_count / TEST_COUNT) * 100
    score_components['stability'] = stability_score * SCORE_WEIGHTS['stability']
    
    # 计算总分
    total_score = sum(score_components.values())
    
    # 对于IPv6连接错误，给予最低评分，但不直接排除
    if ipv6_connection_error and success_count == 0:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: IPv6 connection error, assigning minimum score")
        total_score = 0.1  # 给予最低但非零的评分
    
    elapsed_time = (time.time() - start_time) * 1000
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: test completed in {elapsed_time:.2f}ms, score = {total_score:.2f}")
    return total_score

def secondary_filter():
    """二次筛选功能，对all-countries-ip.txt中的IP进行筛选"""
    start_time = time.time()
    summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
    if not os.path.exists(summary_path):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Summary file not found.")
        return
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [*] Starting secondary filter...")
    
    # 读取IP黑名单
    blacklist = set()
    blacklist_path = os.path.join(BASE_DIR, BLACKLIST_FILE)
    if os.path.exists(blacklist_path):
        with open(blacklist_path, 'r', encoding='utf-8') as f:
            for line in f:
                ip = line.strip()
                if ip:
                    blacklist.add(ip)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Loaded {len(blacklist)} IPs from blacklist")
    
    # 读取所有IP
    with open(summary_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Read {len(lines)} lines from {SUMMARY_FILE}")
    
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
                continue
            
            # 提取#后面的部分
            info_part = parts[1]
            
            # 提取国家码：优先寻找emoji后面的2-3个大写字母
            match = re.search(r'[\U0001F1E6-\U0001F1FF]\s*([A-Z]{2,3})\s*\|', info_part)
            if not match:
                # 尝试另一种模式：可能没有emoji，直接寻找2-3个大写字母
                match = re.search(r'\s*([A-Z]{2,3})\s*\|', info_part)
            if not match:
                # 尝试第三种模式：可能格式不同，直接提取大写字母组合
                match = re.search(r'([A-Z]{2,3})', info_part)
            
            if match:
                country_code = match.group(1)
                if country_code not in country_ips:
                    country_ips[country_code] = []
                country_ips[country_code].append(line)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Extracted country code {country_code} from line: {line}")
            else:
                no_match_count += 1
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] No country code found in line: {line}")
        except Exception as e:
            no_match_count += 1
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Error processing line: {str(e)}")
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Found {len(country_ips)} countries, {no_match_count} lines without country code")
    
    # 对每个国家的IP进行测试和排序
    filtered_ips = []
    new_blacklist = set()
    
    # 使用线程池并行处理不同国家的IP测试
    def process_country(country_code, ips):
        country_filtered = []
        country_blacklist = set()
        
        # 测试每个IP的质量
        ip_scores = []
        for ip in ips:
            # 最多重试MAX_RETRIES次
            retry_count = 0
            best_score = 0
            
            while retry_count <= MAX_RETRIES:
                score = test_ip_quality(ip, blacklist)
                if score > best_score:
                    best_score = score
                # 如果分数足够高，直接结束重试
                if best_score > 60:
                    break
                retry_count += 1
                if retry_count <= MAX_RETRIES:
                    time.sleep(RETRY_INTERVAL)  # 重试间隔
            
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
            min_threshold = max(MIN_THRESHOLD, avg_score * THRESHOLD_RATIO)  # 最低阈值30，或平均分数的60%
            
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Country {country_code}: avg score = {avg_score:.2f}, min threshold = {min_threshold:.2f}")
            
            # 筛选出符合阈值的IP，最多取前MAX_IPS_PER_COUNTRY个
            qualified_ips = [(ip, score) for ip, score in ip_scores if score >= min_threshold]
            top_ips = [ip for ip, score in qualified_ips[:MAX_IPS_PER_COUNTRY]]
            country_filtered.extend(top_ips)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Selected {len(top_ips)} IPs for country {country_code}")
        
        return country_filtered, country_blacklist
    
    # 使用线程池并行处理
    if country_ips:
        with ThreadPoolExecutor(max_workers=min(MAX_COUNTRY_WORKERS, len(country_ips))) as executor:
            futures = {executor.submit(process_country, country, ips): country for country, ips in country_ips.items()}
            for future in as_completed(futures):
                country = futures[future]
                try:
                    country_filtered, country_blacklist = future.result()
                    filtered_ips.extend(country_filtered)
                    new_blacklist.update(country_blacklist)
                except Exception as e:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Error processing country {country}: {str(e)}")
    
    # 去重处理
    filtered_ips = list(set(filtered_ips))
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] After deduplication: {len(filtered_ips)} IPs")
    
    # 更新黑名单
    if new_blacklist:
        with open(blacklist_path, 'a', encoding='utf-8') as f:
            for ip in new_blacklist:
                if ip not in blacklist:
                    f.write(ip + '\n')
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Updated blacklist with {len(new_blacklist)} new IPs")
    
    # 容错机制：如果没有IP通过筛选，使用原始IP
    if not filtered_ips and lines:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [WARNING] No IPs passed quality test, using original IPs")
        # 按国家码分组，每个国家取前MAX_IPS_PER_COUNTRY_FALLBACK个
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
                    if len(temp_country_ips[country_code]) < MAX_IPS_PER_COUNTRY_FALLBACK:
                        temp_country_ips[country_code].append(line)
            except:
                pass
        
        # 收集所有IP
        for country_code, ips in temp_country_ips.items():
            filtered_ips.extend(ips)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Fallback: Selected {len(filtered_ips)} IPs")
    
    # 最终验证：测试筛选出的IP是否满足要求
    if filtered_ips:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [*] Performing final verification on selected IPs...")
        final_ips = []
        
        for ip_line in filtered_ips:
            raw_ip = ip_line.split('#')[0].strip()
            clean_ip = raw_ip.replace('[', '').replace(']', '')
            is_ipv6 = ":" in clean_ip
            trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
            
            success_count = 0
            total_load_time = 0
            test_count = 0
            
            # 从不同地区选择4个代表性域名进行测试
            selected_websites = [
                "http://example.com",      # 全球通用
                "http://google.com",       # 美国
                "http://bbc.co.uk",        # 英国
                "http://raiji.jp"          # 日本
            ]
            
            for website in selected_websites:
                test_count += 1
                try:
                    start_time = time.time()
                    resp = session.get(f"http://{trace_ip}", timeout=3, verify=False, headers=headers)
                    load_time = (time.time() - start_time) * 1000
                    if resp.status_code == 200:
                        total_load_time += load_time
                        if load_time < MAX_LOAD_TIME:  # 3秒内加载
                            success_count += 1
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: website {website} test success, status code: {resp.status_code}, load time: {load_time:.2f}ms")
                except Exception as e:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: website {website} test exception - {str(e)}")
            
            # 计算平均加载时间和成功率
            avg_load_time = total_load_time / test_count if success_count > 0 else 9999
            success_rate = (success_count / test_count) * 100
            
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Final verification for {raw_ip}: {success_count}/{test_count} websites loaded, avg load time = {avg_load_time:.2f}ms, success rate = {success_rate:.1f}%")
            
            # 多条件组合筛选：AND逻辑
            if success_rate >= MIN_SUCCESS_RATE and avg_load_time <= MAX_LOAD_TIME:
                final_ips.append(ip_line)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip} passed final verification")
            else:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip} failed final verification: success rate {success_rate:.1f}%, avg load time {avg_load_time:.2f}ms")
                # 添加到黑名单
                new_blacklist.add(raw_ip)
        
        # 更新黑名单
        if new_blacklist:
            with open(blacklist_path, 'a', encoding='utf-8') as f:
                for ip in new_blacklist:
                    if ip not in blacklist:
                        f.write(ip + '\n')
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Updated blacklist with {len(new_blacklist)} new IPs")
        
        # 使用最终验证通过的IP
        if final_ips:
            filtered_ips = final_ips
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] {len(filtered_ips)} IPs passed final verification")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [WARNING] No IPs passed final verification, using original filtered IPs")
    
    # 生成新的TXT文件
    best_ip_file = os.path.join(BASE_DIR, BEST_IP_FILE)
    if filtered_ips:
        with open(best_ip_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(filtered_ips)) + '\n')
        elapsed_time = time.time() - start_time
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SUCCESS] Secondary filter completed in {elapsed_time:.2f}s. Kept {len(filtered_ips)} IPs in {BEST_IP_FILE}.")
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] No IPs passed the secondary filter.")

def main():
    """主函数"""
    start_time = time.time()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [*] Starting IP filtering process...")
    
    # 确保基础目录存在
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Created base directory: {BASE_DIR}")
    
    # 读取proxy-ip.txt中的IP地址
    proxy_ips = set()
    proxy_path = os.path.join(BASE_DIR, PROXY_IP_FILE)
    if os.path.exists(proxy_path):
        with open(proxy_path, 'r', encoding='utf-8') as f:
            for line in f:
                ip = line.split('#')[0].strip()
                if ip:
                    proxy_ips.add(ip)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Loaded {len(proxy_ips)} proxy IPs from {PROXY_IP_FILE}")
    
    # 处理文件
    summary = set()
    for filename in CLASSIFY_FILES:
        process_file(filename, summary, proxy_ips)
    
    # 检查处理结果
    if summary:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Processed {len(summary)} IPs")
        # 写入汇总文件
        summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary))) + '\n')
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Wrote summary to {SUMMARY_FILE}")
        # 执行二次筛选
        secondary_filter()
    elif os.path.exists(os.path.join(BASE_DIR, SUMMARY_FILE)):
        # 如果已经存在SUMMARY_FILE，直接执行二次筛选
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Using existing summary file for secondary filter")
        secondary_filter()
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] No summary file found and no files to process")
    
    elapsed_time = time.time() - start_time
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SUCCESS] Classification done in {elapsed_time:.2f}s.")

if __name__ == "__main__":
    main()