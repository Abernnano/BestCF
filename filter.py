import requests
import os
import time
import re

# 配置项
INPUT_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt", "proxy-ip.txt"]
BASE_DIR = "./bestcf"

def get_ip_country_batch(ips):
    """批量查询地理位置，避开 Anycast 路由误导"""
    if not ips: return {}
    try:
        # ip-api 批量接口，单次上限 100 个
        response = requests.post("http://ip-api.com/batch", json=ips, timeout=15).json()
        return {item['query']: item.get('countryCode') for item in response if item.get('status') == 'success'}
    except Exception as e:
        print(f"API 查询出错: {e}")
        return {}

def process_file(filename):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path): return

    print(f"开始分类: {filename}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    # 提取纯 IP 列表
    ip_to_line = {}
    pure_ips = []
    for line in lines:
        ip = line.split('#')[0].strip().replace('[', '').replace(']', '')
        # 简单校验是否为 IP 格式
        if re.match(r'^(\d{1,3}\.){3}\d{1,3}$|^([a-fA-F0-9:]+)$', ip):
            pure_ips.append(ip)
            ip_to_line[ip] = line

    # 分批查询 (每批 100 个)
    all_country_data = {}
    for i in range(0, len(pure_ips), 100):
        batch = pure_ips[i:i+100]
        batch_results = get_ip_country_batch(batch)
        all_country_data.update(batch_results)
        time.sleep(1.2) # 遵守 API 频率限制

    # 动态创建文件夹并写入
    categorized_counts = {}
    for ip, country in all_country_data.items():
        if country:
            country_dir = os.path.join(BASE_DIR, country)
            os.makedirs(country_dir, exist_ok=True)
            with open(os.path.join(country_dir, filename), 'a', encoding='utf-8') as f:
                f.write(ip_to_line[ip] + '\n')
            categorized_counts[country] = categorized_counts.get(country, 0) + 1
    
    print(f"完成 {filename}: {categorized_counts}")

if __name__ == "__main__":
    for f in INPUT_FILES:
        process_file(f)
