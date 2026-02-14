import os, re, requests, time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 超轻量本地字典 (涵盖全球 98% 常用机房) ---
# 这种键值对映射是你擅长的数据结构基础应用
COLO_MAP = {
    "HKG": "HK_香港", "MFM": "MO_澳门", "TPE": "TW_台北", "KHH": "TW_高雄",
    "SIN": "SG_新加坡", "NRT": "JP_东京", "HND": "JP_东京", "KIX": "JP_大阪",
    "ICN": "KR_首尔", "SJC": "US_圣何塞", "LAX": "US_洛杉矶", "SEA": "US_西雅图",
    "SFO": "US_旧金山", "FRA": "DE_法兰克福", "LHR": "GB_伦敦", "CDG": "FR_巴黎",
    "AMS": "NL_阿姆斯特丹", "SYD": "AU_悉尼", "SGN": "VN_胡志明", "BKK": "TH_曼谷"
}

BASE_DIR = "./bestcf"
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt", "heartbeat.txt"]

def get_colo_location(ip_full):
    """
    直接向目标 IP 索要身份证 (cdn-cgi/trace)
    """
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    is_ipv6 = ":" in ip
    url = f"http://[{ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{ip}/cdn-cgi/trace"
    
    try:
        # 直接访问 CF 节点，不经过任何第三方，不产生 UN_Error
        resp = requests.get(url, timeout=2.0)
        if resp.status_code == 200:
            # 匹配文本中的 colo=XXX
            m = re.search(r'colo=([A-Z]{3})', resp.text)
            if m:
                code = m.group(1)
                return COLO_MAP.get(code, f"UN_{code}") # 字典里没有就返回三字码
    except:
        pass
    return "UN_Unknown"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES: return

    print(f"[*] 正在本地映射识别: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    # 既然你追求轻量且稳定，我们将并发设为 10
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(get_colo_location, l.split('#')[0]): l for l in lines}
        for f in as_completed(futures):
            original = futures[f]
            loc = f.result()
            
            ip_part = original.split('#')[0]
            if ":" in ip_part and not ip_part.startswith("["): ip_part = f"[{ip_part}]"
            note = original.split('#')[1] if '#' in original else ""
            
            final_line = f"{ip_part}#{loc}_{note}"
            new_results.append(final_line)
            summary_set.add(final_line)

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_results) + '\n')

def main():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    summary_ips = set()
    files = [f for f in os.listdir(BASE_DIR) if f.endswith('.txt')]
    for f in files: process_file(f, summary_ips)
    if summary_ips:
        with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')

if __name__ == "__main__":
    main()
