import requests
import re
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制直连：屏蔽系统代理
os.environ['no_proxy'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')

# 文件路径配置
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
BEST_IP_FILE = "best-ip.txt"
BLACKLIST_FILE = "ip-blacklist.txt"
PROXY_IP_FILE = "proxy-ip.txt"

# 线程池配置
MAX_WORKERS = 80
MAX_COUNTRY_WORKERS = 10

# 测试配置
TEST_COUNT = 2
MAX_RETRIES = 1
RETRY_INTERVAL = 0.2

# 筛选阈值配置
MIN_THRESHOLD = 25
THRESHOLD_RATIO = 0.5
MIN_SUCCESS_RATE = 50
MAX_LOAD_TIME = 3000

# IP数量配置
MAX_IPS_PER_COUNTRY = 5  # 每个国家最多保留的IP数量
MAX_IPS_PER_COUNTRY_FALLBACK = 5

# 国家代码映射
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR", "TPE": "TW",
    "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US", "FRA": "DE", "LHR": "GB",
    "CDG": "FR", "AMS": "NL", "IAD": "US", "ORD": "US", "DFW": "US", "EWR": "US"
}

# 评分权重配置
SCORE_WEIGHTS = {
    "latency": 0.3,     # 延迟评分权重
    "download": 0.25,    # 下载速度评分权重
    "accessibility": 0.3, # 可访问性评分权重
    "stability": 0.15     # 稳定性评分权重
}

# 忽略SSL证书验证警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

session = requests.Session()
session.trust_env = False 
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive'
}

