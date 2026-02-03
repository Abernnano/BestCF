import requests
import os
import time
import re
from concurrent.futures import ThreadPoolExecutor

# --- 配置区 ---
# 待处理的原始 IP 文件列表
INPUT_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt", "proxy-ip.txt"]
BASE_DIR = "./bestcf"
# ip-api 批量接口每分钟限制 45 次请求，每次建议不超过 100 个 IP
BATCH_SIZE = 100 

def get_ip_country_batch(ips):
    """
    通过 ip-api.com 的批量接口获取 IP 的物理注册地。
    这能避开 GitHub 服务器在美国导致的 Anycast 路由偏见。
    """
    if not ips:
        return {}
    try:
        # 使用批量接口以提高效率
        url = "http://ip-api.com/batch?fields=status,message,query,countryCode"
        response = requests.post(url, json=ips, timeout=15).json()
        
        results = {}
        for item in response:
            if item.get('status') == 'success':
                results[item['query']] = item.get('countryCode')
        return results
    except Exception as e:
        print(f"  [!] 批量查询 API 出错: {e}")
        return {}

def clean_ip(line):
    """从包含备注的行中提取纯净的 IP 地址"""
    ip_raw = line.split('#')[0].strip()
    # 移除 IPv6 的中括号
    return ip_raw.replace('[', '').replace(']', '')

def process_file(filename):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path):
        return

    print(f"🔍 正在分类文件: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    # 建立 IP 与原始行的映射，并准备查询列表
    ip_to_original_lines = {}
    pure_ips = []
    for line in lines:
        ip = clean_ip(line)
        if ip:
            pure_ips.append(ip)
            # 考虑到可能存在重复 IP 但备注不同，使用列表存储
            if ip not in ip_to_original_lines:
                ip_to_original_lines[ip] = []
            ip_to_original_lines[ip].append(line)

    # 去重后的 IP 列表
    unique_ips = list(set(pure_ips))
    all_results = {}

    # 分批次查询地理位置
    for i in range(0, len(unique_ips), BATCH_SIZE):
        batch = unique_ips[i:i+BATCH_SIZE]
        print(f"  -> 正在查询第 {i+1} 至 {min(i+BATCH_SIZE, len(unique_ips))} 个 IP...")
        batch_results = get_ip_country_batch(batch)
        all_results.update(batch_results)
        # 遵守 API 速率限制，稍微停顿
        time.sleep(1.5)

    # 按国家码进行归类存储
    categorized_data = {}
    for ip, country in all_results.items():
        if country:
            if country not in categorized_data:
                categorized_data[country] = []
            categorized_data[country].extend(ip_to_original_lines[ip])

    # 写入文件夹
    for country, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, country)
        os.makedirs(country_dir, exist_ok=True)
        
        output_file = os.path.join(country_dir, filename)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')
    
    print(f"  ✅ {filename} 处理完成，识别到国家: {', '.join(categorized_data.keys())}")

if __name__ == "__main__":
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
        
    for f in INPUT_FILES:
        process_file(f)
