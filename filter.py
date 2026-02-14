import os
import re
import IP2Location
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置 ---
BASE_DIR = "./bestcf"
DB_FILE = "ip2location.bin"
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt"]

# 初始化 IP2Location 本地 API (采用高效的二进制搜索算法)
database = IP2Location.IP2Location(os.path.join(os.getcwd(), DB_FILE))

def get_pro_location(ip_full):
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    try:
        rec = database.get_all(ip)
        country_code = rec.country_short
        city = rec.city if rec.city != "-" else "Anycast"
        
        # --- 核心修复逻辑：大陆视角硬映射 ---
        # 很多 CF 的 IP 虽然物理在香港，但数据库会标为 US。
        # 我们根据常见的优选段进行关键词修正，确保触发你的 .ini 规则。
        if country_code == "US":
            # 如果是某些特定的香港 Anycast 段，强制修正
            if ip.startswith(("104.16", "104.17", "172.64")):
                country_code = "HK"
                city = "香港"
        
        # 汉化映射，确保匹配你的订阅转换规则
        city_map = {"San Jose": "圣何塞", "Los Angeles": "洛杉矶", "Hong Kong": "香港", 
                    "Taipei": "台北", "Tokyo": "东京", "Singapore": "新加坡"}
        city_cn = city_map.get(city, city).replace(" ", "")
        
        return f"{country_code}_{city_cn}"
    except:
        return "UN_Unknown"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES:
        return

    print(f"[*] IP2Location 识别中: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_map = {executor.submit(get_pro_location, line.split('#')[0]): line for line in lines}
        for future in as_completed(future_map):
            original = future_map[future]
            loc = future.result()
            
            ip_part = original.split('#')[0]
            if ":" in ip_part and not ip_part.startswith("["): ip_part = f"[{ip_part}]"
            note = original.split('#')[1] if '#' in original else ""
            
            final_line = f"{ip_part}#{loc}_{note}"
            new_results.append(final_line)
            summary_set.add(final_line)

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_results) + '\n')

def main():
    summary_ips = set()
    files = [f for f in os.listdir(BASE_DIR) if f.endswith('.txt')]
    for f in files:
        process_file(f, summary_ips)
    
    if summary_ips:
        with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
    print("[✓] 全球识别任务完成")

if __name__ == "__main__":
    main()
