import requests
import re
import os
import sys
import time
import json
import pickle
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Set, Tuple, Optional

os.environ['no_proxy'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Config:
    BASE_DIR = "./bestcf"
    CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
    SUMMARY_FILE = "all-countries-ip.txt"
    BEST_IP_FILE = "best-ip.txt"
    BLACKLIST_FILE = "ip-blacklist.txt"
    PROXY_IP_FILE = "proxy-ip.txt"
    CACHE_FILE = "ip_cache.pkl"
    
    MAX_WORKERS = 80
    MAX_COUNTRY_WORKERS = 10
    TEST_COUNT = 2
    MAX_RETRIES = 1
    RETRY_INTERVAL = 0.2
    
    MIN_THRESHOLD = 25
    THRESHOLD_RATIO = 0.5
    MIN_SUCCESS_RATE = 50
    MAX_LOAD_TIME = 3000
    
    MAX_IPS_PER_COUNTRY = 10
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
    
    LATENCY_LINKS = [
        ("https://www.cloudflare.com:443/generate_204", "Cloudflare"),
        ("https://www.google.com:443/generate_204", "Google"),
        ("http://www.msftconnecttest.com:80/connecttest.txt", "Microsoft")
    ]
    
    DOWNLOAD_LINKS = [
        ("https://speed.cloudflare.com:443/__down?bytes=5000000", "Cloudflare 5MB")
    ]
    
    @staticmethod
    def should_run_at_desired_time() -> bool:
        now = datetime.now()
        beijing_time = now.astimezone()
        return beijing_time.hour == 2


class Logger:
    DEBUG = False
    
    @staticmethod
    def log(msg: str, level: str = "INFO") -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")
    
    @staticmethod
    def debug(msg: str) -> None:
        if Logger.DEBUG:
            Logger.log(msg, "DEBUG")
    
    @staticmethod
    def info(msg: str) -> None:
        Logger.log(msg, "INFO")
    
    @staticmethod
    def warning(msg: str) -> None:
        Logger.log(msg, "WARNING")
    
    @staticmethod
    def error(msg: str) -> None:
        Logger.log(msg, "ERROR")
    
    @staticmethod
    def success(msg: str) -> None:
        Logger.log(msg, "SUCCESS")


class CacheManager:
    def __init__(self, cache_file: str):
        self.cache_file = cache_file
        self.cache: Dict = {}
        self._load()
    
    def _load(self) -> None:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'rb') as f:
                    self.cache = pickle.load(f)
            except Exception:
                self.cache = {}
    
    def _save(self) -> None:
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
        except Exception as e:
            Logger.warning(f"Failed to save cache: {e}")
    
    def get(self, key: str, max_age_hours: int = 24) -> Optional:
        if key not in self.cache:
            return None
        data, timestamp = self.cache[key]
        if (datetime.now() - timestamp).total_seconds() > max_age_hours * 3600:
            return None
        return data
    
    def set(self, key: str, value) -> None:
        self.cache[key] = (value, datetime.now())
        self._save()


session = requests.Session()
session.trust_env = False
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive'
}


def get_flag(country_code: str) -> str:
    if not country_code or len(country_code) != 2:
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())


def get_ip_location(ip_line: str, cache: CacheManager) -> Optional[str]:
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    cache_key = f"loc_{clean_ip}"
    
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    is_ipv6 = ":" in clean_ip
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    
    try:
        resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
        if resp.status_code == 200:
            colo = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo:
                country = Config.COLO_MAP.get(colo.group(1), colo.group(1))
                cache.set(cache_key, country)
                return country
    except Exception:
        pass
    
    try:
        resp = session.get(f"http://ip-api.com/json/{clean_ip}?fields=countryCode", timeout=3)
        if resp.status_code == 200:
            country = resp.json().get("countryCode")
            if country:
                cache.set(cache_key, country)
                return country
    except Exception:
        pass
    
    return None


