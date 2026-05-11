import socket
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 数据源
domains = [
    'proxy.xinyitang.dpdns.org',
    'proxyip.sg.fxxk.dedyn.io',
    'ProxyIP.sg.CMLiussss.net',
    'ProxyIP.jp.CMLiussss.net',
    'ProxyIP.kr.CMLiussss.net',
]
remote_url = "https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/bestproxy.txt"

# 输出配置
OUTPUT_FILE = "proxyip.txt"
CHECK_PORT = 443  # 既然已知主要是 443，直接锁定探测
TIMEOUT = 3       # 优选 IP 超过 3 秒就没意义了
MAX_THREADS = 50  # Socket 探测很轻量，可以加大并发

# =========================
# 1. 域名解析
# =========================
def resolve_all_ips(domain):
    ips = set()
    try:
        # 获取所有解析记录（A记录）
        infos = socket.getaddrinfo(domain, None, socket.AF_INET)
        for item in infos:
            ips.add(item[4][0])
    except Exception as e:
        logging.debug(f"解析域名 {domain} 失败: {e}")
    return ips

# =========================
# 2. 核心探测函数 (TCP 握手)
# =========================
def tcp_ping(ip, port):
    """
    通过 TCP 三次握手测试延迟，不涉及 HTTP 协议，兼容性最强
    """
    start_time = time.perf_counter()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        # connect_ex 返回 0 表示成功
        result = sock.connect_ex((ip, port))
        sock.close()
        
        if result == 0:
            end_time = time.perf_counter()
            delay = round((end_time - start_time) * 1000, 2) # 毫秒
            return (ip, delay)
    except Exception:
        pass
    return None

# =========================
# 3. 主程序
# =========================
def main():
    start_all = time.time()
    all_ips = set()

    # 1️⃣ 收集域名解析出来的 IP
    for d in domains:
        ips = resolve_all_ips(d)
        all_ips.update(ips)
    
    # 2️⃣ 收集远程列表中的 IP
    try:
        resp = requests.get(remote_url, timeout=10)
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                # 处理可能带端口的格式如 1.1.1.1:443
                ip = line.split(':')[0].strip()
                if ip:
                    all_ips.add(ip)
    except Exception as e:
        logging.warning(f"获取远程列表失败: {e}")

    logging.info(f"💡 原始 IP 总数: {len(all_ips)}")

    # 3️⃣ 并发探测
    valid_results = []
    logging.info(f"🚀 开始对端口 {CHECK_PORT} 进行并发探测 (线程数: {MAX_THREADS})...")
    
    with ThreadPoolExecutor(MAX_THREADS) as executor:
        # 提交任务
        future_to_ip = {executor.submit(tcp_ping, ip, CHECK_PORT): ip for ip in all_ips}
        
        for future in as_completed(future_to_ip):
            res = future.result()
            if res:
                valid_results.append(res)

    # 4️⃣ 排序与保存
    # 按延迟从小到大排序
    valid_results.sort(key=lambda x: x[1])

    if valid_results:
        unique_ips = []
        seen = set()
        for ip, delay in valid_results:
            if ip not in seen:
                unique_ips.append(ip)
                seen.add(ip)
        
        with open(OUTPUT_FILE, 'w') as f:
            f.write("\n".join(unique_ips) + "\n")
            
        logging.info(f"✅ 更新成功！筛选出 {len(unique_ips)} 个可用 IP (最快延迟: {valid_results[0][1]}ms)")
    else:
        logging.error("❌ 未能筛选出任何可用 IP，请检查网络环境。")

    logging.info(f"⏱️ 总耗时: {round(time.time() - start_all, 2)}s")

if __name__ == "__main__":
    main()
