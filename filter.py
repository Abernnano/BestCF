import requests
import re
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Optional, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from download_manager import (
    DownloadManager,
    DownloadConfig,
    CloudflareSpeedTestWrapper,
    NodeFilter,
    PerformanceMetrics
)

os.environ['no_proxy'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')

CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
BEST_IP_FILE = "best-ip.txt"
BLACKLIST_FILE = "ip-blacklist.txt"
PROXY_IP_FILE = "proxy-ip.txt"
CLOUDFLARE_DIR = "third_party/cloudflare_speedtest"

MAX_WORKERS = 80
MAX_COUNTRY_WORKERS = 10

TEST_COUNT = 2
MAX_RETRIES = 1
RETRY_INTERVAL = 0.2

MIN_THRESHOLD = 25
THRESHOLD_RATIO = 0.5
MIN_SUCCESS_RATE = 50
MAX_LOAD_TIME = 3000

MAX_IPS_PER_COUNTRY = 5
MAX_IPS_PER_COUNTRY_FALLBACK = 5

COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR", "TPE": "TW",
    "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US", "FRA": "DE", "LHR": "GB",
    "CDG": "FR", "AMS": "NL", "IAD": "US", "ORD": "US", "DFW": "US", "EWR": "US"
}

SCORE_WEIGHTS = {
    "latency": 0.3,
    "download": 0.25,
    "accessibility": 0.3,
    "stability": 0.15
}

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


def get_flag(country_code):
    if not country_code or len(country_code) != 2:
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())


