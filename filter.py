import requests
import os
import time
from concurrent.futures import ThreadPoolExecutor

# 配置项
INPUT_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt", "proxy-ip.txt"]
BASE_DIR = "./bestcf"

def get_ip_country_batch(ips):
    """使用 ip-api.com 批量查询地理位置，避开 Anycast 路由误导"""
    try:
        # ip-api 批量接口，单次最多 100 个
        response = requests.post("http://ip-api.com/batch", json=ips, timeout=10).json()
        results = {}
        for item in response:
            if item.get('status') == 'success':
                results[item['query']] = item.get('countryCode')
        return results
    except Exception as e:
        print(f"批量查询失败: {e}")
        return {}

def process_file(filename):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path): return

    print(f"正在处理: {filename}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    # 提取纯 IP 列表进行查询
    ip_to_line = {}
    pure_ips = []
    for line in lines:
        ip = line.split('#')[0].strip().replace('[', '').replace(']', '')
        pure_ips.append(ip)
        ip_to_line[ip] = line

    # 分批查询（每批 100 个，符合 API 限制）
    all_country_data = {}
    for i in range(0, len(pure_ips), 100):
        batch = pure_ips[i:i+100]
        batch_results = get_ip_country_batch(batch)
        all_country_data.update(batch_results)
        time.sleep(1) # 稍微延迟，避免频率限制

    # 分类存储
    categorized = {}
    for ip, country in all_country_data.items():
        if country:
            if country not in categorized: categorized[country] = []
            categorized[country].append(ip_to_line[ip])

    for country, items in categorized.items():
        country_dir = os.path.join(BASE_DIR, country)
        os.makedirs(country_dir, exist_ok=True)
        with open(os.path.join(country_dir, filename), 'a', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')
    
    print(f"  [-] {filename} 已按国家/地区分类完成。")

if __name__ == "__main__":
    for f in INPUT_FILES:
        process_file(f)
