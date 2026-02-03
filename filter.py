import requests
import re
import os
import sys
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制设置输出编码为 UTF-8，防止 Windows GBK 报错
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
# 参与国家码分类的文件（严格排除 proxy-ip.txt）
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 30 

def get_real_loc(ip):
    """
    通过本地网络探测真实的 Anycast 落地国家
    """
    clean_ip = ip.replace('[', '').replace(']', '')
    try:
        # 探测当前网络环境下的实际节点
        # 使用 verify=False 是为了防止本地网络环境导致的 SSL 证书吊销检查错误
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

    # 去除了会导致 GBK 报错的表情符号
    print(f"[*] Processing: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_line = {executor.submit(get_real_loc, line.split('#')[0].strip()): line for line in lines}
        
        for future in as_completed(future_to_line):
            original_line = future_to_line[future]
            loc = future.result()
            
            if loc:
                if loc not in categorized_data:
                    categorized_data[loc] = []
                categorized_data[loc].append(original_line)
                
                # 汇总格式: IP#国家码
                ip_part = original_line.split('#')[0].strip()
                summary_set.add(f"{ip_part}#{loc}")

    # 写入分类
    for loc, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, loc)
        os.makedirs(country_dir, exist_ok=True)
        with open(os.path.join(country_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    
    summary_ips = set()

    # 只处理分类列表中的文件，proxy-ip.txt 不会参与
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)

    # 生成汇总全国家文件
    if summary_ips:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
        print("[+] Summary file generated successfully.")

if __name__ == "__main__":
    main()
