import requests, re, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置 ---
BASE_DIR = "./bestcf"
# 排除列表：不进行识别的文件
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt"]
MAX_WORKERS = 20

# 全球核心机房映射表 (用于转换中文以触发 Emoji)
COLO_MAP = {
    "HKG": "香港", "TPE": "台北", "SIN": "新加坡", "NRT": "东京", "HND": "东京", "KIX": "大阪",
    "LAX": "洛杉矶", "SJC": "圣何塞", "SFO": "旧金山", "SEA": "西雅图", "ORD": "芝加哥",
    "IAD": "阿什本", "FRA": "法兰克福", "LHR": "伦敦", "CDG": "巴黎", "AMS": "阿姆斯特丹",
    "ICN": "首尔", "SYD": "悉尼", "CAN": "广州", "SZX": "深圳", "SHA": "上海"
}

def get_ip_info(ip_full):
    # 彻底剥离端口和括号
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    is_ipv6 = ":" in ip
    url = f"http://[{ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{ip}/cdn-cgi/trace"
    
    try:
        resp = requests.get(url, timeout=2.0, proxies={'http': None, 'https': None})
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                code = colo_match.group(1)
                # 获取国家码前两位 + 中文城市名
                city = COLO_MAP.get(code, code)
                return f"{code[:2]}_{city}"
    except: pass

    try: # API 保底
        api_url = f"http://ip-api.com/json/{ip}?fields=countryCode,city"
        r = requests.get(api_url, timeout=2.5)
        d = r.json()
        return f"{d.get('countryCode','UN')}_{d.get('city','Unknown').replace(' ','')}"
    except: return "UN_Unknown"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES: return
    
    print(f"[*] Processing: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(get_ip_info, line.split('#')[0]): line for line in lines}
        for future in as_completed(future_map):
            original_line = future_map[future]
            loc_info = future.result()
            
            ip_part = original_line.split('#')[0]
            old_note = original_line.split('#')[1] if '#' in original_line else ""
            
            # 格式化最终节点名：国家码_城市_原始备注
            final_line = f"{ip_part}#{loc_info}_{old_note}"
            new_results.append(final_line)
            summary_set.add(final_line)
            
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_results) + '\n')

def main():
    summary_ips = set()
    files = [f for f in os.listdir(BASE_DIR) if f.endswith('.txt')]
    for f in files:
        process_file(f, summary_ips)
    
    # 生成汇总文件 all-countries-ip.txt
    if summary_ips:
        with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
    print("[SUCCESS] Classification finished.")

if __name__ == "__main__":
    main()