def get_ip_location(ip_line):
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    try:
        resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
        if resp.status_code == 200:
            colo = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo:
                return COLO_MAP.get(colo.group(1), colo.group(1))
    except Exception:
        pass

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
                if ip in proxy_ips:
                    continue
                if note.startswith("Global-IPDB") and "V6" not in note:
                    continue
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
    start_time = time.time()
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    
    if blacklist and raw_ip in blacklist:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: in blacklist, assigning minimum score")
        return 0.1
    
    latencies = []
    download_speeds = []
    accessibility_scores = []
    success_count = 0
    ipv6_connection_error = False
    
    latency_links = [
        ("https://www.cloudflare.com:443/generate_204", "Cloudflare"),
        ("https://www.google.com:443/generate_204", "Google"),
        ("http://www.msftconnecttest.com:80/connecttest.txt", "Microsoft")
    ]
    
    download_links = [
        ("https://speed.cloudflare.com:443/__down?bytes=50000000", "Cloudflare 50MB"),
        ("https://cdn.cloudflare.steamstatic.com:443/steam/apps/256843155/movie_max.mp4", "Steam CDN")
    ]
    
    for link, name in latency_links:
        try:
            test_start = time.time()
            
            for retry in range(MAX_RETRIES + 1):
                try:
                    timeout = 2 + (retry * 0.5)
                    resp = session.get(link, timeout=timeout, verify=False, headers=headers)
                    
                    expected_status = 204 if link.endswith('generate_204') else 200
                    if resp.status_code == expected_status:
                        latency = (time.time() - test_start) * 1000
                        latencies.append(latency)
                        success_count = TEST_COUNT
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test with {name} success, latency = {latency:.2f}ms")
                        break
                    
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test with {name} failed with status code {resp.status_code}")
                except Exception as e:
                    error_msg = str(e)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test with {name} exception - {error_msg}")
                    
                if retry < MAX_RETRIES:
                    delay = RETRY_INTERVAL * (2 ** retry)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: Retrying latency test with {name} in {delay:.2f}s...")
                    time.sleep(delay)
            
            if latencies:
                break
        except Exception as e:
            error_msg = str(e)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: latency test loop exception - {error_msg}")
    
    download_test_start = time.time()
    for link, name in download_links:
        try:
            test_start = time.time()
            
            for retry in range(MAX_RETRIES + 1):
                try:
                    elapsed_total = time.time() - download_test_start
                    remaining_time = max(1, 5 - elapsed_total)
                    timeout = min(3, remaining_time)
                    
                    if remaining_time <= 0:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download test time limit reached, stopping")
                        break
                    
                    resp = session.get(link, timeout=timeout, verify=False, headers=headers, stream=True)
                    
                    if resp.status_code == 200:
                        data_size = 0
                        start_download = time.time()
                        
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                data_size += len(chunk)
                            
                            if time.time() - download_test_start > 5:
                                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download test time exceeded 5 seconds, stopping")
                                break
                        
                        elapsed_time = time.time() - start_download
                        if elapsed_time > 0:
                            download_speed = (data_size / 1024) / elapsed_time
                            download_speeds.append(download_speed)
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test with {name} success, speed = {download_speed:.2f} KB/s")
                            break
                    elif resp.status_code == 429:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test with {name} rate limited (429), retrying...")
                        time.sleep(1)
                    else:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test with {name} failed with status code {resp.status_code}")
                except Exception as e:
                    error_msg = str(e)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download speed test with {name} exception - {error_msg}")
                
                if retry < MAX_RETRIES:
                    delay = RETRY_INTERVAL * (2 ** retry)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: Retrying download test with {name} in {delay:.2f}s...")
                    time.sleep(delay)
            
            if download_speeds:
                break
            
            if time.time() - download_test_start > 5:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download test time exceeded 5 seconds, stopping")
                break
        except Exception as e:
            error_msg = str(e)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: download test loop exception - {error_msg}")
    
    if not latencies:
        try:
            test_start = time.time()
            resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
            if resp.status_code == 200:
                latency = (time.time() - test_start) * 1000
                latencies.append(latency)
                success_count = TEST_COUNT
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: local latency test success, latency = {latency:.2f}ms")
            else:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: local latency test failed with status code {resp.status_code}")
        except Exception as e:
            error_msg = str(e)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: local latency test exception - {error_msg}")
            if is_ipv6 and ("unreachable network" in error_msg or "10051" in error_msg):
                ipv6_connection_error = True
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: IPv6 connection error detected")
    
    accessible_count = 0
    try:
        test_start = time.time()
        resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
        if resp.status_code == 200:
            load_time = (time.time() - test_start) * 1000
            if load_time < MAX_LOAD_TIME:
                accessible_count = 1
                accessibility_scores.append(100 - (load_time / 30))
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: accessibility test success, load time = {load_time:.2f}ms")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: accessibility test failed with status code {resp.status_code}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: accessibility test exception - {str(e)}")
    
    score_components = {}
    
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        latency_score = max(0, 100 - (avg_latency / 2))
        score_components['latency'] = latency_score * SCORE_WEIGHTS['latency']
    else:
        score_components['latency'] = 0
    
    if download_speeds:
        avg_download = sum(download_speeds) / len(download_speeds)
        download_score = min(100, avg_download)
        score_components['download'] = download_score * SCORE_WEIGHTS['download']
    else:
        score_components['download'] = 0
    
    if accessibility_scores:
        avg_accessibility = sum(accessibility_scores) / len(accessibility_scores)
        score_components['accessibility'] = avg_accessibility * SCORE_WEIGHTS['accessibility']
    else:
        score_components['accessibility'] = 0
    
    stability_score = (success_count / TEST_COUNT) * 100
    score_components['stability'] = stability_score * SCORE_WEIGHTS['stability']
    
    total_score = sum(score_components.values())
    
    if ipv6_connection_error and success_count == 0:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: IPv6 connection error, assigning minimum score")
        total_score = 0.1
    
    elapsed_time = (time.time() - start_time) * 1000
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: test completed in {elapsed_time:.2f}ms, score = {total_score:.2f}")
    return total_score


def get_cloudflare_speedtest_nodes() -> List[str]:
    """使用本地集成的 CloudflareSpeedTest 获取最佳节点"""
    config = DownloadConfig(target_dir=CLOUDFLARE_DIR)
    manager = DownloadManager(config)
    
    if not manager.is_installed():
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] CloudflareSpeedTest not installed, downloading...")
        success, message = manager.download()
        if not success:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Failed to install CloudflareSpeedTest: {message}")
            return []
        manager.print_metrics()
    
    executable_path = manager.get_executable_path()
    if not executable_path:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] CloudflareSpeedTest executable not found")
        return []
    
    wrapper = CloudflareSpeedTestWrapper(executable_path, BASE_DIR)
    results = wrapper.run_test_sync()
    
    node_filter = NodeFilter(max_latency=300.0, min_speed=1.0, top_n=5)
    filtered_results = node_filter.filter(results)
    
    best_nodes = []
    for result in filtered_results:
        ip = result['ip']
        region_code = result['region_code']
        
        country_code = COLO_MAP.get(region_code, region_code)
        if len(country_code) > 2:
            country_code = country_code[:2]
        
        node_info = f"{ip}#{get_flag(country_code)} {country_code}_优选"
        best_nodes.append(node_info)
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Found {len(best_nodes)} best nodes from CloudflareSpeedTest")
    return best_nodes


