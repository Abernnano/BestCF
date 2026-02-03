import requests
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置区 ---
# 输入文件（由 shell 脚本抓取生成原始数据）
INPUT_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt", "proxy-ip.txt"]
BASE_DIR = "./bestcf"
# 并发线程数（GitHub Action 环境建议 20-40，太大会被 CF 暂时屏蔽）
MAX_WORKERS = 30

def get_ip_info(line):
    """提取 IP 并通过 CF Trace 识别国家码"""
    line = line.strip()
    if not line:
        return None, None
    
    # 提取 # 前的 IP 部分并清理
    ip_raw = line.split('#')[0].strip()
    ip_clean = ip_raw.replace('[', '').replace(']', '')
    
    try:
        # 使用 CF trace 接口
        resp = requests.get(f"http://{ip_clean}/cdn-cgi/trace", timeout=2)
        if resp.status_code == 200:
            loc_match = re.search(r'loc=([A-Z]{2})', resp.text)
            if loc_match:
                return loc_match.group(1), line
    except:
        pass
    return "UNKNOWN", line

def process_file(filename):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path):
        print(f"跳过不存在的文件: {filename}")
        return

    print(f"正在分析: {filename} ...")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l for l in f.readlines() if l.strip()]

    # 使用字典动态存储：{ "HK": [line1, line2], "US": [line3] }
    categorized_data = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_line = {executor.submit(get_ip_info, line): line for line in lines}
        for future in as_completed(future_to_line):
            country_code, original_line = future.result()
            if country_code:
                if country_code not in categorized_data:
                    categorized_data[country_code] = []
                categorized_data[country_code].append(original_line)

    # 写入结果：按国家码创建子目录
    for country, items in categorized_data.items():
        if country == "UNKNOWN": continue # 忽略无法识别的
        
        country_dir = os.path.join(BASE_DIR, country)
        os.makedirs(country_dir, exist_ok=True)
        
        output_path = os.path.join(country_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')
    
    print(f"文件 {filename} 处理完毕，共识别出 {len(categorized_data.keys())} 个国家/地区。")

if __name__ == "__main__":
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
        
    for f in INPUT_FILES:
        process_file(f)
