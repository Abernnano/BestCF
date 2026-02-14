import os
import re
import maxminddb
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置 ---
BASE_DIR = "./bestcf"
DB_FILE = "GeoLite2-City.mmdb"
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt", "heartbeat.txt"]

# 城市汉化表：对齐你订阅转换 .ini 中的正则表达式
CITY_CN = {
    "Hong Kong": "香港", "Tokyo": "东京", "Osaka": "大阪", 
    "Seoul": "首尔", "Singapore": "新加坡", "Taipei": "台北",
    "Los Angeles": "洛杉矶", "San Jose": "圣何塞", "Seattle": "西雅图",
    "San Francisco": "旧金山", "Chicago": "芝加哥", "New York": "纽约",
    "London": "伦敦", "Frankfurt": "法兰克福", "Paris": "巴黎"
}

def get_node_location(ip_full):
    # 剥离端口和括号
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    
    try:
        with maxminddb.open_database(DB_FILE) as reader:
            data = reader.get(ip)
            if data:
                country_code = data.get('country', {}).get('iso_code', 'UN')
                # 优先获取英文城市名
                city_en = data.get('city', {}).get('names', {}).get('en', 'Anycast')
                city_cn = CITY_CN.get(city_en, city_en).replace(" ", "")
                
                # --- 核心：中国视角校准逻辑 ---
                # 如果数据库识别为美国，但 IP 段属于 Cloudflare 的亚太高优先级段
                # 针对你之前遇到的 Toronto/Seattle 误报进行修正
                if country_code == "US" and ip.startswith(("104.16", "104.17", "172.64", "162.159")):
                    # 这些段在大陆移动/联通视角下极大概率是香港或直连优化
                    if "Seattle" in city_en or "San" in city_en:
                        # 标记为亚太优化，以触发你的负载均衡组
                        return f"HK_亚太优化"
                
                return f"{country_code}_{city_cn}"
    except Exception:
        pass
    return "UN_Unknown"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES:
        return

    print(f"[*] 正在执行二分树归属地检索: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_map = {executor.submit(get_node_location, line.split('#')[0]): line for line in lines}
        for future in as_completed(future_map):
            original = future_map[future]
            loc = future.result()
            
            ip_part = original.split('#')[0]
            if ":" in ip_part and not ip_part.startswith("["): ip_part = f"[{ip_part}]"
            note = original.split('#')[1] if '#' in original else ""
            
            # 格式：国家码_城市_原始备注
            final_line = f"{ip_part}#{loc}_{note}"
            new_results.append(final_line)
            summary_set.add(final_line)

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_results) + '\n')

def main():
    if not os.path.exists(DB_FILE):
        print(f"[!] 数据库文件 {DB_FILE} 缺失")
        return
        
    summary_ips = set()
    files = [f for f in os.listdir(BASE_DIR) if f.endswith('.txt')]
    for f in files:
        process_file(f, summary_ips)
    
    if summary_ips:
        with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
    print("[✓] 优选 IP 归类任务完成")

if __name__ == "__main__":
    main()
