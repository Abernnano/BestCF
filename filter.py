import requests
import re
import os
import sys
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制设置输出编码为 UTF-8，防止 Windows 环境下输出非 ASCII 字符导致崩溃
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
# 参与分类的文件
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 40 

def get_real_loc(ip):
    """
    通过本地网络探测真实的 Anycast 落地国家
    """
    clean_ip = ip.replace('[', '').replace(']', '')
    try:
        # 使用直连探测，确保反映本地真实的宽带路由
        # 注意：Clash 规则中应将 cp.cloudflare.com 设为 DIRECT
        resp = requests.get(f"http://{clean_ip}/cdn-cgi/trace", timeout=2)
        if resp.status_code == 200:
            loc_match = re.search(r'loc=([A-Z]{2})', resp.text)
            if loc_match:
                return loc_match.group(1)
    except:
        pass
    return None

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path):
        return

    print(f"[*] Processing and Tagging: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 解析每一行，提取 IP 和 原始注释
        future_to_info = {}
        for line in lines:
            parts = line.split('#')
            ip = parts[0].strip()
            comment = parts[1].strip() if len(parts) > 1 else ""
            future = executor.submit(get_real_loc, ip)
            future_to_info[future] = (ip, comment)
        
        for future in as_completed(future_to_info):
            ip, old_comment = future_to_info[future]
            loc = future.result()
            
            if loc:
                # 核心功能：在 # 后标注国家码
                # 格式示例：1.1.1.1#GB_CMCC-IPv4_CMLiu_1
                new_line = f"{ip}#{loc}_{old_comment}" if old_comment else f"{ip}#{loc}"
                
                if loc not in categorized_data:
                    categorized_data[loc] = []
                categorized_data[loc].append(new_line)
                
                # 存入汇总 set
                summary_set.add(new_line)

    # 写入分类文件夹
    for loc, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, loc)
        os.makedirs(country_dir, exist_ok=True)
        with open(os.path.join(country_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    
    summary_ips = set()

    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)

    # 生成全国家汇总文件
    if summary_ips:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
        print("[+] All files categorized and tagged with country codes.")

if __name__ == "__main__":
    main()
