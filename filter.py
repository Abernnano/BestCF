import requests
import re
import os
import sys
import io
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'filter.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 1. 强制直连：屏蔽系统代理
os.environ['no_proxy'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

if sys.platform.startswith('win'):
    # 推荐改用这种方式，它能更好地处理现有的缓冲区
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')

# --- 配置区 ---
CLASSIFY_FILES = ["cmcc-ip.txt", "cucc-ip.txt", "ctcc-ip.txt", "bestcf-ip.txt"]
BASE_DIR = "./bestcf"
SUMMARY_FILE = "all-countries-ip.txt"
OPTIMIZED_FILE = "optimized-colo-ip.txt"
MAX_WORKERS = 50  # 减少并发数避免连接池溢出
MAX_IPS_PER_COLO = 5
MAX_RETRIES = 3  # 增加重试次数提高可靠性

COLO_MAP = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "ICN": "KR", "TPE": "TW",
    "LAX": "US", "SJC": "US", "SEA": "US", "SFO": "US", "FRA": "DE", "LHR": "GB",
    "CDG": "FR", "AMS": "NL", "IAD": "US", "ORD": "US", "DFW": "US", "EWR": "US"
}

# 为直连探测创建session（禁用代理）
direct_session = requests.Session()
direct_session.trust_env = False
# 增加连接池大小，避免连接池溢出
adapter = requests.adapters.HTTPAdapter(
    max_retries=MAX_RETRIES,
    pool_connections=100,  # 增加连接池大小
    pool_maxsize=100       # 增加最大连接数
)
direct_session.mount('http://', adapter)
direct_session.mount('https://', adapter)

# 为API请求创建session（可以使用代理）
api_session = requests.Session()
api_session.trust_env = False  # 禁用环境代理，避免Clash影响
api_adapter = requests.adapters.HTTPAdapter(
    max_retries=MAX_RETRIES,
    pool_connections=50,
    pool_maxsize=50
)
api_session.mount('http://', api_adapter)
api_session.mount('https://', api_adapter)

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def get_flag(country_code):
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def get_ip_location(ip_line):
    """
    获取IP的地理位置信息
    优先使用直连探测获取colo信息，失败后使用在线API
    """
    raw_ip = ip_line.split('#')[0].strip()
    # 移除端口号
    if ':' in raw_ip and raw_ip.count(':') > 1:
        # IPv6地址，可能包含端口号
        if ']:' in raw_ip:
            raw_ip = raw_ip.split(']:')[0] + ']'
    elif ':' in raw_ip:
        # IPv4地址带端口号
        raw_ip = raw_ip.split(':')[0]
    
    clean_ip = raw_ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    
    # 优先：直连探测（使用直连session，确保不经过代理）
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    for retry in range(MAX_RETRIES):
        try:
            resp = direct_session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
            if resp.status_code == 200:
                colo = re.search(r'colo=([A-Z]{3})', resp.text)
                if colo:
                    colo_code = colo.group(1)
                    country_code = COLO_MAP.get(colo_code, colo_code)
                    logger.info(f"IP {raw_ip} 直连探测成功，colo: {colo_code}, 国家: {country_code}")
                    return country_code
        except Exception as e:
            logger.warning(f"IP {raw_ip} 直连探测失败 (尝试 {retry+1}/{MAX_RETRIES}): {str(e)}")
            time.sleep(0.5)  # 重试间隔

    # 保底：在线 API (处理本地无 v6 环境)
    for retry in range(MAX_RETRIES):
        try:
            resp = api_session.get(f"http://ip-api.com/json/{clean_ip}?fields=countryCode", timeout=3)
            if resp.status_code == 200:
                country_code = resp.json().get("countryCode")
                if country_code:
                    logger.info(f"IP {raw_ip} 在线API查询成功，国家: {country_code}")
                    return country_code
        except Exception as e:
            logger.warning(f"IP {raw_ip} 在线API查询失败 (尝试 {retry+1}/{MAX_RETRIES}): {str(e)}")
            time.sleep(0.5)  # 重试间隔
    
    logger.error(f"IP {raw_ip} 无法获取地理位置信息")
    return None