def test_latency(ip_line: str, timeout: float = 3) -> Tuple[List[float], int]:
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    
    latencies = []
    success_count = 0
    
    for link, name in Config.LATENCY_LINKS:
        try:
            test_start = time.time()
            for retry in range(Config.MAX_RETRIES + 1):
                try:
                    t = timeout + (retry * 0.5)
                    resp = session.get(link, timeout=t, verify=False, headers=headers)
                    if (link.endswith('generate_204') and resp.status_code == 204) or \
                       (not link.endswith('generate_204') and resp.status_code == 200):
                        latency = (time.time() - test_start) * 1000
                        latencies.append(latency)
                        success_count = Config.TEST_COUNT
                        Logger.debug(f"{raw_ip}: latency {latency:.2f}ms via {name}")
                        return latencies, success_count
                except Exception as e:
                    Logger.debug(f"{raw_ip}: latency fail with {name}: {e}")
                    if retry < Config.MAX_RETRIES:
                        time.sleep(Config.RETRY_INTERVAL * (2 ** retry))
            if latencies:
                break
        except Exception:
            pass
    
    try:
        test_start = time.time()
        resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
        if resp.status_code == 200:
            latency = (time.time() - test_start) * 1000
            latencies.append(latency)
            success_count = Config.TEST_COUNT
    except Exception:
        pass
    
    return latencies, success_count


def test_download_speed(ip_line: str, max_time: float = 5) -> List[float]:
    raw_ip = ip_line.split('#')[0].strip()
    speeds = []
    test_start = time.time()
    
    for link, name in Config.DOWNLOAD_LINKS:
        if time.time() - test_start > max_time:
            break
        try:
            for retry in range(Config.MAX_RETRIES + 1):
                remaining = max(1, max_time - (time.time() - test_start))
                if remaining <= 0:
                    break
                try:
                    t = min(3, remaining)
                    resp = session.get(link, timeout=t, verify=False, headers=headers, stream=True)
                    if resp.status_code == 200:
                        data_size = 0
                        dl_start = time.time()
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                data_size += len(chunk)
                            if time.time() - test_start > max_time:
                                break
                        elapsed = time.time() - dl_start
                        if elapsed > 0:
                            speed = (data_size / 1024) / elapsed
                            speeds.append(speed)
                            Logger.debug(f"{raw_ip}: {speed:.2f} KB/s via {name}")
                            return speeds
                    elif resp.status_code == 429:
                        time.sleep(1)
                except Exception as e:
                    Logger.debug(f"{raw_ip}: download fail with {name}: {e}")
                    if retry < Config.MAX_RETRIES:
                        time.sleep(Config.RETRY_INTERVAL * (2 ** retry))
            if speeds:
                break
        except Exception:
            pass
    
    return speeds


def test_accessibility(ip_line: str) -> List[float]:
    raw_ip = ip_line.split('#')[0].strip()
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    scores = []
    
    try:
        test_start = time.time()
        resp = session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
        if resp.status_code == 200:
            load_time = (time.time() - test_start) * 1000
            if load_time < Config.MAX_LOAD_TIME:
                scores.append(100 - (load_time / 30))
    except Exception as e:
        Logger.debug(f"{raw_ip}: accessibility fail: {e}")
    
    return scores


def test_ip_quality(ip_line: str, blacklist: Optional[Set[str]] = None, cache: Optional[CacheManager] = None) -> float:
    raw_ip = ip_line.split('#')[0].strip()
    if blacklist and raw_ip in blacklist:
        Logger.debug(f"{raw_ip}: in blacklist")
        return 0.1
    
    if cache:
        cached = cache.get(f"score_{raw_ip}", max_age_hours=12)
        if cached is not None:
            return cached
    
    latencies, success_count = test_latency(ip_line)
    download_speeds = test_download_speed(ip_line)
    accessibility_scores = test_accessibility(ip_line)
    
    components = {}
    
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        components['latency'] = max(0, 100 - (avg_latency / 2)) * Config.SCORE_WEIGHTS['latency']
    else:
        components['latency'] = 0
    
    if download_speeds:
        avg_download = sum(download_speeds) / len(download_speeds)
        components['download'] = min(100, avg_download) * Config.SCORE_WEIGHTS['download']
    else:
        components['download'] = 0
    
    if accessibility_scores:
        avg_accessibility = sum(accessibility_scores) / len(accessibility_scores)
        components['accessibility'] = avg_accessibility * Config.SCORE_WEIGHTS['accessibility']
    else:
        components['accessibility'] = 0
    
    components['stability'] = (success_count / Config.TEST_COUNT) * 100 * Config.SCORE_WEIGHTS['stability']
    
    total = sum(components.values())
    if cache:
        cache.set(f"score_{raw_ip}", total)
    Logger.debug(f"{raw_ip}: score = {total:.2f}")
    return total


