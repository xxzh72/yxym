import socket
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 配置区域
domains = [
    'proxy.xinyitang.dpdns.org',
    'proxyip.fxxk.dedyn.io',
    'proxyip.sg.fxxk.dedyn.io',
]

remote_url = "https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/bestproxy.txt"
OUTPUT_FILE = "proxyip.txt"
PORTS = [80, 443, 8080, 3128]
TEST_URLS = [
    "http://httpbin.org/ip",
    "http://ifconfig.me/ip",
    "https://api.ipify.org"
]
TIMEOUT = 5
MAX_THREADS = 20

def resolve_all_ips(domain):
    ips = set()
    try:
        infos = socket.getaddrinfo(domain, None)
        for item in infos:
            ips.add(item[4][0])
    except:
        pass
    return ips

def quick_check(ip, port):
    proxy = f"http://{ip}:{port}"
    try:
        r = requests.get(TEST_URLS[0], proxies={"http": proxy, "https": proxy}, timeout=TIMEOUT)
        return r.status_code == 200
    except:
        return False

def speed_test(ip, port):
    proxy = f"http://{ip}:{port}"
    for url in TEST_URLS:
        try:
            start = time.time()
            r = requests.get(url, proxies={"http": proxy, "https": proxy}, timeout=TIMEOUT)
            if r.status_code == 200:
                delay = round(time.time() - start, 2)
                return (ip, port, delay)
        except:
            continue
    return None

def main():
    old_data = None
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r') as f:
            old_data = f.read()

    all_ips = set()
    for d in domains:
        all_ips.update(resolve_all_ips(d))

    try:
        data = requests.get(remote_url, timeout=10).text
        for line in data.splitlines():
            ip = line.split(':')[0].strip()
            if ip:
                all_ips.add(ip)
    except:
        pass

    logging.info(f"收集 IP: {len(all_ips)}")

    candidates = []
    with ThreadPoolExecutor(MAX_THREADS) as ex:
        futures = {ex.submit(quick_check, ip, port): (ip, port) for ip in all_ips for port in PORTS}
        for f in as_completed(futures):
            ip, port = futures[f]
            if f.result():
                candidates.append((ip, port))

    logging.info(f"初筛通过: {len(candidates)}")

    if not candidates:
        logging.warning("初筛为空，降级使用原始IP")
        candidates = [(ip, 80) for ip in list(all_ips)[:50]]

    results = []
    with ThreadPoolExecutor(MAX_THREADS) as ex:
        futures = {ex.submit(speed_test, ip, port): (ip, port) for ip, port in candidates}
        for f in as_completed(futures):
            r = f.result()
            if r:
                results.append(r)

    logging.info(f"测速成功: {len(results)}")

    # ==========================================
    # 修改后的核心写入逻辑：只保留唯一 IP
    # ==========================================
    if results:
        # 按延迟排序（快的在前）
        results.sort(key=lambda x: x[2])
        
        final_ips = []
        seen = set()
        for ip, port, delay in results:
            if ip not in seen:
                final_ips.append(ip)
                seen.add(ip)

        with open(OUTPUT_FILE, 'w') as f:
            for ip in final_ips:
                f.write(f"{ip}\n")  # 👈 这里只写 IP，不写端口和备注
        
        logging.info(f"文件更新成功: 写入 {len(final_ips)} 个 IP")
    else:
        # 如果彻底没数据，为了防止 Actions 报错，我们至少写入一条空信息或保持原样
        logging.warning("完全没有可用数据，保留旧数据")
        if old_data:
            with open(OUTPUT_FILE, 'w') as f:
                f.write(old_data)

if __name__ == "__main__":
    main()