def evaluate_ip_performance(ip):
    """
    评估IP性能
    返回值：(延迟, 可用性, 分数)
    分数越高表示性能越好
    """
    # 移除端口号
    if ':' in ip and ip.count(':') > 1:
        # IPv6地址，可能包含端口号
        if ']:' in ip:
            ip = ip.split(']:')[0] + ']'
    elif ':' in ip:
        # IPv4地址带端口号
        ip = ip.split(':')[0]
    
    clean_ip = ip.replace('[', '').replace(']', '')
    is_ipv6 = ":" in clean_ip
    trace_ip = f"[{clean_ip}]" if is_ipv6 else clean_ip
    
    latency = float('inf')
    availability = 0
    throughput = 0
    
    # 测试延迟和可用性（使用直连session，确保不经过代理）
    for retry in range(MAX_RETRIES):
        try:
            start_time = time.time()
            resp = direct_session.get(f"http://{trace_ip}/cdn-cgi/trace", timeout=2, verify=False, headers=headers)
            if resp.status_code == 200:
                latency = (time.time() - start_time) * 1000  # 转换为毫秒
                availability = 1
                # 简单测试吞吐量：计算响应大小和时间的比率
                throughput = len(resp.content) / (time.time() - start_time + 0.001)  # 字节/秒
                break
        except Exception as e:
            logger.debug(f"IP {ip} 性能测试失败 (尝试 {retry+1}/{MAX_RETRIES}): {str(e)}")
            time.sleep(0.5)  # 重试间隔
    
    # 计算性能分数：延迟越低分数越高，可用性和吞吐量越高分数越高
    score = 0
    if latency < float('inf'):
        # 延迟分数：1000ms对应0分，0ms对应100分
        latency_score = max(0, 100 - (latency / 10))
        # 吞吐量分数：基于相对值，最高50分
        throughput_score = min(50, (throughput / 10000) * 50)  # 假设100KB/s对应满分
        score = latency_score + (50 * availability) + throughput_score
    
    logger.debug(f"IP {ip} 性能评估结果：延迟={latency:.2f}ms, 可用性={availability}, 吞吐量={throughput:.2f}B/s, 分数={score:.2f}")
    return (latency, availability, throughput, score)

def process_file(filename, summary_set):
    """
    处理单个IP文件，进行分类和汇总
    """
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path):
        logger.warning(f"文件 {filename} 不存在，跳过处理")
        return
    
    logger.info(f"开始处理文件：{filename}")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        
        logger.info(f"文件 {filename} 包含 {len(lines)} 个IP")
        
        categorized = {}
        success_count = 0
        failure_count = 0
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(get_ip_location, l): l for l in lines}
            for f in as_completed(futures):
                line = futures[f]
                try:
                    tag = f.result()
                    if tag:
                        ip = line.split('#')[0].strip()
                        note = line.split('#')[1].strip() if '#' in line else "Worker"
                        final = f"{ip}#{get_flag(tag)} {tag} | {note}"
                        if tag not in categorized: categorized[tag] = []
                        categorized[tag].append(final)
                        summary_set.add(final)
                        success_count += 1
                    else:
                        failure_count += 1
                except Exception as e:
                    logger.error(f"处理IP {line} 时出错: {str(e)}")
                    failure_count += 1
        
        # 保存分类结果
        for tag, items in categorized.items():
            tag_dir = os.path.join(BASE_DIR, tag)
            os.makedirs(tag_dir, exist_ok=True)
            output_path = os.path.join(tag_dir, filename)
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(items) + '\n')
                logger.info(f"已保存 {tag} 分类结果到 {output_path}，共 {len(items)} 个IP")
            except Exception as e:
                logger.error(f"保存分类结果到 {output_path} 时出错: {str(e)}")
        
        logger.info(f"文件 {filename} 处理完成：成功 {success_count} 个，失败 {failure_count} 个")
        
    except Exception as e:
        logger.error(f"处理文件 {filename} 时出错: {str(e)}")

