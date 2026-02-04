import requests
import re
import os
import sys
import io
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed

# 彻底解决 Windows 控制台编码问题
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 50  # 线程数

# 扩展 Cloudflare 数据中心(Colo)到国家码的映射表
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR",
    "TPE": "TW", "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US",
    "FRA": "DE", "LHR": "GB", "CDG": "FR", "AMS": "NL", "ARN": "SE",
    "SYD": "AU", "BKK": "TH", "MNL": "PH", "KUL": "MY", "MAA": "IN",
    "BOM": "IN", "DXB": "AE", "SNA": "US", "BUR": "US", "DFW": "US"
}

requests.packages.urllib3.disable_warnings()

def get_ip_version(ip_str):
    """识别 IP 版本"""
    try:
        clean_ip = ip_str.replace('[', '').replace(']', '')
        addr = ipaddress.ip_address(clean_ip)
        return f"v{addr.version}"
    except:
        return "Unknown"

def get_real_info(ip):
    """
    获取国家码：
    1. 尝试 Cloudflare Trace 探测 (最准)
    2. 如果失败，尝试通过 GeoIP API 兜底
    """
    clean_ip = ip.replace('[', '').replace(']', '')
    
    # 方法 1: CF Trace (针对 Anycast IP 识别节点位置)
    try:
        resp = requests.get(
            f"http://{clean_ip}/cdn-cgi/trace", 
            timeout=1.5, 
            verify=False,
            proxies={'http': None, 'https': None}
        )
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                colo = colo_match.group(1)
                return COLO_MAP.get(colo, colo)
    except:
        pass

    # 方法 2: GeoIP API 兜底 (针对非 CF IP 或不响应 IP)
    try:
        # ip-api.com 免费接口
        resp = requests.get(f"http://ip-api.com/json/{clean_ip}?fields=countryCode", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("countryCode")
    except:
        pass

    return None

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path):
        return

    print(f"[*] 正在分析: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}
    success_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_info = {}
        for line in lines:
            # 解析 IP 和现有注释
            parts = line.split('#')
            ip = parts[0].strip()
            old_comment = parts[1].strip() if len(parts) > 1 else ""
            
            # 提交任务
            future = executor.submit(get_real_info, ip)
            future_to_info[future] = (ip, old_comment)
        
        for future in as_completed(future_to_info):
            ip, old_comment = future_to_info[future]
            country_tag = future.result()
            ip_ver = get_ip_version(ip)
            
            # 如果没拿到国家码，给一个默认标记
            tag = country_tag if country_tag else "UN"
            
            # 新的注释格式: IP#国家-版本_原注释
            new_comment = f"{tag}-{ip_ver}"
            if old_comment:
                # 避免重复叠加版本号
                clean_old_comment = old_comment.replace("IPv4", "").replace("IPv6", "").strip('_')
                final_line = f"{ip}#{new_comment}_{clean_old_comment}"
            else:
                final_line = f"{ip}#{new_comment}"

            # 归类数据
            if tag not in categorized_data:
                categorized_data[tag] = []
            categorized_data[tag].append(final_line)
            
            summary_set.add(final_line)
            success_count += 1

    # 写入按国家分类的文件
    for tag, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(country_dir, exist_ok=True)
        with open(os.path.join(country_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')
    
    print(f"    [+] {filename} 处理完成: 识别到 {success_count} 个全球 IP.")

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    
    summary_ips = set()

    # 处理列表中的文件
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)

    # 生成汇总文件
    summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
    if summary_ips:
        # 排序：让 IPv4 在前，IPv6 在后，并按国家字母排序
        sorted_ips = sorted(list(summary_ips), key=lambda x: (re.search(r'v\d', x).group() if re.search(r'v\d', x) else "", x))
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted_ips) + '\n')
        print(f"[SUCCESS] 全球汇总列表已生成: {summary_path}")

if __name__ == "__main__":
    main()
