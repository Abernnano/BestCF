import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor

# 1. 强制在进程级屏蔽所有代理环境变量
os.environ['NO_PROXY'] = '*'
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy']:
    if key in os.environ:
        del os.environ[key]

# 2. 定义 Cloudflare 节点映射表
COLO_MAP = {
    "HKG": "香港", "TPE": "台北", "SGP": "新加坡", "NRT": "东京", 
    "KIX": "大阪", "ICN": "首尔", "BKK": "曼谷", "MNL": "马尼拉",
    "KUL": "吉隆坡", "LAX": "洛杉矶", "SJC": "圣何塞", "SEA": "西雅图",
    "IAD": "华盛顿", "FRA": "法兰克福", "LHR": "伦敦", "CAN": "广州",
    "SHA": "上海", "BJS": "北京", "HGH": "杭州", "CTU": "成都"
}

def get_real_colo(ip_str):
    """核心：直连 Cloudflare 获取路由节点"""
    clean_ip = ip_str.replace('[', '').replace(']', '').strip()
    is_ipv6 = ':' in clean_ip
    url = f"http://[{clean_ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{clean_ip}/cdn-cgi/trace"
    
    try:
        # trust_env=False 关键：忽略一切本地翻墙工具配置
        session = requests.Session()
        session.trust_env = False 
        
        # 必须模拟 Host 头部，否则某些优选 IP 会拒绝连接
        response = session.get(url, timeout=2.5, headers={'Host': 'da.gd'})
        if response.status_code == 200:
            match = re.search(r'colo=([A-Z]{3})', response.text)
            if match:
                code = match.group(1)
                return COLO_MAP.get(code, code)
    except:
        pass
    return "未知"

def process_file(file_path):
    if not os.path.exists(file_path):
        return
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    def update_line(line):
        line = line.strip()
        if not line or '#' not in line:
            return line + "\n"
        
        ip_part, tag_part = line.split('#', 1)
        # 本地实测识别
        location = get_real_colo(ip_part)
        return f"{ip_part}#[{location}]{tag_part}\n"

    # 提高并发到 20 线程
    with ThreadPoolExecutor(max_workers=20) as executor:
        new_lines = list(executor.map(update_line, lines))

    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

if __name__ == "__main__":
    base_dir = "./bestcf/"
    # 定义需要识别的文件列表
    target_files = ['cmcc-ip.txt', 'cucc-ip.txt', 'ctcc-ip.txt', 'bestcf-ip.txt', 'proxy-ip.txt']
    
    print("开始本地视角节点识别...")
    for filename in target_files:
        path = os.path.join(base_dir, filename)
        if os.path.exists(path):
            print(f"正在分析: {filename}")
            process_file(path)
    print("识别任务结束")
