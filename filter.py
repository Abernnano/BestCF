import requests
import re
import os
import sys
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# 处理 Windows 环境编码
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 配置区 ---
BASE_DIR = "./bestcf"
# 明确排除：不处理 proxy 和 domain 文件
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt", "heartbeat.txt"]
MAX_WORKERS = 20

# 城市名映射 (用于将 API 返回的英文城市转为中文，以触发你的订阅转换 Emoji)
CITY_MAP = {
    "Hong Kong": "香港", "Taipei": "台北", "Singapore": "新加坡",
    "Tokyo": "东京", "Osaka": "大阪", "Seoul": "首尔",
    "Los Angeles": "洛杉矶", "San Jose": "圣何塞", "San Francisco": "旧金山",
    "Seattle": "西雅图", "Chicago": "芝加哥", "New York": "纽约",
    "London": "伦敦", "Frankfurt": "法兰克福", "Paris": "巴黎",
    "Amsterdam": "阿姆斯特丹", "Sydney": "悉尼"
}

def get_physical_location(ip_full):
    """
    通过 GeoIP API 获取 IP 的物理注册地，而非云端 Anycast 路由地
    """
    # 彻底剥离端口和括号
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    
    try:
        # 使用 ip-api.com 获取物理归属地 (这是静态的，不受 GitHub 路由影响)
        # 字段包含：国家码、城市
        api_url = f"http://ip-api.com/json/{ip}?fields=status,countryCode,city"
        resp = requests.get(api_url, timeout=3.0)
        data = resp.json()
        
        if data.get("status") == "success":
            country_code = data.get("countryCode", "UN")
            city_en = data.get("city", "Unknown")
            # 匹配中文城市名，匹配不到则使用英文
            city_cn = CITY_MAP.get(city_en, city_en).replace(" ", "")
            return f"{country_code}_{city_cn}"
    except Exception:
        pass
            
    return "UN_Unknown"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    # 逻辑修复：严格排除不处理的文件
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES:
        return

    print(f"[*] 正在识别地理位置: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_line = {executor.submit(get_physical_location, line.split('#')[0]): line for line in lines}
        
        for future in as_completed(future_to_line):
            original_line = future_to_line[future]
            loc_info = future.result()
            
            ip_part = original_line.split('#')[0]
            # 补齐 IPv6 括号
            if ":" in ip_part and not ip_part.startswith("["):
                ip_part = f"[{ip_part}]"
                
            old_remark = original_line.split('#')[1] if '#' in original_line else ""
            
            # 生成新备注：国家码_城市_原始备注
            final_line = f"{ip_part}#{loc_info}_{old_remark}"
            new_results.append(final_line)
            summary_set.add(final_line)

    # 写回原文件
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_results) + '\n')

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
        
    summary_ips = set()
    # 遍历 bestcf 目录下所有 txt 文件
    files = [f for f in os.listdir(BASE_DIR) if f.endswith('.txt')]
    
    for f in files:
        process_file(f, summary_ips)
    
    # 生成总汇总文件
    if summary_ips:
        with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
            
    print("[✓] 云端识别任务完成")

if __name__ == "__main__":
    main()
