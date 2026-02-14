import requests, re, os, sys, io, time
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 核心配置 ---
BASE_DIR = "./bestcf"
MAX_WORKERS = 15 # 保护 API 频率

# 针对你订阅转换正则的中文名映射 (覆盖 90%+ 核心机房)
COLO_MAP = {
    # --- 中国大陆及港澳台 (直连最常见) ---
    "HKG": ("HK", "香港"), "MFM": ("MO", "澳门"), "TPE": ("TW", "台北"),
    "CAN": ("CN", "广州"), "SZX": ("CN", "深圳"), "SHA": ("CN", "上海"),
    "PVG": ("CN", "上海"), "BJS": ("CN", "北京"), "PEK": ("CN", "北京"),
    "CTU": ("CN", "成都"), "CKG": ("CN", "重庆"), "SIA": ("CN", "西安"),
    "TSN": ("CN", "天津"), "NKG": ("CN", "南京"), "HGH": ("CN", "杭州"),
    "TAO": ("CN", "青岛"), "WUX": ("CN", "无锡"), "CGO": ("CN", "郑州"),
    "CSX": ("CN", "长沙"), "KWL": ("CN", "桂林"), "SYX": ("CN", "三亚"),
    "KMG": ("CN", "昆明"), "FOC": ("CN", "福州"), "XMN": ("CN", "厦门"),
    
    # --- 亚太地区 ---
    "SIN": ("SG", "新加坡"), "BKK": ("TH", "曼谷"), "KUL": ("MY", "吉隆坡"),
    "MNL": ("PH", "马尼拉"), "SGN": ("VN", "胡志明市"), "HAN": ("VN", "河内"),
    "JKT": ("ID", "雅加达"), "NRT": ("JP", "东京"), "HND": ("JP", "东京"),
    "KIX": ("JP", "大阪"), "NGO": ("JP", "名古屋"), "FUK": ("JP", "福冈"),
    "ICN": ("KR", "首尔"), "SYD": ("AU", "悉尼"), "MEL": ("AU", "墨尔本"),
    "BNE": ("AU", "布里斯班"), "PER": ("AU", "珀斯"), "AKL": ("NZ", "奥克兰"),
    "BOM": ("IN", "孟买"), "DEL": ("IN", "新德里"), "MAA": ("IN", "金奈"),
    
    # --- 北美地区 ---
    "LAX": ("US", "洛杉矶"), "SJC": ("US", "圣何塞"), "SFO": ("US", "旧金山"),
    "SEA": ("US", "西雅图"), "PDX": ("US", "波特兰"), "LAS": ("US", "拉斯维加斯"),
    "PHX": ("US", "凤凰城"), "DEN": ("US", "丹佛"), "ORD": ("US", "芝加哥"),
    "DFW": ("US", "达拉斯"), "IAH": ("US", "休斯顿"), "ATL": ("US", "亚特兰大"),
    "MIA": ("US", "迈阿密"), "IAD": ("US", "阿什本"), "EWR": ("US", "纽瓦克"),
    "JFK": ("US", "纽约"), "BOS": ("US", "波士顿"), "YVR": ("CA", "温哥华"),
    "YYZ": ("CA", "多伦多"), "YUL": ("CA", "蒙特利尔"),
    
    # --- 欧洲地区 ---
    "LHR": ("GB", "伦敦"), "MAN": ("GB", "曼彻斯特"), "FRA": ("DE", "法兰克福"),
    "TXL": ("DE", "柏林"), "BER": ("DE", "柏林"), "DUS": ("DE", "杜塞尔多夫"),
    "AMS": ("NL", "阿姆斯特丹"), "CDG": ("FR", "巴黎"), "MRS": ("FR", "马赛"),
    "MAD": ("ES", "马德里"), "BCN": ("ES", "巴塞罗那"), "MXP": ("IT", "米兰"),
    "FCO": ("IT", "罗马"), "ZRH": ("CH", "苏黎世"), "VIE": ("AT", "维也纳"),
    "CPH": ("DK", "哥本哈根"), "ARN": ("SE", "斯德哥尔摩"), "OSL": ("NO", "奥斯陆"),
    "HEL": ("FI", "赫尔辛基"), "WAW": ("PL", "华沙"), "PRG": ("CZ", "布拉格"),
    "IST": ("TR", "伊斯坦布尔"), "ATH": ("GR", "雅典"), "DUB": ("IE", "都柏林"),
    
    # --- 其他 ---
    "GRU": ("BR", "圣保罗"), "GIG": ("BR", "里约热内卢"), "EZE": ("AR", "布宜诺斯艾利斯"),
    "JNB": ("ZA", "约翰内斯堡"), "DXB": ("AE", "迪拜")
}

def get_location(ip_full):
    # 剥离端口和括号
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    url = f"http://[{ip}]/cdn-cgi/trace" if ":" in ip else f"http://{ip}/cdn-cgi/trace"
    try:
        resp = requests.get(url, timeout=2.0, proxies={'http': None, 'https': None})
        if resp.status_code == 200:
            m = re.search(r'colo=([A-Z]{3})', resp.text)
            if m and m.group(1) in COLO_MAP:
                return f"{COLO_MAP[m.group(1)][0]}_{COLO_MAP[m.group(1)][1]}"
            if m: return f"{m.group(1)[:2]}_{m.group(1)}"
    except: pass
    
    try: # API 保底
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=countryCode,city", timeout=2.0)
        d = r.json()
        return f"{d.get('countryCode','UN')}_{d.get('city','Unknown').replace(' ','')}"
    except: return "UN_Unknown"

def process():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    all_ips = set()
    for fname in ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt"]:
        fpath = os.path.join(BASE_DIR, fname)
        if not os.path.exists(fpath): continue
        with open(fpath, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
            futures = {exe.submit(get_location, l.split('#')[0]): l for l in lines}
            for f in as_completed(futures):
                loc = f.result()
                ip_part = futures[f].split('#')[0]
                if ":" in ip_part and not ip_part.startswith("["): ip_part = f"[{ip_part}]"
                note = futures[f].split('#')[1] if '#' in futures[f] else ""
                new_line = f"{ip_part}#{loc}_{note}"
                results.append(new_line)
                all_ips.add(new_line)
        
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(results) + '\n')

    with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(list(all_ips))) + '\n')

if __name__ == "__main__":
    process()
