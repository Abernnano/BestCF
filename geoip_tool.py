import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor

# 针对中国地区优化的节点映射
COLO_MAP = {
    "HKG": "香港", "TPE": "台北", "SGP": "新加坡", "NRT": "东京", 
    "KIX": "大阪", "ICN": "首尔", "BKK": "曼谷", "MNL": "马尼拉",
    "KUL": "吉隆坡", "LAX": "洛杉矶", "SJC": "圣何塞", "SEA": "西雅图",
    "IAD": "华盛顿", "FRA": "法兰克福", "LHR": "伦敦", "CTU": "成都",
    "CAN": "广州", "SHA": "上海", "BJS": "北京"
}

def get_cf_colo(ip_part):
    clean_ip = ip_part.replace('[', '').replace(']', '')
    # 识别 IPv6
    is_ipv6 = ':' in clean_ip
    url = f"http://[{clean_ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{clean_ip}/cdn-cgi/trace"
    
    try:
        # 本地联动核心：直接通过本地网络连接
        # 使用 da.gd 作为 Host 诱导 CF 响应，或者直接请求
        resp = requests.get(url, timeout=3, headers={'Host': 'da.gd'})
        if resp.status_code == 200:
            match = re.search(r'colo=([A-Z]{3})', resp.text)
            if match:
                code = match.group(1)
                return COLO_MAP.get(code, f"未知-{code}")
    except Exception:
        pass
    return "超时/死IP"

def process_file(path):
    if not os.path.exists(path): return
    with open(path, 'r') as f:
        lines = f.readlines()
    
    processed_lines = []
    # 使用线程池并发提高本地识别速度
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda l: (l, get_cf_colo(l.split('#')[0])), lines))
    
    for line, colo in results:
        parts = line.strip().split('#')
        ip = parts[0]
        tag = parts[1] if len(parts) > 1 else ""
        processed_lines.append(f"{ip}#[{colo}]{tag}\n")
        
    with open(path, 'w') as f:
        f.writelines(processed_lines)

if __name__ == "__main__":
    target_dir = './bestcf/'
    files = ['cmcc-ip.txt', 'cucc-ip.txt', 'ctcc-ip.txt', 'bestcf-ip.txt']
    for f in files:
        print(f"正在本地识别: {f}")
        process_file(os.path.join(target_dir, f))
