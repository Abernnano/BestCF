import requests
import re
import os
import sys
import io
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 兼容性修复：强制 TLS 1.2 以解决 Windows Schannel 报错 ---
class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ssl_version=ssl.PROTOCOL_TLSv1_2)
        kwargs['ssl_context'] = context
        return super(TLSAdapter, self).init_poolmanager(*args, **kwargs)

# 核心修复：强制 Windows 控制台使用 UTF-8 编码，确保 Emoji 显示不崩溃
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 50 

# 扩充 Cloudflare 数据中心(Colo)到国家码的映射表
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR",
    "TPE": "TW", "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US",
    "FRA": "DE", "LHR": "GB", "CDG": "FR", "AMS": "NL", "ARN": "SE",
    "BKK": "TH", "MNL": "PH", "KUL": "MY", "CAN": "CN", "SHA": "CN",
    "PEK": "CN", "SZX": "CN", "CTU": "CN", "SYD": "AU", "MEL": "AU"
}

# 禁用不安全请求警告
requests.packages.urllib3.disable_warnings()

# 初始化全局 Session 并挂载 TLS 适配器
session = requests.Session()
session.mount("https://", TLSAdapter())
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

def get_flag(country_code):
    """将国家码转换为国旗 Emoji"""
    if not country_code or len(country_code) != 2:
        return ""
    try:
        return "".join(chr(127397 + ord(c)) for c in country_code.upper())
    except:
        return ""

def get_real_info(ip):
    """获取数据中心代码并返回国家码"""
    clean_ip = ip.replace('[', '').replace(']', '').strip()
    try:
        resp = session.get(f"http://{clean_ip}/cdn-cgi/trace", timeout=2, verify=False)
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                colo = colo_match.group(1)
                return COLO_MAP.get(colo, colo)
    except:
        pass
    return None

def purge_jsdelivr():
    """自动化刷新 jsDelivr CDN 缓存"""
    repo = os.getenv("GITHUB_REPOSITORY")
    if not repo:
        print("[!] GITHUB_REPOSITORY env not found, skipping purge.")
        return

    print(f"[*] Starting jsDelivr Purge for: {repo}")
    
    # 递归查找所有生成的 .txt 文件
    purge_list = []
    for root, _, files in os.walk(BASE_DIR):
        for file in files:
            if file.endswith(".txt"):
                # 计算相对于 BASE_DIR 的路径并处理 Windows 反斜杠
                rel_path = os.path.relpath(os.path.join(root, file), BASE_DIR).replace("\\", "/")
                purge_list.append(rel_path)

    for file_path in purge_list:
        # 刷新地址格式: https://purge.jsdelivr.net/gh/user/repo@branch/file
        url = f"https://purge.jsdelivr.net/gh/{repo}@bestcf/{file_path}"
        try:
            r = session.get(url, timeout=10)
            status = "SUCCESS" if r.status_code == 200 else f"FAILED({r.status_code})"
            print(f"    - [{status}] {file_path}")
        except Exception as e:
            print(f"    - [ERROR] {file_path}: {e}")

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path): return

    print(f"[*] Analyzing Routes: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_info = {executor.submit(get_real_info, line.split('#')[0].strip()): line for line in lines}
        for future in as_completed(future_to_info):
            original_line = future_to_info[future]
            country_tag = future.result()
            if country_tag:
                ip_part = original_line.split('#')[0].strip()
                old_comment = original_line.split('#')[1].strip() if '#' in original_line else ""
                flag = get_flag(country_tag) if len(country_tag) == 2 else ""
                new_line = f"{ip_part}#{flag}{country_tag}_{old_comment}" if old_comment else f"{ip_part}#{flag}{country_tag}"
                
                if country_tag not in categorized_data:
                    categorized_data[country_tag] = []
                categorized_data[country_tag].append(new_line)
                summary_set.add(new_line)

    for tag, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(country_dir, exist_ok=True)
        with open(os.path.join(country_dir, filename), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(items) + '\n')

def main():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    
    summary_ips = set()
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)

    if summary_ips:
        output_path = os.path.join(BASE_DIR, SUMMARY_FILE)
        with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
        print(f"[SUCCESS] Summary generated.")
        
        # 处理完所有文件后，执行 CDN 刷新
        purge_jsdelivr()

if __name__ == "__main__":
    main()
