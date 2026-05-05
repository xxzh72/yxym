import socket
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

domains = [
    'proxy.xinyitang.dpdns.org',
    'proxyip.fxxk.dedyn.io',
    'proxyip.sg.fxxk.dedyn.io',
    'ProxyIP.sg.CMLiussss.net',
    'ProxyIP.jp.CMLiussss.net',
    'ProxyIP.kr.CMLiussss.net',
    'ProxyIP.CMLiussss.net',
]

remote_url = "https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/bestproxy.txt"

OUTPUT_FILE = "proxyip.txt"

PORTS = [443]

TEST_URLS = [
    "http://httpbin.org/ip",
    "http://ifconfig.me/ip",
    "https://api.ipify.org"
]

TIMEOUT = 5
MAX_THREADS = 20


# =========================
# 解析域名（全部IP）
# =========================
def resolve_all_ips(domain):
    ips = set()
    try:
        infos = socket.getaddrinfo(domain, None)
        for item in infos:
            ips.add(item[4][0])
    except:
        pass
    return ips


# =========================
# 第一阶段（宽松检测）
# =========================
def quick_check(ip, port):
    proxy = f"http://{ip}:{port}"
    try:
        r = requests.get(
            "http://example.com",
            proxies={"http": proxy},
            timeout=8,
            allow_redirects=True
        )
        return r.status_code < 500
    except:
        return False


# =========================
# 第二阶段（测速）
# =========================
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


# =========================
# 主流程
# =========================
def main():
    old_data = None

    # 读取旧数据（防止覆盖）
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r') as f:
            old_data = f.read()

    all_ips = set()

    # 1️⃣ 域名解析
    for d in domains:
        all_ips.update(resolve_all_ips(d))

    # 2️⃣ 远程IP
    try:
        data = requests.get(remote_url, timeout=10).text
        for line in data.splitlines():
            ip = line.split(':')[0].strip()
            if ip:
                all_ips.add(ip)
    except:
        pass

    logging.info(f"收集 IP: {len(all_ips)}")

    # =========================
    # 第一阶段：宽松筛选
    # =========================
    candidates = []

    with ThreadPoolExecutor(MAX_THREADS) as ex:
        futures = {ex.submit(quick_check, ip, port): (ip, port)
                   for ip in all_ips for port in PORTS}

        for f in as_completed(futures):
            ip, port = futures[f]
            if f.result():
                candidates.append((ip, port))

    logging.info(f"初筛通过: {len(candidates)}")

    # 👉 如果一个都没有 → 降级
    if not candidates:
        logging.warning("初筛为空，降级使用原始IP")
        candidates = [(ip, 80) for ip in list(all_ips)[:50]]

    # =========================
    # 第二阶段：测速
    # =========================
    results = []

    with ThreadPoolExecutor(MAX_THREADS) as ex:
        futures = {ex.submit(speed_test, ip, port): (ip, port)
                   for ip, port in candidates}

        for f in as_completed(futures):
            r = f.result()
            if r:
                results.append(r)

    logging.info(f"测速成功: {len(results)}")

    # 👉 如果测速也为空 → 用初筛结果
    if not results:
        logging.warning("测速为空，使用初筛结果")
        results = [(ip, port, 999) for ip, port in candidates]

    # 排序
    results.sort(key=lambda x: x[2])

    # =========================
    # 核心修改：只写IP且去重
    # =========================
    if results:
        # 使用 set 确保同一个 IP 不会因为不同端口写多次
        unique_ips = set()
        with open(OUTPUT_FILE, 'w') as f:
            for item in results:
                ip = item[0]  # 原程序 result 的第一个元素就是 IP
                if ip not in unique_ips:
                    f.write(f"{ip}\n")
                    unique_ips.add(ip)
        logging.info(f"更新成功: {len(unique_ips)}")
    else:
        logging.warning("完全失败，保留旧数据")
        if old_data:
            with open(OUTPUT_FILE, 'w') as f:
                f.write(old_data)


if __name__ == "__main__":
    main()
