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
MAX_WORKERS = 20 

# 全球 Cloudflare 核心机房映射表 (适配订阅转换 Emoji 规则)
COLO_INFO = {
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

requests.packages.urllib3.disable_warnings()

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip_full):
    # 彻底剥离端口和括号，如 [2606:4700::1]:443 -> 2606:4700::1
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    is_ipv6 = ":" in ip
    url = f"http://[{ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{ip}/cdn-cgi/trace"
    
    # 1. 尝试直连获取 Colo
    try:
        resp = requests.get(url, timeout=2.5, verify=False, proxies={'http': None, 'https': None})
        if resp.status_code == 200:
            colo_match = re.search(r'colo=([A-Z]{3})', resp.text)
            if colo_match:
                code = colo_match.group(1)
                if code in COLO_INFO:
                    country, city = COLO_INFO[code]
                    return f"{country}_{city}"
                return f"{code[:2]}_{code}" # 未知机房返回前两位国家码+代号
    except:
        pass

    # 2. 保底使用 API
    try:
        api_url = f"http://ip-api.com/json/{ip}?fields=countryCode,city"
        resp = requests.get(api_url, timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            return f"{data.get('countryCode','UN')}_{data.get('city','Unknown').replace(' ','')}"
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
        # 传入全量 IP 字符串（包含可能的端口）
        future_to_info = {executor.submit(get_ip_location, line.split('#')[0].strip()): line for line in lines}
        
        for future in as_completed(future_to_info):
            original_line = future_to_info[future]
            loc_info = future.result() 
            
            ip_part = original_line.split('#')[0].strip()
            # 格式化输出：给 IPv6 补上括号（如果不带端口但有冒号）
            clean_ip = re.sub(r'\[|\]', '', ip_part.split(':')[0] if ":" in ip_part else ip_part)
            if ":" in clean_ip and not ip_part.startswith("["):
                ip_part = f"[{ip_part}]"
                
            old_comment = original_line.split('#')[1].strip() if '#' in original_line else ""
            
            # 生成备注：US_洛杉矶_备注
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
    print("[SUCCESS] Classification finished.")

if __name__ == "__main__":
    main()
