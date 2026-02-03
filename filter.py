import requests
import re
import os
import sys
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. 彻底解决 Windows 控制台编码问题
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
# 明确参与分类的文件列表（此处不包含 proxy-ip.txt，确保其被排除）
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 50  # 增加并发提高探测速度

# 禁用 requests 的安全警告（因为我们要跳过 SSL 验证）
requests.packages.urllib3.disable_warnings()

def get_real_loc(ip):
    """
    通过本地网络探测真实的国家码，跳过代理和 SSL 检查
    """
    clean_ip = ip.replace('[', '').replace(']', '')
    try:
        # 核心逻辑：强制不走代理，跳过 SSL 验证，确保识别的是本地宽带路由
        resp = requests.get(
            f"http://{clean_ip}/cdn-cgi/trace", 
            timeout=3, 
            verify=False,
            proxies={'http': None, 'https': None} 
        )
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
        print(f"[!] File not found: {filename}")
        return

    print(f"[*] Processing: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    if not lines:
        return

    categorized_data = {}
    success_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_info = {}
        for line in lines:
            # 兼容带有 # 的注释行
            ip = line.split('#')[0].strip()
            comment = line.split('#')[1].strip() if '#' in line else ""
            future = executor.submit(get_real_loc, ip)
            future_to_info[future] = (ip, comment)
        
        for future in as_completed(future_to_info):
            ip, old_comment = future_to_info[future]
            loc = future.result()
            
            if loc:
                # 重新标注国家码：IP#LOC_原注释
                new_line = f"{ip}#{loc}_{old_comment}" if old_comment else f"{ip}#{loc}"
                
                if loc not in categorized_data:
                    categorized_data[loc] = []
                categorized_data[loc].append(new_line)
                
                # 存入汇总集（此处只处理 CLASSIFY_FILES 里的内容）
                summary_set.add(new_line)
                success_count += 1

    # 写入按国家分类的文件
    for loc, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, loc)
        os.makedirs(country_dir, exist_ok=True)
        with open(os.path.join(country_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')
    
    print(f"    [+] Finished {filename}: {success_count}/{len(lines)} IPs identified.")

def main():
    # 确保基础目录存在
    if not os.path.exists(BASE_DIR):
        print(f"[!] Base directory {BASE_DIR} does not exist. Creating...")
        os.makedirs(BASE_DIR)
    
    summary_ips = set()

    # 1. 遍历需要分类的文件
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)

    # 2. 生成汇总文件 (排除 proxy-ip.txt)
    # 注意：只要 summary_ips 不为空，就会强制生成文件
    summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
    
    if summary_ips:
        with open(summary_path, 'w', encoding='utf-8') as f:
            # 排序后写入，确保结果整齐
            sorted_ips = sorted(list(summary_ips))
            f.write('\n'.join(sorted_ips) + '\n')
        print(f"[SUCCESS] All-countries summary generated at: {summary_path}")
    else:
        print("[ERROR] No IP locations were identified. Summary file skipped.")

if __name__ == "__main__":
    main()
