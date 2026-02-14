import requests, re, os, sys, io
from concurrent.futures import ThreadPoolExecutor, as_completed

# 处理编码
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = "./bestcf"
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt", "heartbeat.txt"]
MAX_WORKERS = 20

# 扩展 Cloudflare 全球核心机房映射表 (涵盖 95% 以上常见节点)
COLO_MAP = {
    # 亚太 (中国视角最关注)
    "HKG": "香港", "MFM": "澳门", "TPE": "台北", "KHH": "高雄",
    "SIN": "新加坡", "NRT": "东京", "HND": "东京", "KIX": "大阪",
    "ICN": "首尔", "BKK": "曼谷", "KUL": "吉隆坡", "MNL": "马尼拉",
    "SGN": "胡志明市", "HAN": "河内", "JKT": "雅加达", "SYD": "悉尼",
    # 北美 (大陆电信/联通直连常见)
    "SJC": "圣何塞", "LAX": "洛杉矶", "SFO": "旧金山", "SEA": "西雅图",
    "PDX": "波特兰", "ORD": "芝加哥", "DFW": "达拉斯", "IAD": "阿什本",
    "JFK": "纽约", "EWR": "纽瓦克", "ATL": "亚特兰大", "MIA": "迈阿密",
    "YYZ": "多伦多", "YVR": "温哥华", "YUL": "蒙特利尔",
    # 欧洲
    "FRA": "法兰克福", "LHR": "伦敦", "CDG": "巴黎", "AMS": "阿姆斯特丹",
    "MRS": "马赛", "MAD": "马德里", "MXP": "米兰", "ZRH": "苏黎世",
    # 中国境内 (如有移动合作节点)
    "CAN": "广州", "SZX": "深圳", "PVG": "上海", "SHA": "上海", "PEK": "北京", "BJS": "北京"
}

def get_accurate_location(ip_full):
    # 彻底剥离端口和括号
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    is_ipv6 = ":" in ip
    url = f"http://[{ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{ip}/cdn-cgi/trace"
    
    # 1. 优先通过 CF Trace 识别 Colo 代码
    try:
        resp = requests.get(url, timeout=2.0, proxies={'http': None, 'https': None})
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                code = colo_match.group(1)
                # 转换城市，找不到则保留三字码
                city = COLO_MAP.get(code, code)
                # 提取国家码 (通过 IP-API 辅助获取)
                return f"{code[:2]}_{city}" 
    except: pass

    # 2. 保底 API (物理注册地)
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=countryCode,city", timeout=2.5)
        d = r.json()
        city_en = d.get('city', 'Unknown')
        return f"{d.get('countryCode','UN')}_{city_en.replace(' ','')}"
    except: return "UN_Unknown"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES: return
    
    print(f"[*] Analyzing: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_line = {executor.submit(get_accurate_location, line.split('#')[0]): line for line in lines}
        for future in as_completed(future_to_line):
            original_line = future_to_line[future]
            loc_info = future.result()
            
            ip_part = original_line.split('#')[0]
            if ":" in ip_part and not ip_part.startswith("["): ip_part = f"[{ip_part}]"
            old_note = original_line.split('#')[1] if '#' in original_line else ""
            
            # 格式化：国家码_城市_备注
            final_line = f"{ip_part}#{loc_info}_{old_note}"
            new_results.append(final_line)
            summary_set.add(final_line)
            
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_results) + '\n')

def main():
    summary_ips = set()
    for f in os.listdir(BASE_DIR):
        if f.endswith('.txt'): process_file(f, summary_ips)
    if summary_ips:
        with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')

if __name__ == "__main__":
    main()