def optimize_ips_by_colo():
    """
    二次筛选：按colo机场码分组，每个分组最多保留5个最优IP
    """
    summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
    if not os.path.exists(summary_path):
        logger.error("汇总文件不存在，请先运行分类步骤")
        return
    
    logger.info("开始按colo优化IP...")
    
    # 读取所有IP
    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        logger.info(f"读取到 {len(lines)} 个IP进行优化")
    except Exception as e:
        logger.error(f"读取汇总文件时出错: {str(e)}")
        return
    
    # 按colo分组
    colo_groups = {}
    for line in lines:
        # 提取colo信息
        match = re.search(r'\| (.*?)_\d+$', line)
        if not match:
            continue
        colo = match.group(1).split('-')[0]
        if colo not in colo_groups:
            colo_groups[colo] = []
        colo_groups[colo].append(line)
    
    logger.info(f"按colo分组完成，共 {len(colo_groups)} 个分组")
    
    # 对每个colo分组进行性能评估和筛选
    optimized_ips = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for colo, ips in colo_groups.items():
            logger.info(f"开始评估 {colo} 分组，共 {len(ips)} 个IP")
            # 提取IP地址
            ip_lines = []
            for line in ips:
                ip = line.split('#')[0].strip()
                ip_lines.append((ip, line))
            
            # 并行评估性能
            futures = {executor.submit(evaluate_ip_performance, ip): line for ip, line in ip_lines}
            results = []
            for f in as_completed(futures):
                line = futures[f]
                try:
                    latency, availability, throughput, score = f.result()
                    results.append((score, latency, availability, throughput, line))
                except Exception as e:
                    logger.error(f"评估IP性能时出错: {str(e)}")
            
            # 按分数排序，选择前MAX_IPS_PER_COLO个
            results.sort(reverse=True, key=lambda x: x[0])
            top_ips = results[:MAX_IPS_PER_COLO]
            
            # 添加到优化结果
            for score, latency, availability, throughput, line in top_ips:
                # 在注释中添加性能信息
                ip_part, note_part = line.split('#', 1)
                optimized_line = f"{ip_part}#{note_part} | 延迟: {latency:.2f}ms | 可用性: {availability} | 吞吐量: {throughput:.2f}B/s | 分数: {score:.2f}"
                optimized_ips.append(optimized_line)
            
            logger.info(f"{colo} 分组优化完成，选择了 {len(top_ips)} 个最优IP")
    
    # 保存优化结果
    if optimized_ips:
        output_path = os.path.join(BASE_DIR, OPTIMIZED_FILE)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(optimized_ips) + '\n')
            logger.info(f"优化结果保存成功，共 {len(optimized_ips)} 个IP")
        except Exception as e:
            logger.error(f"保存优化结果时出错: {str(e)}")
    else:
        logger.error("没有IP被优化")

def main():
    """
    主函数：执行IP分类和优化
    """
    start_time = time.time()
    logger.info("开始执行IP筛选和优化")
    
    if not os.path.exists(BASE_DIR):
        logger.info(f"创建目录: {BASE_DIR}")
        os.makedirs(BASE_DIR, exist_ok=True)
    
    summary = set()
    for f in CLASSIFY_FILES:
        process_file(f, summary)
    
    if summary:
        summary_path = os.path.join(BASE_DIR, SUMMARY_FILE)
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(sorted(list(summary))) + '\n')
            logger.info(f"汇总文件保存成功，共 {len(summary)} 个IP")
            # 执行二次筛选
            optimize_ips_by_colo()
        except Exception as e:
            logger.error(f"保存汇总文件时出错: {str(e)}")
    else:
        logger.warning("没有IP被处理")
    
    end_time = time.time()
    logger.info(f"IP筛选和优化完成，耗时: {end_time - start_time:.2f}秒")
    print("[SUCCESS] Classification and optimization done.")

if __name__ == "__main__":
    main()