def secondary_filter():
    start_time = time.time()
    summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
    if not os.path.exists(summary_path):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Summary file not found.")
        return
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [*] Starting secondary filter...")
    
    blacklist = set()
    blacklist_path = os.path.join(BASE_DIR, BLACKLIST_FILE)
    if os.path.exists(blacklist_path):
        with open(blacklist_path, 'r', encoding='utf-8') as f:
            for line in f:
                ip = line.strip()
                if ip:
                    blacklist.add(ip)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Loaded {len(blacklist)} IPs from blacklist")
    
    with open(summary_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Read {len(lines)} lines from {SUMMARY_FILE}")
    
    country_ips = {}
    no_match_count = 0
    for line in lines:
        try:
            parts = line.split('#', 1)
            if len(parts) < 2:
                no_match_count += 1
                continue
            
            info_part = parts[1]
            
            match = re.search(r'[\U0001F1E6-\U0001F1FF]\s*([A-Z]{2,3})\s*\|', info_part)
            if not match:
                match = re.search(r'\s*([A-Z]{2,3})\s*\|', info_part)
            if not match:
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
    
    filtered_ips = []
    new_blacklist = set()
    
    def process_country(country_code, ips):
        country_filtered = []
        country_blacklist = set()
        
        ip_scores = []
        for ip in ips:
            retry_count = 0
            best_score = 0
            
            while retry_count <= MAX_RETRIES:
                score = test_ip_quality(ip, blacklist)
                if score > best_score:
                    best_score = score
                if best_score > 60:
                    break
                retry_count += 1
                if retry_count <= MAX_RETRIES:
                    time.sleep(RETRY_INTERVAL)
            
            ip_scores.append((ip, best_score))
            
            if best_score < 10:
                ip_addr = ip.split('#')[0].strip()
                country_blacklist.add(ip_addr)
        
        if ip_scores:
            ip_scores.sort(key=lambda x: x[1], reverse=True)
            
            avg_score = sum(score for _, score in ip_scores) / len(ip_scores)
            min_threshold = max(MIN_THRESHOLD, avg_score * THRESHOLD_RATIO)
            
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Country {country_code}: avg score = {avg_score:.2f}, min threshold = {min_threshold:.2f}")
            
            qualified_ips = [(ip, score) for ip, score in ip_scores if score >= min_threshold]
            top_ips = [ip for ip, score in qualified_ips[:MAX_IPS_PER_COUNTRY]]
            
            formatted_ips = []
            for i, ip in enumerate(top_ips):
                parts = ip.split('#')
                if len(parts) >= 2:
                    ip_addr = parts[0]
                    info = parts[1]
                    source = "未知来源"
                    if '|' in info:
                        source_part = info.split('|')[-1].strip()
                        if '_' in source_part:
                            source = '_'.join(source_part.split('_')[:-1])
                        else:
                            source = source_part
                    new_info = f"{get_flag(country_code)} {country_code}_{source}"
                    formatted_ip = f"{ip_addr}#{new_info}"
                    formatted_ips.append(formatted_ip)
                else:
                    formatted_ips.append(ip)
            
            country_filtered.extend(formatted_ips)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Selected {len(formatted_ips)} IPs for country {country_code}")
        
        return country_filtered, country_blacklist
    
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
    
    filtered_ips = list(set(filtered_ips))
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] After deduplication: {len(filtered_ips)} IPs")
    
    if new_blacklist:
        with open(blacklist_path, 'a', encoding='utf-8') as f:
            for ip in new_blacklist:
                if ip not in blacklist:
                    f.write(ip + '\n')
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Updated blacklist with {len(new_blacklist)} new IPs")
    
    if not filtered_ips and lines:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [WARNING] No IPs passed quality test, using original IPs")
        temp_country_ips = {}
        for line in lines:
            try:
                parts = line.split('#', 1)
                if len(parts) < 2:
                    continue
                
                info_part = parts[1]
                
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
        
        for country_code, ips in temp_country_ips.items():
            filtered_ips.extend(ips)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Fallback: Selected {len(filtered_ips)} IPs")
    
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
            
            final_latency_links = [
                ("https://www.cloudflare.com:443/generate_204", "Cloudflare"),
                ("https://www.google.com:443/generate_204", "Google"),
                ("http://www.msftconnecttest.com:80/connecttest.txt", "Microsoft")
            ]
            
            final_download_links = [
                ("https://speed.cloudflare.com:443/__down?bytes=50000000", "Cloudflare 50MB"),
                ("https://cdn.cloudflare.steamstatic.com:443/steam/apps/256843155/movie_max.mp4", "Steam CDN")
            ]
            
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
            
            download_success = False
            download_test_start = time.time()
            for link, name in final_download_links:
                test_count += 1
                try:
                    test_start = time.time()
                    
                    for retry in range(MAX_RETRIES + 1):
                        try:
                            elapsed_total = time.time() - download_test_start
                            remaining_time = max(1, 5 - elapsed_total)
                            timeout = min(3, remaining_time)
                            
                            if remaining_time <= 0:
                                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test time limit reached, stopping")
                                break
                            
                            resp = session.get(link, timeout=timeout, verify=False, headers=headers, stream=True)
                            
                            if resp.status_code == 200:
                                data_size = 0
                                start_download = time.time()
                                
                                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                                    if chunk:
                                        data_size += len(chunk)
                                    
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
                    
                    if time.time() - download_test_start > 5:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test time exceeded 5 seconds, stopping")
                        break
                except Exception as e:
                    error_msg = str(e)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip}: final download test loop exception - {error_msg}")
            
            avg_load_time = total_load_time / test_count if success_count > 0 else 9999
            success_rate = (success_count / test_count) * 100
            
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] Final verification for {raw_ip}: {success_count}/{test_count} tests passed, avg load time = {avg_load_time:.2f}ms, success rate = {success_rate:.1f}%")
            
            if success_rate >= MIN_SUCCESS_RATE and avg_load_time <= MAX_LOAD_TIME:
                final_ips.append(ip_line)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip} passed final verification")
            else:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [DEBUG] {raw_ip} failed final verification: success rate {success_rate:.1f}%, avg load time {avg_load_time:.2f}ms")
                new_blacklist.add(raw_ip)
        
        if new_blacklist:
            with open(blacklist_path, 'a', encoding='utf-8') as f:
                for ip in new_blacklist:
                    if ip not in blacklist:
                        f.write(ip + '\n')
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Updated blacklist with {len(new_blacklist)} new IPs")
        
        if final_ips:
            filtered_ips = final_ips
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] {len(filtered_ips)} IPs passed final verification")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [WARNING] No IPs passed final verification, using original filtered IPs")
    
    cfst_nodes = get_cloudflare_speedtest_nodes()
    
    if cfst_nodes:
        combined_ips = list(set(filtered_ips + cfst_nodes))
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Combined {len(combined_ips)} IPs from secondary filter and CloudflareSpeedTest")
    else:
        combined_ips = filtered_ips
    
    best_ip_file = os.path.join(BASE_DIR, BEST_IP_FILE)
    if combined_ips:
        with open(best_ip_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(combined_ips)) + '\n')
        elapsed_time = time.time() - start_time
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SUCCESS] Secondary filter completed in {elapsed_time:.2f}s. Kept {len(combined_ips)} IPs in {BEST_IP_FILE}.")
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] No IPs passed the secondary filter.")


