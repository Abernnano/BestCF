import requests
import os
import time
import re

# --- 配置区 ---
# 待处理的原始 IP 文件列表
INPUT_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
# 汇总文件名
SUMMARY_FILE = "all-countries-ip.txt"
# ip-api 批量接口限制
BATCH_SIZE = 100 

def get_ip_country_batch(ips):
    """
    通过 ip-api.com 的批量接口获取 IP 的物理注册地。
    """
    if not ips:
        return {}
    try:
        url = "http://ip-api.com/batch?fields=status,message,query,countryCode"
        response = requests.post(url, json=ips, timeout=15).json()
        results = {}
        for item in response:
            if item.get('status') == 'success':
                results[item['query']] = item.get('countryCode')
        return results
    except Exception as e:
        print(f"  [!] API 查询出错: {e}")
        return {}

def clean_ip(line):
    """从行中提取纯净 IP"""
    ip_raw = line.split('#')[0].strip()
    return ip_raw.replace('[', '').replace(']', '')

def process_file(filename, summary_list):
    """
    处理单个文件：分国家存储，并将结果记录到汇总列表中。
    """
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path):
        return

    print(f"🔍 正在处理: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    ip_to_original_lines = {}
    pure_ips = []
    for line in lines:
        ip = clean_ip(line)
        if ip and re.match(r'^(\d{1,3}\.){3}\d{1,3}$|^([a-fA-F0-9:]+)$', ip):
            pure_ips.append(ip)
            if ip not in ip_to_original_lines:
                ip_to_original_lines[ip] = []
            ip_to_original_lines[ip].append(line)

    unique_ips = list(set(pure_ips))
    all_results = {}

    # 分批查询地理位置
    for i in range(0, len(unique_ips), BATCH_SIZE):
        batch = unique_ips[i:i+BATCH_SIZE]
        batch_results = get_ip_country_batch(batch)
        all_results.update(batch_results)
        time.sleep(1.2)

    # 分类逻辑
    categorized_data = {}
    for ip, country in all_results.items():
        if country:
            # 1. 存入分国家文件夹数据结构
            if country not in categorized_data:
                categorized_data[country] = []
            categorized_data[country].extend(ip_to_original_lines[ip])
            
            # 2. 存入汇总数据结构（格式：IP#国家码）
            # 如果是 IPv6，自动加上中括号
            formatted_ip = f"[{ip}]" if ":" in ip else ip
            summary_list.add(f"{formatted_ip}#{country}")

    # 写入分国家文件夹
    for country, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, country)
        os.makedirs(country_dir, exist_ok=True)
        output_file = os.path.join(country_dir, filename)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    
    # 使用 set 自动去重汇总 IP
    summary_ips = set()

    for f in INPUT_FILES:
        process_file(f, summary_ips)

    # 写入汇总文件 (all-countries-ip.txt)
    if summary_ips:
        summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
        with open(summary_path, 'w', encoding='utf-8') as f:
            # 按字母顺序排序以便查看
            sorted_ips = sorted(list(summary_ips))
            f.write('\n'.join(sorted_ips) + '\n')
        print(f"✨ 汇总完成！已生成: {SUMMARY_FILE}，包含 {len(sorted_ips)} 个 IP。")

if __name__ == "__main__":
    main()