# CloudflareSpeedTest 相关配置
CLOUDFLARE_SPEED_TEST_URL = "https://github.com/XIU2/CloudflareSpeedTest/releases/latest/download/"
CLOUDFLARE_SPEED_TEST_EXEC = "cfst.exe" if sys.platform.startswith('win') else "cfst"
CLOUDFLARE_SPEED_TEST_RESULT = os.path.join(BASE_DIR, "cfst_result.txt")

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_cloudflare_speedtest_nodes():
    """使用 CloudflareSpeedTest 获取最佳节点"""
    import subprocess
    import platform
    
    cfst_exec = os.path.join(BASE_DIR, CLOUDFLARE_SPEED_TEST_EXEC)
    
    # 检查是否存在 CloudflareSpeedTest 可执行文件
    if not os.path.exists(cfst_exec):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] CloudflareSpeedTest not found, downloading...")
        
        # 确定下载 URL
        if platform.system() == "Windows":
            download_url = CLOUDFLARE_SPEED_TEST_URL + "cfst_windows_amd64.zip"
        elif platform.system() == "Linux":
            download_url = CLOUDFLARE_SPEED_TEST_URL + "cfst_linux_amd64.tar.gz"
        elif platform.system() == "Darwin":
            download_url = CLOUDFLARE_SPEED_TEST_URL + "cfst_darwin_amd64.tar.gz"
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Unsupported platform: {platform.system()}")
            return []
        
        # 下载文件
        try:
            import zipfile
            import tarfile
            
            temp_file = os.path.join(BASE_DIR, "cfst_temp")
            if platform.system() == "Windows":
                temp_file += ".zip"
            else:
                temp_file += ".tar.gz"
            
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Downloading CloudflareSpeedTest from {download_url}")
            resp = session.get(download_url, stream=True, headers=headers)
            with open(temp_file, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
            
            # 解压文件
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Extracting CloudflareSpeedTest")
            if platform.system() == "Windows":
                with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                    zip_ref.extractall(BASE_DIR)
            else:
                with tarfile.open(temp_file, 'r:gz') as tar_ref:
                    tar_ref.extractall(BASE_DIR)
            
            # 清理临时文件
            os.remove(temp_file)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] CloudflareSpeedTest downloaded successfully")
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Failed to download CloudflareSpeedTest: {str(e)}")
            return []
    
    # 运行 CloudflareSpeedTest
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Running CloudflareSpeedTest...")
    try:
        # 运行 CloudflareSpeedTest 并获取结果
        result = subprocess.run(
            [cfst_exec, "-tl", "200", "-dn", "20", "-o", CLOUDFLARE_SPEED_TEST_RESULT],
            capture_output=True,
            text=True,
            cwd=BASE_DIR
        )
        
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] CloudflareSpeedTest completed with return code: {result.returncode}")
        
        # 解析结果
        if os.path.exists(CLOUDFLARE_SPEED_TEST_RESULT):
            with open(CLOUDFLARE_SPEED_TEST_RESULT, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 提取最佳的 5 个节点
            best_nodes = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith("IP") or line.startswith("-"):
                    continue
                
                # 解析行数据
                parts = line.split()
                if len(parts) >= 6:
                    ip = parts[0]
                    latency = float(parts[4])
                    speed = float(parts[5])
                    country_code = parts[6]
                    
                    # 构建节点信息，使用国家码_优选格式
                    node_info = f"{ip}#{get_flag(country_code)} {country_code}_优选"
                    best_nodes.append((latency, speed, node_info))
            
            # 按延迟和速度排序，取前 5 个
            best_nodes.sort(key=lambda x: (x[0], -x[1]))
            best_nodes = [node[2] for node in best_nodes[:5]]
            
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Found {len(best_nodes)} best nodes from CloudflareSpeedTest")
            return best_nodes
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] CloudflareSpeedTest result file not found")
            return []
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Failed to run CloudflareSpeedTest: {str(e)}")
        return []

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
    except Exception:
        pass

    # 保底：在线 API (处理本地无 v6 环境)
    try:
        resp = session.get(f"http://ip-api.com/json/{clean_ip}?fields=countryCode", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("countryCode")
    except Exception:
        pass
    return None

def process_file(filename, summary_set, proxy_ips):
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path):
        return
    print(f"[*] Processing: {filename}")
    with open(path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(get_ip_location, l): l for l in lines}
        for future in as_completed(futures):
            line = futures[future]
            tag = future.result()
            if tag:
                ip = line.split('#')[0].strip()
                note = line.split('#')[1].strip() if '#' in line else "Worker"
                # 排除proxy-ip.txt中的IP和IPDB服务的IPv4地址
                if ip in proxy_ips:
                    continue
                if note.startswith("Global-IPDB") and "V6" not in note:
                    continue
                # 排除Proxy-IPDB开头的IP（反代IP）
                if note.startswith("Proxy-IPDB"):
                    continue
                final = f"{ip}#{get_flag(tag)} {tag} | {note}"
                if tag not in categorized:
                    categorized[tag] = []
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
    
    # 延迟测试链接列表
    latency_links = [
        ("https://www.cloudflare.com:443/generate_204", "Cloudflare"),
        ("https://www.google.com:443/generate_204", "Google"),
        ("http://www.msftconnecttest.com:80/connecttest.txt", "Microsoft")
    ]
    
    # 下载速度测试链接列表
    download_links = [
        ("https://speed.cloudflare.com:443/__down?bytes=50000000", "Cloudflare 50MB"),
        ("https://cdn.cloudflare.steamstatic.com:443/steam/apps/256843155/movie_max.mp4", "Steam CDN")
    ]
    
    # 延迟测试 - 实施链接fallback机制
    for link, name in latency_links:
        try:
            test_start = time.time()
            
            for retry in range(MAX_RETRIES + 1):
                try:
                    # 动态调整超时时间
                    timeout = 2 + (retry * 0.5)
                    resp = session.get(link, timeout=timeout, verify=False, headers=headers)
                    
                    # 检查响应状态码
                    expected_status = 204 if link.endswith('generate_204') else 200
                    if resp.status_code == expected_status:
                        latency = (time.time() - test_start) * 1000  # 转换为毫秒
                        latencies.append(latency)
                        success_count = TEST_COUNT  # 一次成功视为所有测试通过
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test with {name} success, latency = {latency:.2f}ms")
                        break
                    
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test with {name} failed with status code {resp.status_code}")
                except Exception as e:
                    error_msg = str(e)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test with {name} exception - {error_msg}")
                    
                # 指数退避
                if retry < MAX_RETRIES:
                    delay = RETRY_INTERVAL * (2 ** retry)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: Retrying latency test with {name} in {delay:.2f}s...")
                    time.sleep(delay)
            
            if latencies:
                break
        except Exception as e:
            error_msg = str(e)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test loop exception - {error_msg}")
    
    # 下载速度测试 - 实施链接fallback机制
    download_test_start = time.time()
    for link, name in download_links:
        try:
            test_start = time.time()
            
            for retry in range(MAX_RETRIES + 1):
                try:
                    # 动态调整超时时间，确保总时间不超过5秒
                    elapsed_total = time.time() - download_test_start
                    remaining_time = max(1, 5 - elapsed_total)
                    timeout = min(3, remaining_time)
                    
                    # 中断测试如果剩余时间不足
                    if remaining_time <= 0:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download test time limit reached, stopping")
                        break
                    
                    resp = session.get(link, timeout=timeout, verify=False, headers=headers, stream=True)
                    
                    if resp.status_code == 200:
                        # 限制下载数据量，确保测试时间在5秒以内
                        data_size = 0
                        start_download = time.time()
                        
                        # 读取数据，直到达到时间限制或数据量限制
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                            if chunk:
                                data_size += len(chunk)
                            
                            # 检查是否超过时间限制
                            if time.time() - download_test_start > 5:
                                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download test time exceeded 5 seconds, stopping")
                                break
                        
                        elapsed_time = time.time() - start_download
                        if elapsed_time > 0:
                            download_speed = (data_size / 1024) / elapsed_time  # KB/s
                            download_speeds.append(download_speed)
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test with {name} success, speed = {download_speed:.2f} KB/s")
                            break
                    elif resp.status_code == 429:
                        # 处理速率限制错误
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test with {name} rate limited (429), retrying...")
                        # 增加延迟以应对速率限制
                        time.sleep(1)
                    else:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test with {name} failed with status code {resp.status_code}")
                except Exception as e:
                    error_msg = str(e)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test with {name} exception - {error_msg}")
                
                # 指数退避
                if retry < MAX_RETRIES:
                    delay = RETRY_INTERVAL * (2 ** retry)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: Retrying download test with {name} in {delay:.2f}s...")
                    time.sleep(delay)
            
            if download_speeds:
                break
            
            # 检查总时间是否超过5秒
            if time.time() - download_test_start > 5:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download test time exceeded 5 seconds, stopping")
                break
        except Exception as e:
            error_msg = str(e)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download test loop exception - {error_msg}")
    
    # 备用延迟测试 - 如果所有外部链接都失败，使用本地测试
    if not latencies:
        try:
            test_start = time.time()
            resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
            if resp.status_code == 200:
                latency = (time.time() - test_start) * 1000  # 转换为毫秒
                latencies.append(latency)
                success_count = TEST_COUNT  # 一次成功视为所有测试通过
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: local latency test success, latency = {latency:.2f}ms")
            else:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: local latency test failed with status code {resp.status_code}")
        except Exception as e:
            error_msg = str(e)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: local latency test exception - {error_msg}")
            # 检测IPv6连接错误
            if is_ipv6 and ("unreachable network" in error_msg or "10051" in error_msg):
                ipv6_connection_error = True
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: IPv6 connection error detected")
    
    # 网页可访问性测试 - 简化为基础连接测试
    accessible_count = 0
    try:
        test_start = time.time()
        resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
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
            else:
                no_match_count += 1
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
            min_threshold = max(MIN_THRESHOLD, avg_score * THRESHOLD_RATIO)
            
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Country {country_code}: avg score = {avg_score:.2f}, min threshold = {min_threshold:.2f}")
            
            # 筛选出符合阈值的IP，最多取前MAX_IPS_PER_COUNTRY个
            qualified_ips = [(ip, score) for ip, score in ip_scores if score >= min_threshold]
            top_ips = [ip for ip, score in qualified_ips[:MAX_IPS_PER_COUNTRY]]
            
            # 确保每个国家码只保留性能最优的5个节点
            # 并按照"国家码_筛选来源"的命名规范对节点进行命名
            formatted_ips = []
            for i, ip in enumerate(top_ips):
                parts = ip.split('#')
                if len(parts) >= 2:
                    ip_addr = parts[0]
                    info = parts[1]
                    # 提取筛选来源：从原始信息中获取
                    # 原始信息格式："国旗 国家码 | 筛选来源_序号"
                    source = "未知来源"
                    # 尝试从原始信息中提取筛选来源
                    if '|' in info:
                        # 格式：国旗 国家码 | 筛选来源_序号
                        source_part = info.split('|')[-1].strip()
                        # 从来源部分提取，去掉序号部分
                        if '_' in source_part:
                            source = '_'.join(source_part.split('_')[:-1])
                        else:
                            source = source_part
                    # 重新格式化节点名称
                    new_info = f"{get_flag(country_code)} {country_code}_{source}"
                    formatted_ip = f"{ip_addr}#{new_info}"
                    formatted_ips.append(formatted_ip)
                else:
                    formatted_ips.append(ip)
            
            country_filtered.extend(formatted_ips)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Selected {len(formatted_ips)} IPs for country {country_code}")
        
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
            
            # 最终验证测试链接列表
            final_latency_links = [
                ("https://www.cloudflare.com:443/generate_204", "Cloudflare"),
                ("https://www.google.com:443/generate_204", "Google"),
                ("http://www.msftconnecttest.com:80/connecttest.txt", "Microsoft")
            ]
            
            final_download_links = [
                ("https://speed.cloudflare.com:443/__down?bytes=50000000", "Cloudflare 50MB"),
                ("https://cdn.cloudflare.steamstatic.com:443/steam/apps/256843155/movie_max.mp4", "Steam CDN")
            ]
            
            # 延迟测试
            latency_success = False
            for link, name in final_latency_links:
                test_count += 1
                try:
                    start_time = time.time()
                    
                    for retry in range(MAX_RETRIES + 1):
                        try:
                            timeout = 3 + (retry * 0.5)
                            resp = session.get(link, timeout=timeout, verify=False, headers=headers)
                            
                            expected_status = 204 if link.endswith('generate_204') else 200
                            if resp.status_code == expected_status:
                                load_time = (time.time() - start_time) * 1000
                                total_load_time += load_time
                                if load_time < MAX_LOAD_TIME:
                                    success_count += 1
                                    latency_success = True
                                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final latency test with {name} success, status code: {resp.status_code}, load time: {load_time:.2f}ms")
                                break
                            
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final latency test with {name} failed with status code {resp.status_code}")
                        except Exception as e:
                            error_msg = str(e)
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final latency test with {name} exception - {error_msg}")
                        
                        if retry < MAX_RETRIES:
                            delay = RETRY_INTERVAL * (2 ** retry)
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: Retrying final latency test with {name} in {delay:.2f}s...")
                            time.sleep(delay)
                    
                    if latency_success:
                        break
                except Exception as e:
                    error_msg = str(e)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final latency test loop exception - {error_msg}")
            
            # 下载速度测试
            download_success = False
            download_test_start = time.time()
            for link, name in final_download_links:
                test_count += 1
                try:
                    test_start = time.time()
                    
                    for retry in range(MAX_RETRIES + 1):
                        try:
                            # 动态调整超时时间，确保总时间不超过5秒
                            elapsed_total = time.time() - download_test_start
                            remaining_time = max(1, 5 - elapsed_total)
                            timeout = min(3, remaining_time)
                            
                            # 中断测试如果剩余时间不足
                            if remaining_time <= 0:
                                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test time limit reached, stopping")
                                break
                            
                            resp = session.get(link, timeout=timeout, verify=False, headers=headers, stream=True)
                            
                            if resp.status_code == 200:
                                # 限制下载数据量，确保测试时间在5秒以内
                                data_size = 0
                                start_download = time.time()
                                
                                # 读取数据，直到达到时间限制或数据量限制
                                for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                                    if chunk:
                                        data_size += len(chunk)
                                    
                                    # 检查是否超过时间限制
                                    if time.time() - download_test_start > 5:
                                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test time exceeded 5 seconds, stopping")
                                        break
                                
                                load_time = (time.time() - start_download) * 1000
                                total_load_time += load_time
                                if load_time < MAX_LOAD_TIME:
                                    success_count += 1
                                    download_success = True
                                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test with {name} success, status code: {resp.status_code}, load time: {load_time:.2f}ms")
                                break
                            elif resp.status_code == 429:
                                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test with {name} rate limited (429), retrying...")
                                time.sleep(1)
                            else:
                                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test with {name} failed with status code {resp.status_code}")
                        except Exception as e:
                            error_msg = str(e)
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test with {name} exception - {error_msg}")
                        
                        if retry < MAX_RETRIES:
                            delay = RETRY_INTERVAL * (2 ** retry)
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: Retrying final download test with {name} in {delay:.2f}s...")
                            time.sleep(delay)
                    
                    if download_success:
                        break
                    
                    # 检查总时间是否超过5秒
                    if time.time() - download_test_start > 5:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test time exceeded 5 seconds, stopping")
                        break
                except Exception as e:
                    error_msg = str(e)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test loop exception - {error_msg}")
            
            # 计算平均加载时间和成功率
            avg_load_time = total_load_time / test_count if success_count > 0 else 9999
            success_rate = (success_count / test_count) * 100
            
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Final verification for {raw_ip}: {success_count}/{test_count} tests passed, avg load time = {avg_load_time:.2f}ms, success rate = {success_rate:.1f}%")
            
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
    
    # 获取 CloudflareSpeedTest 最佳节点
    cfst_nodes = get_cloudflare_speedtest_nodes()
    
    # 整合结果
    if cfst_nodes:
        # 合并并去重
        combined_ips = list(set(filtered_ips + cfst_nodes))
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Combined {len(combined_ips)} IPs from secondary filter and CloudflareSpeedTest")
    else:
        combined_ips = filtered_ips
    
    # 生成新的TXT文件
    best_ip_file = os.path.join(BASE_DIR, BEST_IP_FILE)
    if combined_ips:
        with open(best_ip_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(combined_ips)) + '\n')
        elapsed_time = time.time() - start_time
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SUCCESS] Secondary filter completed in {elapsed_time:.2f}s. Kept {len(combined_ips)} IPs in {BEST_IP_FILE}.")
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
    
    # 每日仅执行一次IP基础筛选的机制
    today = time.strftime('%Y-%m-%d')
    last_run_file = os.path.join(BASE_DIR, 'last_run.txt')
    need_base_filter = True
    
    if os.path.exists(last_run_file):
        with open(last_run_file, 'r', encoding='utf-8') as f:
            last_run = f.read().strip()
        if last_run == today:
            need_base_filter = False
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Base filter already executed today, skipping...")
    
    # 处理文件
    summary = set()
    if need_base_filter:
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
            # 更新最后运行时间
            with open(last_run_file, 'w', encoding='utf-8') as f:
                f.write(today)
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] No IPs processed")
    
    # 执行二次筛选
    if os.path.exists(os.path.join(BASE_DIR, SUMMARY_FILE)):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Starting secondary filter...")
        secondary_filter()
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] No summary file found")
    
    elapsed_time = time.time() - start_time
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SUCCESS] Classification done in {elapsed_time:.2f}s.")

if __name__ == "__main__":
    main()