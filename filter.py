import requests
import re
import os
import sys
import io
import ssl
import json
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 核心修复：强制 TLS 1.2 避开 Windows Schannel Bug ---
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
MAX_WORKERS = 40

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

def get_flag(cc):
    return "".join(chr(127397 + ord(c)) for c in cc.upper()) if cc and len(cc)==2 else ""

def get_real_info(ip):
    clean_ip = ip.replace('[', '').replace(']', '').strip()
    try:
        # 尝试通过 Cloudflare 诊断接口获取数据中心(Colo)
        resp = session.get(f"http://{clean_ip}/cdn-cgi/trace", timeout=2, verify=False)
        if resp.status_code == 200:
            match = re.search(r'colo=([A-Z]{3})', resp.text)
            if match:
                colo = match.group(1)
                return COLO_MAP.get(colo, colo)
    except: pass
    return "UNKNOWN"

def safe_fetch(url, is_json=False, post_data=None):
    """通用的安全下载函数，替代 curl"""
    try:
        if post_data:
            r = session.post(url, json=post_data, timeout=10)
        else:
            r = session.get(url, timeout=10)
        return r.json() if is_json else r.text
    except Exception as e:
        print(f"[!] Fetch Error: {url} -> {e}")
        return None

def main():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    
    # 1. 抓取所有源数据 (原 YAML 里的所有 curl 逻辑)
    print("[*] Downloading raw data...")
    raw_data = {
        "cmcc-ip.txt": [], "cucc-ip.txt": [], "ctcc-ip.txt": [], "bestcf-ip.txt": []
    }
    
    # 移动源
    cmliu_cmcc = safe_fetch("https://cf.090227.xyz/cmcc?ips=50")
    if cmliu_cmcc: raw_data["cmcc-ip.txt"].extend([f"{l}#CMCC_CMLiu" for l in cmliu_cmcc.splitlines()])
    
    # 联通源
    cmliu_cu = safe_fetch("https://cf.090227.xyz/cu?ips=50")
    if cmliu_cu: raw_data["cucc-ip.txt"].extend([f"{l}#CUCC_CMLiu" for l in cmliu_cu.splitlines()])
    
    # 电源源
    cmliu_ct = safe_fetch("https://cf.090227.xyz/ct?ips=50")
    if cmliu_ct: raw_data["ctcc-ip.txt"].extend([f"{l}#CTCC_CMLiu" for l in cmliu_ct.splitlines()])

    # Hostmonit 优选 (替代 curl --data-raw)
    hostmonit = safe_fetch("https://api.hostmonit.com/get_optimization_ip", is_json=True, post_data={"key":"iDetkOys"})
    if hostmonit and 'info' in hostmonit:
        for item in hostmonit['info']:
            line_map = {"CM": "cmcc-ip.txt", "CU": "cucc-ip.txt", "CT": "ctcc-ip.txt"}
            target_file = line_map.get(item['line'])
            if target_file:
                raw_data[target_file].append(f"{item['ip']}#CFYes_{item['line']}")

    # 2. 处理与分类
    summary_ips = set()
    for filename, lines in raw_data.items():
        if not lines: continue
        print(f"[*] Classifying {filename}...")
        categorized = {}
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exec:
            future_to_line = {exec.submit(get_real_info, l.split('#')[0]): l for l in lines}
            for f in as_completed(future_to_line):
                orig = future_to_line[f]
                tag = f.result()
                ip = orig.split('#')[0]
                comment = orig.split('#')[1] if '#' in orig else ""
                
                flag = get_flag(tag)
                new_line = f"{ip}#{flag}{tag}_{comment}"
                
                if tag not in categorized: categorized[tag] = []
                categorized[tag].append(new_line)
                summary_ips.add(new_line)

        # 写入分类文件
        for tag, items in categorized.items():
            path = os.path.join(BASE_DIR, tag)
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, filename), 'w', encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(items) + '\n')

    # 3. 生成汇总
    if summary_ips:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(sorted(list(summary_ips))))
        print(f"[+] Total {len(summary_ips)} IPs generated.")

    # 4. 刷新 CDN (直接在 Python 里完成)
    repo = os.getenv("GITHUB_REPOSITORY")
    if repo:
        print("[*] Purging jsDelivr...")
        session.get(f"https://purge.jsdelivr.net/gh/{repo}@bestcf/{SUMMARY_FILE}")

if __name__ == "__main__":
    main()
