import os
import re
import maxminddb
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置 ---
BASE_DIR = "./bestcf"
DB_FILE = "GeoLite2-City.mmdb"
# 排除列表：不处理的文件
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt", "heartbeat.txt"]

# 城市汉化映射 (用于对齐你的 .ini 规则)
CITY_CN = {
    "Hong Kong": "香港", "Tokyo": "东京", "Osaka": "大阪", 
    "Seoul": "首尔", "Singapore": "新加坡", "Taipei": "台北",
    "Los Angeles": "洛杉矶", "San Jose": "圣何塞", "Seattle": "西雅图"
}

def get_node_location(ip_full):
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    try:
        with maxminddb.open_database(DB_FILE) as reader:
            data = reader.get(ip)
            if data:
                country_code = data.get('country', {}).get('iso_code', 'UN')
                city_en = data.get('city', {}).get('names', {}).get('en', 'Anycast')
                city_cn = CITY_CN.get(city_en, city_en).replace(" ", "")
                
                # --- 中国视角校准逻辑 ---
                # 如果数据库在北美识别为 US，但网段属于亚太常见优化段，强制纠正
                if country_code == "US" and ip.startswith(("104.16", "104.17", "172.64", "162.159")):
                    return f"HK_亚太优化"
                
                return f"{country_code}_{city_cn}"
    except: pass
    return "UN_Unknown"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES:
        return

    print(f"[*] 正在分析: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_map = {executor.submit(get_node_location, l.split('#')[0]): l for l in lines}
        for future in as_completed(future_map):
            original = future_map[future]
            loc = future.result()
            
            ip_part = original.split('#')[0]
            # IPv6 括号处理
            if ":" in ip_part and not ip_part.startswith("["):
                ip_part = f"[{ip_part}]"
            
            note = original.split('#')[1] if '#' in original else ""
            new_results.append(f"{ip_part}#{loc}_{note}")
            summary_set.add(f"{ip_part}#{loc}_{note}")

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_results) + '\n')

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    
    if not os.path.exists(DB_FILE):
        print(f"[!] 数据库 {DB_FILE} 缺失，跳过识别")
        return

    summary_ips = set()
    try:
        files = [f for f in os.listdir(BASE_DIR) if f.endswith('.txt')]
        for f in files:
            process_file(f, summary_ips)
        
        if summary_ips:
            with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), "w", encoding="utf-8") as f:
                f.write('\n'.join(sorted(list(summary_ips))) + '\n')
        print("[✓] 任务已完成")
    except Exception as e:
        print(f"[X] 运行出错: {e}")

if __name__ == "__main__":
    main()
