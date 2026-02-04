import requests
import re
import os
import sys
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. 强制 Windows 输出为 UTF-8，防止国旗 Emoji 导致崩溃
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 60 # 提高并发以加快全球延迟测试速度

# 数据中心映射表
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR",
    "TPE": "TW", "LAX": "US", "SJC": "US", "SEA": "US", "FRA": "DE",
    "LHR": "GB", "CDG": "FR", "AMS": "NL", "ARN": "SE", "SFO": "US"
}

requests.packages.urllib3.disable_warnings()

def get_flag(country_code):
    """将国家码转换为国旗 Emoji"""
    if not country_code or len(country_code) != 2:
        return ""
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def test_ip_performance(ip):
    """
    同时获取国家码(Colo)并测量 HTTP 响应延迟
    """
    # 自动处理 IPv6 的括号包裹
    is_ipv6 = ":" in ip and "[" not in ip
    test_url = f"http://[{ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{ip}/cdn-cgi/trace"
    
    try:
        start_time = time.time()
        # 强制直连探测，获取本地真实的响应速度
        resp = requests.get(
            test_url, 
            timeout=2.5, 
            verify=False,
            proxies={'http': None, 'https': None} 
        )
        latency = int((time.time() - start_time) * 1000) # 转换为毫秒
        
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                colo = colo_match.group(1)
                country = COLO_MAP.get(colo, colo)
                return country, latency
    except:
        pass
    return None, None

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path):
        return

    print(f"[*] Testing Latency & Classification: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 解析每一行，兼容原始备注
        future_to_info = {}
        for line in lines:
            parts = line.split('#')
            ip = parts[0].strip()
            old_comment = parts[1].strip() if len(parts) > 1 else ""
            future = executor.submit(test_ip_performance, ip)
            future_to_info[future] = (ip, old_comment)
        
        for future in as_completed(future_to_info):
            ip, old_comment = future_to_info[future]
            country_tag, latency = future.result()
            
            if country_tag:
                flag = get_flag(country_tag) if len(country_tag) == 2 else "🌐"
                # 插入格式：IP#国旗+国家码+延迟_原始备注
                # 示例: 1.1.1.1#🇭🇰HK(158ms)_CMCC-IPv4...
                new_line = f"{ip}#{flag}{country_tag}({latency}ms)_{old_comment}"
                
                if country_tag not in categorized_data:
                    categorized_data[country_tag] = []
                categorized_data[country_tag].append(new_line)
                summary_set.add(new_line)

    # 写入文件，保持 UTF-8 编码
    for tag, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(country_dir, exist_ok=True)
        # 按延迟升序排列，方便选取最快的 IP
        items.sort(key=lambda x: int(re.search(r'\((\d+)ms\)', x).group(1)) if re.search(r'\((\d+)ms\)', x) else 999)
        with open(os.path.join(country_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    
    summary_ips = set()
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)

    if summary_ips:
        summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
        # 汇总文件按国家及延迟排序
        sorted_summary = sorted(list(summary_ips))
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted_summary) + '\n')
        print(f"[SUCCESS] Multi-stack Global filter finished.")

if __name__ == "__main__":
    main()
