import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor

# 1. 强制屏蔽环境变量代理，确保直连探测
os.environ['NO_PROXY'] = '*'
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

# 常用节点中文映射
COLO_MAP = {
    "HKG": "香港", "TPE": "台北", "SGP": "新加坡", "NRT": "东京", 
    "KIX": "大阪", "ICN": "首尔", "LAX": "洛杉矶", "SJC": "圣何塞",
    "SEA": "西雅图", "IAD": "华盛顿", "FRA": "法兰克福", "LHR": "伦敦",
    "CAN": "广州", "SHA": "上海", "BJS": "北京", "CTU": "成都"
}

def get_real_colo(ip_str):
    """直接向 IP 请求 Cloudflare 诊断信息，获取真实连接节点"""
    clean_ip = ip_str.replace('[', '').replace(']', '').strip()
    is_ipv6 = ':' in clean_ip
    url = f"http://[{clean_ip}]/cdn-cgi/trace" if is_ipv6 else f"http://{clean_ip}/cdn-cgi/trace"
    
    try:
        # trust_env=False 禁止读取系统代理配置
        session = requests.Session()
        session.trust_env = False 
        
        # 针对 Cloudflare IP 必须携带正确的 Host 才能触发 trace
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
        if '#' not in line:
            return line
        ip_part, tag_part = line.strip().split('#', 1)
        # 探测真实节点
        colo = get_real_colo(ip_part)
        return f"{ip_part}#[{colo}]{tag_part}\n"

    # 并发处理提高速度
    with ThreadPoolExecutor(max_workers=15) as executor:
        new_lines = list(executor.map(update_line, lines))

    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"处理完成: {file_path}")

if __name__ == "__main__":
    base_path = "./bestcf/"
    # 按照顺序处理需要打标签的文件
    target_files = ['cmcc-ip.txt', 'cucc-ip.txt', 'ctcc-ip.txt', 'bestcf-ip.txt', 'proxy-ip.txt']
    
    for filename in target_files:
        full_path = os.path.join(base_path, filename)
        process_file(full_path)
