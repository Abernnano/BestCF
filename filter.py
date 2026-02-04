import requests
import re
import os
import sys
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. 强制 Windows 输出为 UTF-8
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 60 

# 定义抓取源（直接在 Python 里抓，不走命令行 curl）
FETCH_SOURCES = {
    "cmcc-ip.txt": [
        "https://cf.090227.xyz/cmcc?ips=50",
        "https://cf.090227.xyz/cmcc-ipv6?ips=50"
    ],
    "cucc-ip.txt": [
        "https://cf.090227.xyz/cu?ips=50"
    ],
    "ctcc-ip.txt": [
        "https://cf.090227.xyz/ct?ips=50"
    ],
    "bestcf-ip.txt": [
        "https://vps789.com/openApi/cfIpApi",
        "https://ipdb.api.030101.xyz/?type=bestcfv4"
    ]
}

COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR",
    "TPE": "TW", "LAX": "US", "SJC": "US", "SEA": "US", "FRA": "DE"
}

requests.packages.urllib3.disable_warnings()

def get_flag(country_code):
    """生成国旗 Emoji"""
    if not country_code or len(country_code) != 2: return ""
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def fetch_raw_ips(urls):
    """使用 Python 抓取数据，绕过 curl SSL 错误"""
    raw_ips = []
    for url in urls:
        try:
            # verify=False 相当于 --ssl-no-revoke
            resp = requests.get(url, timeout=10, verify=False)
            if resp.status_code == 200:
                # 简单解析 IP (支持 JSON 或 换行文本)
                if "application/json" in resp.headers.get("Content-Type", ""):
                    data = resp.json()
                    # 针对 vps789 等 API 的解析逻辑
                    if 'data' in data:
                        ips = [item.get('ip') for item in data['data'].get('CM', []) + data['data'].get('AllAvg', []) if item.get('ip')]
                        raw_ips.extend(ips)
                else:
                    ips = re.findall(r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}|(?:[a-f0-9]{1,4}:){7}[a-f0-9]{1,4}', resp.text)
                    raw_ips.extend(ips)
        except: pass
    return list(set(raw_ips))

def test_ip(ip):
    """测试延迟并识别国家"""
    clean_ip = ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    url = f"http://[{clean_ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{clean_ip}/cdn-cgi/trace"
    try:
        start = time.time()
        # 强制不走代理进行探测
        r = requests.get(url, timeout=2.5, verify=False, proxies={'http': None, 'https': None})
        latency = int((time.time() - start) * 1000)
        if r.status_code == 200:
            colo = re.search(r'colo=([A-Z]{3})', r.text).group(1)
            country = COLO_MAP.get(colo, colo)
            return country, latency
    except: pass
    return None, None

def main():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    summary_ips = set()

    for filename, urls in FETCH_SOURCES.items():
        print(f"[*] Fetching & Testing: {filename}")
        raw_list = fetch_raw_ips(urls)
        categorized = {}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(test_ip, ip): ip for ip in raw_list}
            for f in as_completed(futures):
                ip = futures[f]
                tag, ms = f.result()
                if tag:
                    flag = get_flag(tag) if len(tag) == 2 else "🌐"
                    # 格式：IP#国旗+国家码(延迟)_原始备注(此处标记来源)
                    line = f"{ip}#{flag}{tag}({ms}ms)_{filename.split('-')[0].upper()}"
                    categorized.setdefault(tag, []).append(line)
                    summary_ips.add(line)

        # 写入分类文件
        for tag, items in categorized.items():
            path = os.path.join(BASE_DIR, tag)
            os.makedirs(path, exist_ok=True)
            items.sort(key=lambda x: int(re.search(r'\((\d+)ms\)', x).group(1)))
            with open(os.path.join(path, filename), 'w', encoding='utf-8') as out:
                out.write('\n'.join(items) + '\n')

    # 生成汇总文件 (排除 proxy-ip)
    if summary_ips:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
        print("[SUCCESS] All processes completed.")

if __name__ == "__main__":
    main()