def load_blacklist() -> Set[str]:
    blacklist = set()
    path = os.path.join(Config.BASE_DIR, Config.BLACKLIST_FILE)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                ip = line.strip()
                if ip:
                    blacklist.add(ip)
        Logger.info(f"Loaded {len(blacklist)} IPs from blacklist")
    return blacklist


def save_blacklist(blacklist: Set[str], new_ips: Set[str]) -> None:
    path = os.path.join(Config.BASE_DIR, Config.BLACKLIST_FILE)
    with open(path, 'a', encoding='utf-8') as f:
        for ip in new_ips:
            if ip not in blacklist:
                f.write(ip + '\n')
    if new_ips:
        Logger.info(f"Updated blacklist with {len(new_ips)} new IPs")


def load_proxy_ips() -> Set[str]:
    proxy_ips = set()
    path = os.path.join(Config.BASE_DIR, Config.PROXY_IP_FILE)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                ip = line.split('#')[0].strip()
                if ip:
                    proxy_ips.add(ip)
        Logger.info(f"Loaded {len(proxy_ips)} proxy IPs")
    return proxy_ips


def process_file(filename: str, summary_set: Set[str], proxy_ips: Set[str], cache: CacheManager) -> None:
    path = os.path.join(Config.BASE_DIR, filename)
    if not os.path.exists(path):
        return
    Logger.info(f"Processing: {filename}")
    
    with open(path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    categorized = {}
    with ThreadPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
        futures = {executor.submit(get_ip_location, l, cache): l for l in lines}
        for f in as_completed(futures):
            line = futures[f]
            tag = f.result()
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
        tag_dir = os.path.join(Config.BASE_DIR, tag)
        os.makedirs(tag_dir, exist_ok=True)
        with open(os.path.join(tag_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')


def extract_country_code(line: str) -> Optional[str]:
    try:
        parts = line.split('#', 1)
        if len(parts) < 2:
            return None
        info_part = parts[1]
        match = re.search(r'[\U0001F1E6-\U0001F1FF]\s*([A-Z]{2,3})\s*\|', info_part)
        if not match:
            match = re.search(r'\s*([A-Z]{2,3})\s*\|', info_part)
        if not match:
            match = re.search(r'([A-Z]{2,3})', info_part)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def process_country(country_code: str, ips: List[str], blacklist: Set[str], cache: CacheManager) -> Tuple[List[str], Set[str]]:
    filtered = []
    country_blacklist = set()
    ip_scores = []
    
    for ip in ips:
        best_score = 0
        for retry in range(Config.MAX_RETRIES + 1):
            score = test_ip_quality(ip, blacklist, cache)
            if score > best_score:
                best_score = score
            if best_score > 60:
                break
            if retry < Config.MAX_RETRIES:
                time.sleep(Config.RETRY_INTERVAL)
        ip_scores.append((ip, best_score))
        
        if best_score < 10:
            ip_addr = ip.split('#')[0].strip()
            country_blacklist.add(ip_addr)
    
    if ip_scores:
        ip_scores.sort(key=lambda x: x[1], reverse=True)
        avg_score = sum(score for _, score in ip_scores) / len(ip_scores)
        min_threshold = max(Config.MIN_THRESHOLD, avg_score * Config.THRESHOLD_RATIO)
        Logger.debug(f"Country {country_code}: avg {avg_score:.2f}, threshold {min_threshold:.2f}")
        qualified = [(ip, score) for ip, score in ip_scores if score >= min_threshold]
        top = [ip for ip, score in qualified[:Config.MAX_IPS_PER_COUNTRY]]
        filtered.extend(top)
        Logger.debug(f"Selected {len(top)} IPs for {country_code}")
    
    return filtered, country_blacklist


def final_verify_ips(ips: List[str]) -> Tuple[List[str], Set[str]]:
    final_ips = []
    new_blacklist = set()
    
    for ip_line in ips:
        raw_ip = ip_line.split('#')[0].strip()
        success_count = 0
        total_load_time = 0
        test_count = 0
        
        latencies, _ = test_latency(ip_line, timeout=3)
        if latencies:
            success_count += 1
            total_load_time += sum(latencies)
            test_count += 1
        
        downloads = test_download_speed(ip_line, max_time=5)
        if downloads:
            success_count += 1
            test_count += 1
        
        avg_load_time = total_load_time / test_count if success_count > 0 else 9999
        success_rate = (success_count / max(1, test_count)) * 100
        
        Logger.debug(f"Final verify {raw_ip}: {success_count}/{test_count} passed, {success_rate:.1f}%")
        
        if success_rate >= Config.MIN_SUCCESS_RATE and avg_load_time <= Config.MAX_LOAD_TIME:
            final_ips.append(ip_line)
        else:
            new_blacklist.add(raw_ip)
    
    return final_ips, new_blacklist


def secondary_filter(cache: CacheManager) -> None:
    start_time = time.time()
    summary_path = os.path.join(Config.BASE_DIR, Config.SUMMARY_FILE)
    if not os.path.exists(summary_path):
        Logger.error("Summary file not found")
        return
    
    Logger.info("Starting secondary filter...")
    blacklist = load_blacklist()
    
    with open(summary_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    Logger.debug(f"Read {len(lines)} lines")
    
    country_ips = {}
    no_match = 0
    for line in lines:
        cc = extract_country_code(line)
        if cc:
            if cc not in country_ips:
                country_ips[cc] = []
            country_ips[cc].append(line)
        else:
            no_match += 1
    
    Logger.debug(f"Found {len(country_ips)} countries, {no_match} no match")
    
    filtered_ips = []
    new_blacklist = set()
    
    if country_ips:
        with ThreadPoolExecutor(max_workers=min(Config.MAX_COUNTRY_WORKERS, len(country_ips))) as executor:
            futures = {executor.submit(process_country, cc, ips, blacklist, cache): cc for cc, ips in country_ips.items()}
            for future in as_completed(futures):
                cc = futures[future]
                try:
                    country_filtered, country_bl = future.result()
                    filtered_ips.extend(country_filtered)
                    new_blacklist.update(country_bl)
                except Exception as e:
                    Logger.error(f"Error processing {cc}: {e}")
    
    filtered_ips = list(set(filtered_ips))
    Logger.debug(f"After dedup: {len(filtered_ips)}")
    
    save_blacklist(blacklist, new_blacklist)
    
    if not filtered_ips and lines:
        Logger.warning("No IPs passed quality test, using fallback")
        temp = {}
        for line in lines:
            cc = extract_country_code(line)
            if cc:
                if cc not in temp:
                    temp[cc] = []
                if len(temp[cc]) < Config.MAX_IPS_PER_COUNTRY_FALLBACK:
                    temp[cc].append(line)
        for ips in temp.values():
            filtered_ips.extend(ips)
    
    if filtered_ips:
        Logger.info("Performing final verification...")
        final_ips, final_bl = final_verify_ips(filtered_ips)
        if final_ips:
            filtered_ips = final_ips
            Logger.info(f"{len(filtered_ips)} IPs passed final verification")
        else:
            Logger.warning("No IPs passed final verification")
        save_blacklist(blacklist, final_bl)
    
    best_ip_path = os.path.join(Config.BASE_DIR, Config.BEST_IP_FILE)
    if filtered_ips:
        with open(best_ip_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(filtered_ips)) + '\n')
        elapsed = time.time() - start_time
        Logger.success(f"Secondary filter completed in {elapsed:.2f}s. Kept {len(filtered_ips)} IPs.")
    else:
        Logger.error("No IPs passed the secondary filter")


def main():
    start_time = time.time()
    Logger.info("Starting IP filtering process...")
    
    if not Config.should_run_at_desired_time():
        Logger.warning("Not running at desired time (2:00 AM Beijing time), but continuing anyway...")
    
    if not os.path.exists(Config.BASE_DIR):
        os.makedirs(Config.BASE_DIR)
        Logger.info(f"Created base directory: {Config.BASE_DIR}")
    
    cache = CacheManager(os.path.join(Config.BASE_DIR, Config.CACHE_FILE))
    proxy_ips = load_proxy_ips()
    summary = set()
    
    for filename in Config.CLASSIFY_FILES:
        process_file(filename, summary, proxy_ips, cache)
    
    if summary:
        Logger.info(f"Processed {len(summary)} IPs")
        summary_path = os.path.join(Config.BASE_DIR, Config.SUMMARY_FILE)
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary))) + '\n')
        Logger.info(f"Wrote summary to {Config.SUMMARY_FILE}")
        secondary_filter(cache)
    elif os.path.exists(os.path.join(Config.BASE_DIR, Config.SUMMARY_FILE)):
        Logger.info("Using existing summary file")
        secondary_filter(cache)
    else:
        Logger.error("No summary file found and no files to process")
    
    elapsed = time.time() - start_time
    Logger.success(f"Classification done in {elapsed:.2f}s.")


if __name__ == "__main__":
    main()
