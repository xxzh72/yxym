import socket
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.error

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

domains = [
    'proxy.xinyitang.dpdns.org',
    'proxyip.fxxk.dedyn.io',
    'proxyip.us.fxxk.dedyn.io',
    'proxyip.sg.fxxk.dedyn.io',
    'proxyip.jp.fxxk.dedyn.io',
    'proxyip.hk.fxxk.dedyn.io',
    'proxyip.aliyun.fxxk.dedyn.io',
    'proxyip.oracle.fxxk.dedyn.io',
    'proxyip.digitalocean.fxxk.dedyn.io',
    'ProxyIP.CMLiussss.net',
    'proxyip.oracle.cmliussss.net',
]

remote_url = "https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/bestproxy.txt"

OUTPUT_FILE = "proxyip.txt"

# 多端口支持（关键）
PORTS = [80, 443, 8080, 3128]

TEST_URL = "https://httpbin.org/ip"

MAX_THREADS = 50
TIMEOUT = 3


# =========================
# 获取域名所有 IP
# =========================
def resolve_all_ips(domain):
    ips = set()
    try:
        infos = socket.getaddrinfo(domain, None)
        for item in infos:
            ip = item[4][0]
            ips.add(ip)
    except Exception as e:
        logging.error(f"{domain} 解析失败: {e}")
    return ips


# =========================
# 测试代理 + 测速
# =========================
def test_proxy(ip, port):
    proxy = f"http://{ip}:{port}"

    proxy_handler = urllib.request.ProxyHandler({
        "http": proxy,
        "https": proxy
    })

    opener = urllib.request.build_opener(proxy_handler)

    start = time.time()

    try:
        req = urllib.request.Request(
            TEST_URL,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with opener.open(req, timeout=TIMEOUT) as resp:
            if resp.status == 200:
                delay = round(time.time() - start, 2)
                logging.info(f"✅ {ip}:{port} 延迟 {delay}s")
                return (ip, port, delay)

    except Exception:
        return None

    return None


# =========================
# 多端口检测
# =========================
def check_ip(ip):
    results = []
    for port in PORTS:
        result = test_proxy(ip, port)
        if result:
            results.append(result)
    return results


# =========================
# 主程序
# =========================
def main():
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

    all_ips = set()

    # 1️⃣ 域名解析
    logging.info("解析域名...")
    for domain in domains:
        ips = resolve_all_ips(domain)
        logging.info(f"{domain} -> {len(ips)} IP")
        all_ips.update(ips)

    # 2️⃣ 远程数据
    logging.info("获取远程 IP...")
    try:
        with urllib.request.urlopen(remote_url, timeout=10) as response:
            data = response.read().decode('utf-8')
            for line in data.splitlines():
                ip = line.split(':')[0].strip()
                if ip:
                    all_ips.add(ip)
    except Exception as e:
        logging.error(f"远程获取失败: {e}")

    logging.info(f"总 IP 数: {len(all_ips)}")

    # 3️⃣ 多线程检测
    valid_proxies = []

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {executor.submit(check_ip, ip): ip for ip in all_ips}

        for future in as_completed(futures):
            results = future.result()
            if results:
                valid_proxies.extend(results)

    # 4️⃣ 按延迟排序（核心）
    valid_proxies.sort(key=lambda x: x[2])

    # 5️⃣ 写入文件
    with open(OUTPUT_FILE, 'w') as f:
        for ip, port, delay in valid_proxies:
            f.write(f"{ip}:{port} # {delay}s\n")

    logging.info(f"完成！有效代理数: {len(valid_proxies)}")


if __name__ == "__main__":
    main()
