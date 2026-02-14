import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor

# 探测 Cloudflare 节点的函数
def get_cf_colo(ip_with_brackets):
    # 移除方括号以便请求
    clean_ip = ip_with_brackets.replace('[', '').replace(']', '')
    # 如果是 IPv6，请求格式需要处理
    url = f"http://[{clean_ip}]/cdn-cgi/trace" if ':' in clean_ip else f"http://{clean_ip}/cdn-cgi/trace"
    
    try:
        # 设置 2 秒超时，直接请求 Cloudflare 诊断接口
        response = requests.get(url, timeout=2, headers={'Host': 'da.gd'})
        if response.status_code == 200:
            # 在返回的文本中查找 colo=XXX
            match = re.search(r'colo=([A-Z]{3})', response.text)
            if match:
                return match.group(1)
    except:
        pass
    return "UNK" # 未知节点

def process_line(line):
    if '#' not in line:
        return line
    
    parts = line.strip().split('#')
    ip_part = parts[0]
    comment = parts[1] if len(parts) > 1 else ""
    
    # 获取该 IP 的实测节点代码
    colo = get_cf_colo(ip_part)
    return f"{ip_part}#[{colo}]{comment}\n"

def main():
    target_dir = './bestcf/'
    # 需要处理的文件列表
    files_to_process = [
        'cmcc-ip.txt', 'cucc-ip.txt', 'ctcc-ip.txt', 'bestcf-ip.txt', 'proxy-ip.txt'
    ]

    for filename in files_to_process:
        path = os.path.join(target_dir, filename)
        if not os.path.exists(path):
            continue
            
        with open(path, 'r') as f:
            lines = f.readlines()

        # 使用线程池并发探测，加快速度
        with ThreadPoolExecutor(max_workers=20) as executor:
            new_lines = list(executor.map(process_line, lines))

        with open(path, 'w') as f:
            f.writelines(new_lines)
        print(f"Processed {filename}")

if __name__ == "__main__":
    main()
