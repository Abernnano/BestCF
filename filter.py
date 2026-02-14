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
    # --- 核心节点 (优先级最高) ---
    "香港": "HK_香港", "台湾": "TW_台湾", "澳门": "MO_澳门",
    "日本": "JP_日本", "韩国": "KR_韩国", "新加坡": "SG_新加坡",
    "圣何塞": "US_圣何塞", "洛杉矶": "US_洛杉矶", "西雅图": "US_西雅图",
    "旧金山": "US_旧金山", "芝加哥": "US_芝加哥", "纽约": "US_纽约",
    
    # --- 亚洲 (Asia) ---
    "越南": "VN_越南", "泰国": "TH_泰国", "菲律宾": "PH_菲律宾",
    "马来西亚": "MY_马来西亚", "印度尼西亚": "ID_印度尼西亚", "印尼": "ID_印尼",
    "柬埔寨": "KH_柬埔寨", "缅甸": "MM_缅甸", "老挝": "LA_老挝",
    "文莱": "BN_文莱", "东帝汶": "TL_东帝汶", "印度": "IN_印度",
    "巴基斯坦": "PK_巴基斯坦", "孟加拉": "BD_孟加拉", "斯里兰卡": "LK_斯里兰卡",
    "哈萨克斯坦": "KZ_哈萨克斯坦", "乌兹别克斯坦": "UZ_乌兹别克斯坦",
    
    # --- 欧洲 (Europe) ---
    "德国": "DE_德国", "法兰克福": "DE_法兰克福", "英国": "GB_英国",
    "伦敦": "GB_伦敦", "法国": "FR_法国", "巴黎": "FR_巴黎",
    "荷兰": "NL_荷兰", "阿姆斯特丹": "NL_阿姆斯特丹", "意大利": "IT_意大利",
    "西班牙": "ES_西班牙", "俄罗斯": "RU_俄罗斯", "波兰": "PL_波兰",
    "瑞士": "CH_瑞士", "瑞典": "SE_瑞典", "挪威": "NO_挪威",
    "芬兰": "FI_芬兰", "丹麦": "DK_丹麦", "奥地利": "AT_奥地利",
    "爱尔兰": "IE_爱尔兰", "葡萄牙": "PT_葡萄牙", "希腊": "GR_希腊",
    "捷克": "CZ_捷克", "土耳其": "TR_土耳其", "乌克兰": "UA_乌克兰",
    
    # --- 北美洲与南美洲 (Americas) ---
    "美国": "US_美国", "加拿大": "CA_加拿大", "多伦多": "CA_多伦多",
    "温哥华": "CA_温哥华", "墨西哥": "MX_墨西哥", "巴西": "BR_巴西",
    "阿根廷": "AR_阿根廷", "智利": "CL_智利", "哥伦比亚": "CO_哥伦比亚",
    "秘鲁": "PE_秘鲁", "委内瑞拉": "VE_委内瑞拉",
    
    # --- 大洋洲 (Oceania) ---
    "澳大利亚": "AU_澳大利亚", "悉尼": "AU_悉尼", "墨尔本": "AU_墨尔本",
    "新西兰": "NZ_新西兰", "斐济": "FJ_斐济",
    
    # --- 中东与非洲 (Middle East & Africa) ---
    "阿联酋": "AE_阿联酋", "迪拜": "AE_迪拜", "沙特": "SA_沙特",
    "以色列": "IL_以色列", "卡塔尔": "QA_卡塔尔", "南非": "ZA_南非",
    "埃及": "EG_埃及", "尼日利亚": "NG_尼日利亚", "肯尼亚": "KE_肯尼亚",
    "摩洛哥": "MA_摩洛哥", "阿尔及利亚": "DZ_阿尔及利亚"
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
