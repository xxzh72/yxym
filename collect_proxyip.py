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

# =========================
# 解析域名（获取所有绑定的IP）
# =========================
def resolve_all_ips(domain):
    ips = set()
    try:
        infos = socket.getaddrinfo(domain, None)
        for item in infos:
            ips.add(item[4][0])
    except Exception:
        pass
    return ips

# =========================
# 第一阶段：快速连接测试
# =========================
def quick_check(ip, port):
    proxy = f"http://{ip}:{port}"
    try:
        # 仅尝试第一个测试地址
        r = requests.get(
            TEST_URLS[0],
            proxies={"http": proxy, "https": proxy},
            timeout=TIMEOUT
        )
        return r.status_code == 200
    except:
        return False

# =========================
# 第二阶段：详细测速
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
# 主程序
# =========================
def main():
    old_data = None
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r') as f:
            old_data = f.read()

    all_ips = set()

    # 1. 收集域名下的 IP
    for d in domains:
        all_ips.update(resolve_all_ips(d))

    # 2. 收集远程地址的 IP
    try:
        resp = requests.get(remote_url, timeout=10)
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                # 处理可能带端口的格式，只取冒号前的部分
                ip = line.split(':')[0].strip()
                if ip:
                    all_ips.add(ip)
    except Exception as e:
        logging.error(f"下载远程IP失败: {e}")

    logging.info(f"共收集到待检测 IP: {len(all_ips)}")

    # 3. 第一阶段：快速筛选
    candidates = []
    with ThreadPoolExecutor(MAX_THREADS) as ex:
        futures = {ex.submit(quick_check, ip, port): (ip, port)
                   for ip in all_ips for port in PORTS}
        for f in as_completed(futures):
            ip, port = futures[f]
            if f.result():
                candidates.append((ip, port))

    logging.info(f"初步筛选通过数量: {len(candidates)}")

    if not candidates:
        logging.warning("无可用候选，尝试直接使用前50个原始IP")
        candidates = [(ip, 80) for ip in list(all_ips)[:50]]

    # 4. 第二阶段：精确测速
    results = []
    with ThreadPoolExecutor(MAX_THREADS) as ex:
        futures = {ex.submit(speed_test, ip, port): (ip, port)
                   for ip, port in candidates}
        for f in as_completed(futures):
            res = f.result()
            if res:
                results.append(res)

    logging.info(f"最终测速成功数量: {len(results)}")

    # 5. 排序并写入文件（只保留IP且去重）
    if results:
        # 按延迟从低到高排序
        results.sort(key=lambda x: x[2])

        final_unique_ips = []
        seen = set()
        
        for ip, port, delay in results:
            if ip not in seen:
                final_unique_ips.append(ip)
                seen.add(ip)

        with open(OUTPUT_FILE, 'w') as f:
            for ip in final_unique_ips:
                f.write(f"{ip}\n")
        
        logging.info(f"文件更新成功！共写入 {len(final_unique_ips)} 个唯一 IP 地址")
    else:
        logging.warning("未能检测到任何有效 IP，保留旧数据。")
        if old_data:
            with open(OUTPUT_FILE, 'w') as f:
                f.write(old_data)

if __name__ == "__main__":
    main()
