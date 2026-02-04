import requests
import re
import os
import sys
import io
import ssl
import time
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 兼容性修复：强制 TLS 1.2 ---
class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ssl_version=ssl.PROTOCOL_TLSv1_2)
        kwargs['ssl_context'] = context
        return super(TLSAdapter, self).init_poolmanager(*args, **kwargs)

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 30  # 适当降低并发以提高在 Windows 上的稳定性

# 扩展 Colo 映射表
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR",
    "TPE": "TW", "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US",
    "FRA": "DE", "LHR": "GB", "CDG": "FR", "AMS": "NL", "ARN": "SE",
    "BKK": "TH", "MNL": "PH", "KUL": "MY", "CAN": "CN", "SHA": "CN",
    "PEK": "CN", "SZX": "CN", "CTU": "CN", "SYD": "AU", "MEL": "AU"
}

requests.packages.urllib3.disable_warnings()
session = requests.Session()
session.mount("https://", TLSAdapter())
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"})

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return ""
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_real_info(ip):
    """获取数据中心并识别国家"""
    clean_ip = ip.replace('[', '').replace(']', '').strip()
    # 尝试访问 trace 接口，增加重试
    for _ in range(2):
        try:
            # 优先尝试 http 避免部分环境 SSL 握手慢
            resp = session.get(f"http://{clean_ip}/cdn-cgi/trace", timeout=3, verify=False)
            if resp.status_code == 200:
                colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
                if colo_match:
                    colo = colo_match.group(1)
                    return COLO_MAP.get(colo, colo)
        except:
            continue
    return "UNKNOWN"

def fetch_data():
    """替代 curl，直接下载所有源数据"""
    print("[*] Downloading IP sources...")
    sources = {
        "cmcc-ip.txt": [
            "https://cf.090227.xyz/cmcc?ips=50",
            "https://cf.090227.xyz/cmcc-ipv6?ips=50"
        ],
        "cucc-ip.txt": ["https://cf.090227.xyz/cu?ips=50"],
        "ctcc-ip.txt": ["https://cf.090227.xyz/ct?ips=50"],
        "bestcf-ip.txt": ["https://ipdb.api.030101.xyz/?type=bestcfv4"]
    }
    
    for filename, urls in sources.items():
        all_content = []
        for url in urls:
            try:
                r = session.get(url, timeout=10)
                if r.status_code == 200:
                    all_content.append(r.text)
            except:
                print(f"[!] Failed to fetch {url}")
        
        with open(os.path.join(BASE_DIR, filename), 'w', encoding='utf-8') as f:
            f.write("\n".join(all_content))

def process_classification():
    """核心处理逻辑"""
    summary_ips = set()
    files = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
    
    for filename in files:
        file_path = os.path.join(BASE_DIR, filename)
        if not os.path.exists(file_path): continue
        
        print(f"[*] Processing {filename}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = list(set([l.strip() for l in f.readlines() if l.strip()]))

        categorized = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_ip = {executor.submit(get_real_info, line.split('#')[0]): line for line in lines}
            for future in as_completed(future_to_ip):
                original_line = future_to_ip[future]
                tag = future.result()
                ip = original_line.split('#')[0].strip()
                
                # 即使识别失败也保留 UNKNOWN 标签，确保文件生成
                flag = get_flag(tag)
                new_line = f"{ip}#{flag}{tag}_{filename.split('-')[0].upper()}"
                
                if tag not in categorized: categorized[tag] = []
                categorized[tag].append(new_line)
                summary_ips.add(new_line)

        # 写入分类
        for tag, items in categorized.items():
            tag_dir = os.path.join(BASE_DIR, tag)
            os.makedirs(tag_dir, exist_ok=True)
            with open(os.path.join(tag_dir, filename), 'w', encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(items) + '\n')

    # 生成总表
    if summary_ips:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(sorted(list(summary_ips))))

def purge_cdn():
    repo = os.getenv("GITHUB_REPOSITORY")
    if not repo: return
    print("[*] Purging CDN...")
    # 简化的 purge 逻辑
    try:
        session.get(f"https://purge.jsdelivr.net/gh/{repo}@bestcf/{SUMMARY_FILE}", timeout=10)
    except: pass

if __name__ == "__main__":
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    fetch_data()            # 1. 下载
    process_classification() # 2. 识别与分类
    purge_cdn()             # 3. 刷新
    print("[DONE] Project executed successfully.")
