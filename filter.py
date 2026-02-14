import os, re, requests, time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 全球 98% 核心机房映射表 (涵盖你的订阅转换分组需求) ---
COLO_MAP = {
    # 亚太地区
    "HKG": "HK_香港", "MFM": "MO_澳门", "TPE": "TW_台北", "KHH": "TW_高雄",
    "SIN": "SG_新加坡", "NRT": "JP_东京", "HND": "JP_东京", "KIX": "JP_大阪",
    "ICN": "KR_首尔", "BKK": "TH_曼谷", "KUL": "MY_吉隆坡", "SGN": "VN_胡志明",
    "HAN": "VN_河内", "MNL": "PH_马尼拉", "CGK": "ID_雅加达", "SYD": "AU_悉尼",
    # 北美地区
    "SJC": "US_圣何塞", "LAX": "US_洛杉矶", "SFO": "US_旧金山", "SEA": "US_西雅图",
    "ORD": "US_芝加哥", "DFW": "US_达拉斯", "IAD": "US_阿什本", "JFK": "US_纽约",
    "ATL": "US_亚特兰大", "MIA": "US_迈阿密", "YYZ": "CA_多伦多", "YVR": "CA_温哥华",
    # 欧洲地区
    "FRA": "DE_法兰克福", "LHR": "GB_伦敦", "CDG": "FR_巴黎", "AMS": "NL_阿姆斯特丹",
    "MRS": "FR_马赛", "MAD": "ES_马德里", "MXP": "IT_米兰", "ZRH": "CH_苏黎世",
    # 其他
    "DXB": "AE_迪拜", "JNB": "ZA_约翰内斯堡"
}

BASE_DIR = "./bestcf"
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt"]

def get_colo_info(ip_full):
    # 剥离端口和中括号
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    is_ipv6 = ":" in ip
    url = f"http://[{ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{ip}/cdn-cgi/trace"
    
    try:
        # 直接向优选IP发起请求，获取其真实的 Colo 机房代号
        resp = requests.get(url, timeout=1.5)
        if resp.status_code == 200:
            m = re.search(r'colo=([A-Z]{3})', resp.text)
            if m:
                code = m.group(1)
                return COLO_MAP.get(code, f"UN_{code}")
    except:
        pass
    return "UN_Unknown"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES:
        return

    print(f"[*] 正在本地探测识别: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    # 使用 ThreadPoolExecutor 提升云端处理效率
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {executor.submit(get_colo_info, l.split('#')[0]): l for l in lines}
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
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    summary_ips = set()
    files = [f for f in os.listdir(BASE_DIR) if f.endswith('.txt')]
    for f in files:
        process_file(f, summary_ips)
    
    # 生成汇总文件 all-countries-ip.txt 供订阅转换读取
    if summary_ips:
        with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
    print("[✓] 轻量化识别任务已完成")

if __name__ == "__main__":
    main()
