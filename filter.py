import requests
import re
import os
import sys
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# 彻底解决 Windows 控制台编码问题
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 50 

# 常见的 Cloudflare 数据中心(Colo)到国家码的映射表
COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR",
    "TPE": "TW", "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US",
    "FRA": "DE", "LHR": "GB", "CDG": "FR", "AMS": "NL", "ARN": "SE"
}

requests.packages.urllib3.disable_warnings()

def get_real_info(ip):
    """
    通过探测获取数据中心代码(colo)，从而识别全球位置
    """
    clean_ip = ip.replace('[', '').replace(']', '')
    try:
        # 强制直连探测，获取该 IP 在当前网络下的落地数据中心
        resp = requests.get(
            f"http://{clean_ip}/cdn-cgi/trace", 
            timeout=2, 
            verify=False,
            proxies={'http': None, 'https': None} 
        )
        if resp.status_code == 200:
            # 提取数据中心代码 (例如 colo=HKG)
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                colo = colo_match.group(1)
                # 转换国家码，如果不在映射表中则直接显示三字码
                country = COLO_MAP.get(colo, colo)
                return country
    except:
        pass
    return None

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path):
        return

    print(f"[*] Analyzing Global Routes: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}
    success_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_info = {}
        for line in lines:
            ip = line.split('#')[0].strip()
            comment = line.split('#')[1].strip() if '#' in line else ""
            future = executor.submit(get_real_info, ip)
            future_to_info[future] = (ip, comment)
        
        for future in as_completed(future_to_info):
            ip, old_comment = future_to_info[future]
            country_tag = future.result()
            
            if country_tag:
                # 标注格式：IP#国家码_原注释
                new_line = f"{ip}#{country_tag}_{old_comment}" if old_comment else f"{ip}#{country_tag}"
                
                if country_tag not in categorized_data:
                    categorized_data[country_tag] = []
                categorized_data[country_tag].append(new_line)
                
                summary_set.add(new_line)
                success_count += 1

    for tag, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(country_dir, exist_ok=True)
        with open(os.path.join(country_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')
    
    print(f"    [+] {filename} Done: {success_count} Global IPs identified.")

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    
    summary_ips = set()

    # 严格仅处理分类列表，排除 proxy-ip.txt
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)

    summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
    if summary_ips:
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
        print(f"[SUCCESS] Global summary generated at: {summary_path}")

if __name__ == "__main__":
    main()
