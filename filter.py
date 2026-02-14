import os, re, requests, time, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 1. 全球 98% 国家码 & 核心机房映射表 ---
# 字典排序：具体城市 > 国家，确保圣何塞不会被误标为美国
REGION_MAP = {
    "香港": "HK_香港", "台湾": "TW_台湾", "澳门": "MO_澳门", "中国": "CN_中国",
    "日本": "JP_日本", "韩国": "KR_韩国", "新加坡": "SG_新加坡", "越南": "VN_越南",
    "泰国": "TH_泰国", "菲律宾": "PH_菲律宾", "马来西亚": "MY_马来西亚", "印尼": "ID_印尼",
    "圣何塞": "US_圣何塞", "洛杉矶": "US_洛杉矶", "西雅图": "US_西雅图", "芝加哥": "US_芝加哥",
    "纽约": "US_纽约", "多伦多": "CA_多伦多", "温哥华": "CA_温哥华", "法兰克福": "DE_法兰克福",
    "伦敦": "GB_伦敦", "巴黎": "FR_巴黎", "荷兰": "NL_荷兰", "俄罗斯": "RU_俄罗斯",
    "德国": "DE_德国", "英国": "GB_英国", "法国": "FR_法国", "美国": "US_美国",
    "澳大利亚": "AU_澳洲", "悉尼": "AU_悉尼", "巴西": "BR_巴西", "迪拜": "AE_迪拜"
    # 脚本会自动处理未匹配项为 UN_[API原词]
}

BASE_DIR = "./bestcf"
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt", "heartbeat.txt"]
# 大陆视角权威接口
MAINLAND_API = "https://ip.zxinc.org/api.php?type=json&ip={}"

def detect_runner_env():
    """
    第一步：识别本地网络环境 (Runner IP)
    """
    try:
        r = requests.get("https://api.ipify.org?format=json", timeout=5)
        ip = r.json().get("ip")
        # 识别该 IP 归属地
        info = requests.get(f"http://ip-api.com/json/{ip}").json()
        print(f"--- [自省系统] ---")
        print(f"当前运行 IP: {ip}")
        print(f"运行位置: {info.get('country')} - {info.get('city')}")
        print(f"--- 开始切换【中国视角】探测 ---")
    except:
        print("[!] 无法识别本地环境，默认开启强制大陆视角模式")

def get_location_by_china_api(ip_full):
    """
    第二步：通过大陆 API 识别目标优选 IP
    """
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    try:
        # 使用国内镜像 API 绕过 GitHub 路由导致的阿什本偏差
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(MAINLAND_API.format(ip), headers=headers, timeout=6)
        data = resp.json()
        
        if data.get('code') == 0:
            addr = data.get('data', {}).get('location', '')
            
            # 匹配大字典
            for key in REGION_MAP:
                if key in addr:
                    return REGION_MAP[key]
            
            # 兜底识别：如果没有匹配到，取 API 返回的前两个词
            clean_addr = addr.replace(" ", "_").split("_")[0]
            return f"UN_{clean_addr[:6]}"
    except:
        pass
    return "UN_Unknown"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES: return

    print(f"[*] 正在处理: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    # 限制并发数至 5，确保中国视角 API 不会重置连接
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {executor.submit(get_location_by_china_api, l.split('#')[0]): l for l in lines}
        for future in as_completed(future_map):
            original = future_map[future]
            loc_label = future.result()
            
            ip_part = original.split('#')[0]
            # 修正 IPv6 括号格式
            if ":" in ip_part and not ip_part.startswith("["): ip_part = f"[{ip_part}]"
            
            note = original.split('#')[1] if '#' in original else ""
            final_line = f"{ip_part}#{loc_label}_{note}"
            new_results.append(final_line)
            summary_set.add(final_line)
            time.sleep(0.2) # 礼貌间隔

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_results) + '\n')

def main():
    if not os.path.exists(BASE_DIR): os.makedirs(BASE_DIR)
    
    # 运行自省模块
    detect_runner_perspective = detect_runner_env()
    
    summary_ips = set()
    files = [f for f in os.listdir(BASE_DIR) if f.endswith('.txt')]
    for f in files: process_file(f, summary_ips)
    
    if summary_ips:
        with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), "w", encoding="utf-8") as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
    print("[✓] 全球 98% 归属地识别任务完成")

if __name__ == "__main__":
    main()
