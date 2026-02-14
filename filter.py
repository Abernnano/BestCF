import os
import re
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置 ---
BASE_DIR = "./bestcf"
# 排除不需要识别的文件
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt", "heartbeat.txt"]
# 大陆视角 API (太平洋电脑网)
API_URL = "http://whois.pconline.com.cn/ipJson.jsp?ip={}&json=true"

# 关键词汉化映射，对齐你的 .ini 规则
REGION_MAP = {
    "香港": "HK_香港",
    "美国": "US_美国",
    "日本": "JP_日本",
    "台湾": "TW_台湾",
    "新加坡": "SG_新加坡",
    "韩国": "KR_韩国",
    "圣何塞": "US_圣何塞",
    "洛杉矶": "US_洛杉矶"
}

def get_mainland_location(ip_full):
    # 剥离端口和括号
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    
    try:
        # 调用国内 API
        resp = requests.get(API_URL.format(ip), timeout=5)
        # API 返回 GBK 编码，需要正确处理
        resp.encoding = 'gbk'
        data = resp.json()
        addr = data.get('addr', '')
        
        # 识别逻辑：匹配关键词
        for key, val in REGION_MAP.items():
            if key in addr:
                return val
        
        # 如果没匹配到常见区域，返回 API 原始地点前缀
        clean_addr = addr.split(' ')[0] if ' ' in addr else addr
        return f"UN_{clean_addr[:10]}"
    except Exception as e:
        return "UN_Error"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES:
        return

    print(f"[*] 正在调用大陆 API 识别: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    # 限制并发，防止被 API 封锁
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {executor.submit(get_mainland_location, l.split('#')[0]): l for l in lines}
        for future in as_completed(future_map):
            original = future_map[future]
            loc_label = future.result()
            
            ip_part = original.split('#')[0]
            if ":" in ip_part and not ip_part.startswith("["):
                ip_part = f"[{ip_part}]"
            
            note = original.split('#')[1] if '#' in original else ""
            final_line = f"{ip_part}#{loc_label}_{note}"
            new_results.append(final_line)
            summary_set.add(final_line)
            # 增加极小延迟
            time.sleep(0.2)

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_results) + '\n')

def main():
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)

    summary_ips = set()
    try:
        files = [f for f in os.listdir(BASE_DIR) if f.endswith('.txt')]
        for f in files:
            process_file(f, summary_ips)
        
        if summary_ips:
            with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), "w", encoding="utf-8") as f:
                f.write('\n'.join(sorted(list(summary_ips))) + '\n')
        print("[✓] 大陆视角识别任务已完成")
    except Exception as e:
        print(f"[X] 运行出错: {e}")

if __name__ == "__main__":
    main()
