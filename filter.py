import requests
import re
import os
import sys
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制输出编码
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
MAX_WORKERS = 15 

# 适配你的订阅转换：使用中文名以触发转换器的 Emoji 规则
COLO_INFO = {
    "HKG": ("HK", "香港"), "SIN": ("SG", "新加坡"), "NRT": ("JP", "东京"),
    "HND": ("JP", "东京"), "KIX": ("JP", "大阪"), "ICN": ("KR", "首尔"),
    "TPE": ("TW", "台湾"), "LAX": ("US", "洛杉矶"), "SJC": ("US", "圣何塞"),
    "SEA": ("US", "西雅图"), "SFO": ("US", "旧金山"), "ORD": ("US", "芝加哥"),
    "DFW": ("US", "达拉斯"), "IAD": ("US", "阿什本"), "JFK": ("US", "纽约"),
    "FRA": ("DE", "法兰克福"), "LHR": ("GB", "伦敦"), "CDG": ("FR", "巴黎"),
    "AMS": ("NL", "阿姆斯特丹"), "CAN": ("CN", "广州"), "SZX": ("CN", "深圳"),
    "SHA": ("CN", "上海"), "PVG": ("CN", "上海"), "PEK": ("CN", "北京"),
    "CTU": ("CN", "成都"), "SIA": ("CN", "西安"), "CKG": ("CN", "重庆"),
    "HGH": ("CN", "杭州"), "MFM": ("MO", "澳门"), "BKK": ("TH", "曼谷"),
    "KUL": ("MY", "吉隆坡"), "SYD": ("AU", "悉尼"), "YVR": ("CA", "温哥华")
}

requests.packages.urllib3.disable_warnings()

def get_ip_location(ip_full):
    """三级探测：Trace -> API -> Unknown"""
    # 核心修复：精准剥离中括号和端口号，确保 API 能识别
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    is_ipv6 = ":" in ip
    trace_url = f"http://[{ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{ip}/cdn-cgi/trace"
    
    # 1. 优先直连探测 Cloudflare Colo (最准)
    try:
        resp = requests.get(trace_url, timeout=2.0, verify=False, proxies={'http': None, 'https': None})
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                code = colo_match.group(1)
                if code in COLO_INFO:
                    country, city = COLO_INFO[code]
                    return f"{country}_{city}"
                return f"{code[:2]}_{code}" 
    except:
        pass

    # 2. 保底：在线 API (处理 IPv6 无法直连的情况)
    try:
        # 增加 IPv6 友好型接口调用
        api_url = f"http://ip-api.com/json/{ip}?fields=countryCode,city"
        resp = requests.get(api_url, timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            country = data.get("countryCode", "UN")
            city = data.get("city", "Unknown")
            return f"{country}_{city}"
    except:
        pass
            
    return "UN_Unknown"

def process_file(filename, summary_set):
    file_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(file_path): return

    print(f"[*] Analyzing: {filename}")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    categorized_data = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 获取第一部分（#号前）作为 IP 传入
        future_to_info = {executor.submit(get_ip_location, line.split('#')[0].strip()): line for line in lines}
        
        for future in as_completed(future_to_info):
            original_line = future_to_info[future]
            loc_info = future.result() 
            
            # 格式化 IP 部分
            ip_part = original_line.split('#')[0].strip()
            # 自动修复 IPv6 的中括号
            raw_ip = re.sub(r'\[|\]', '', ip_part.split(':')[0] if ":" in ip_part else ip_part)
            if ":" in raw_ip and not ip_part.startswith("["):
                ip_part = f"[{ip_part}]"
                
            # 提取注释（如 CMCC-IPv6_1）
            old_comment = original_line.split('#')[1].strip() if '#' in original_line else "Cloudflare"
            
            # 最终生成的Remark：例如 US_洛杉矶_CMCC-IPv6_1
            # 注意：此处不手动加 Emoji，让转换器的 add_emoji=true 去处理
            new_remark = f"{loc_info}_{old_comment}"
            new_line = f"{ip_part}#{new_remark}"
            
            country_code = loc_info.split('_')[0]
            if country_code not in categorized_data: categorized_data[country_code] = []
            categorized_data[country_code].append(new_line)
            summary_set.add(new_line)

    for tag, items in categorized_data.items():
        country_dir = os.path.join(BASE_DIR, tag)
        os.makedirs(country_dir, exist_ok=True)
        with open(os.path.join(country_dir, filename), 'w', encoding='utf-8') as f:
            f.write('\n'.join(items) + '\n')

def main():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    summary_ips = set()
    for f in CLASSIFY_FILES:
        process_file(f, summary_ips)
    if summary_ips:
        with open(os.path.join(BASE_DIR, SUMMARY_FILE), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
    print("[SUCCESS] Adaptation complete.")

if __name__ == "__main__":
    main()