def main():
    start_time = time.time()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [*] Starting IP filtering process...")
    
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Created base directory: {BASE_DIR}")
    
    proxy_ips = set()
    proxy_path = os.path.join(BASE_DIR, PROXY_IP_FILE)
    if os.path.exists(proxy_path):
        with open(proxy_path, 'r', encoding='utf-8') as f:
            for line in f:
                ip = line.split('#')[0].strip()
                if ip:
                    proxy_ips.add(ip)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Loaded {len(proxy_ips)} proxy IPs from {PROXY_IP_FILE}")
    
    today = time.strftime('%Y-%m-%d')
    last_run_file = os.path.join(BASE_DIR, 'last_run.txt')
    need_base_filter = True
    
    if os.path.exists(last_run_file):
        with open(last_run_file, 'r', encoding='utf-8') as f:
            last_run = f.read().strip()
        if last_run == today:
            need_base_filter = False
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Base filter already executed today, skipping...")
    
    summary = set()
    if need_base_filter:
        for filename in CLASSIFY_FILES:
            process_file(filename, summary, proxy_ips)
        
        if summary:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Processed {len(summary)} IPs")
            summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(sorted(list(summary))) + '\n')
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Wrote summary to {SUMMARY_FILE}")
            with open(last_run_file, 'w', encoding='utf-8') as f:
                f.write(today)
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] No IPs processed")
    
    if os.path.exists(os.path.join(BASE_DIR, SUMMARY_FILE)):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Starting secondary filter...")
        secondary_filter()
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] No summary file found")
    
    elapsed_time = time.time() - start_time
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SUCCESS] Classification done in {elapsed_time:.2f}s.")


if __name__ == "__main__":
    main()
