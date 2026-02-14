import os
import re
from qqwry import QQWry
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 核心配置 ---
BASE_DIR = "./bestcf"
DB_FILE = "qqwry.dat"
# 严格排除不处理的文件
EXCLUDE_FILES = ["proxy-ip.txt", "bestcf-domain.txt", "heartbeat.txt"]

# 加载数据库 (Binary Search Tree 结构)
q = QQWry()
q.load_file(DB_FILE)

def get_location(ip_full):
    # 彻底剥离端口和括号
    ip = re.sub(r'\[|\]|:\d+$', '', ip_full).strip()
    try:
        res = q.lookup(ip)
        if res:
            area, isp = res[0], res[1]
            # 逻辑映射：将数据库描述转化为订阅转换能识别的关键词
            code = "UN"
            if "香港" in area: code = "HK"
            elif any(x in area for x in ["美国", "圣何塞", "洛杉矶", "西雅图", "芝加哥"]): code = "US"
            elif "日本" in area: code = "JP"
            elif "台湾" in area: code = "TW"
            elif "新加坡" in area: code = "SG"
            elif "韩国" in area: code = "KR"
            elif "欧洲" in area or any(x in area for x in ["德国", "法国", "英国"]): code = "EU"
            
            # 提取城市名，去除多余后缀
            city = area.replace("省", "").replace("市", "").replace("自治区", "")
            return f"{code}_{city}"
    except:
        pass
    return "UN_Unknown"

def process_file(filename, summary_set):
    fpath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(fpath) or filename in EXCLUDE_FILES:
        return

    print(f"[*] 离线识别任务: {filename}")
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    new_results = []
    # 离线查询极快，可提高并发
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_map = {executor.submit(get_location, l.split('#')[0]): l for l in lines}
        for future in as_completed(future_map):
            original = future_map[future]
            loc = future.result()
            
            ip_part = original.split('#')[0]
            # 补全 IPv6 括号
            if ":" in ip_part and not ip_part.startswith("["):
                ip_part = f"[{ip_part}]"
            
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
    
    # 生成万能总表 all-countries-ip.txt
    if summary_ips:
        with open(os.path.join(BASE_DIR, "all-countries-ip.txt"), 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(list(summary_ips))) + '\n')
    print("[✓] 全球节点云端识别完成")

if __name__ == "__main__":
    main()
