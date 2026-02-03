import requests
import re
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置区 ---
# 参与国家码分类的文件（移除了 proxy-ip.txt）
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 30 # 探测并发数

def get_real_loc(ip):
    """
    核心：通过实地探测获取 IP 此时此刻的实际落地国家
    """
    clean_ip = ip.replace('[', '').replace(']', '')
    try:
        # 访问 Cloudflare 诊断接口
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

    print(f"🔍 正在探测路由位置: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    # 分类存储结构
    categorized_data = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 建立任务映射
        future_to_line = {executor.submit(get_real_loc, line.split('#')[0].strip()): line for line in lines}
        
        for future in as_completed(future_to_line):
            original_line = future_to_line[future]
            loc = future.result()
            
            if loc:
                # 存入国家分类目录
                if loc not in categorized_data:
                    categorized_data[loc] = []
                categorized_data[loc].append(original_line)
                
                # 提取 IP 存入汇总 set (格式: IP#国家码)
                ip_part = original_line.split('#')[0].strip()
                summary_set.add(f"{ip_part}#{loc}")

    # 写入分类文件
    for loc, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, loc)
        os.makedirs(country_dir, exist_ok=True)
        output_path = os.path.join(country_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')
            
    print(f"  ✅ {filename} 探测完成，分类至: {', '.join(categorized_data.keys())}")

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    
    summary_ips = set()

    # 逻辑：只循环需要分类的文件列表
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)

    # 汇总文件写入
    if summary_ips:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
        print(f"✨ 全球优选汇总已生成: {SUMMARY_FILE}")

if __name__ == "__main__":
    main()
