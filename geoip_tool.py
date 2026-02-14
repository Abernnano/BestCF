import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor

# 彻底屏蔽系统代理环境变量，强制 Python 直连
os.environ['NO_PROXY'] = '*'
for env_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    if env_var in os.environ:
        del os.environ[env_var]

# 更加丰富的 Cloudflare 节点映射
COLO_MAP = {
    "HKG": "香港", "TPE": "台北", "SGP": "新加坡", "NRT": "东京", 
    "KIX": "大阪", "ICN": "首尔", "BKK": "曼谷", "MNL": "马尼拉",
    "KUL": "吉隆坡", "LAX": "洛杉矶", "SJC": "圣何塞", "SEA": "西雅图",
    "IAD": "华盛顿", "FRA": "法兰克福", "LHR": "伦敦", "CTU": "成都",
    "CAN": "广州", "SHA": "上海", "BJS": "北京", "HGH": "杭州"
}

def get_real_colo(ip_str):
    """实测 IP 连接到的 Cloudflare 数据中心"""
    clean_ip = ip_str.replace('[', '').replace(']', '').strip()
    is_ipv6 = ':' in clean_ip
    # 构造 Cloudflare 诊断 URL
    url = f"http://[{clean_ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{clean_ip}/cdn-cgi/trace"
    
    try:
        # trust_env=False 关键：不读取电脑本地的代理配置（如 Clash/V2Ray）
        session = requests.Session()
        session.trust_env = False 
        
        # 这里的 Host 必须是 Cloudflare 上的域名，否则无法识别 trace
        response = session.get(url, timeout=2, headers={'Host': 'da.gd'})
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
        # 获取本地环境下的真实节点
        colo = get_real_colo(ip_part)
        # 拼接结果：IP#[节点]原始标签
        return f"{ip_part}#[{colo}]{tag_part}\n"

    # 使用 20 个线程并发探测，加快处理速度
    with ThreadPoolExecutor(max_workers=20) as executor:
        new_lines = list(executor.map(update_line, lines))

    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

if __name__ == "__main__":
    # 处理生成的所有 IP 文件
    base_dir = "./bestcf/"
    target_files = ['cmcc-ip.txt', 'cucc-ip.txt', 'ctcc-ip.txt', 'bestcf-ip.txt', 'proxy-ip.txt']
    
    for filename in target_files:
        path = os.path.join(base_dir, filename)
        if os.path.exists(path):
            print(f"正在分析节点归属: {filename}")
            process_file(path)
