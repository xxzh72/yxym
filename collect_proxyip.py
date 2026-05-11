import socket
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
CHECK_PORT = 443
TIMEOUT = 3
MAX_THREADS = 50

# =========================
# 1. 域名解析
# =========================
def resolve_all_ips(domain):
    ips = set()
    try:
        infos = socket.getaddrinfo(domain, None, socket.AF_INET)
        for item in infos:
            ips.add(item[4][0])
    except Exception as e:
        logging.debug(f"解析域名 {domain} 失败: {e}")
    return ips

# =========================
# 2. TCP 探测
# =========================
def tcp_ping(ip, port):
    start_time = time.perf_counter()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)

        result = sock.connect_ex((ip, port))
        sock.close()

        if result == 0:
            delay = round((time.perf_counter() - start_time) * 1000, 2)
            return (ip, delay)

    except Exception:
        pass

    return None

# =========================
# 3. 获取 IP 地区
# =========================
def get_ip_location(ip):
    """
    返回类似 HK / SG / JP
    """
    try:
        url = f"http://ip-api.com/json/{ip}?fields=countryCode"
        r = requests.get(url, timeout=5)

        if r.status_code == 200:
            data = r.json()
            return data.get("countryCode", "UNKN")

    except Exception:
        pass

    return "UNKN"

# =========================
# 4. 主程序
# =========================
def main():
    start_all = time.time()

    all_ips = set()

    # 收集域名解析 IP
    for d in domains:
        all_ips.update(resolve_all_ips(d))

    # 收集远程 IP
    try:
        resp = requests.get(remote_url, timeout=10)

        if resp.status_code == 200:
            for line in resp.text.splitlines():
                ip = line.split(':')[0].strip()

                if ip:
                    all_ips.add(ip)

    except Exception as e:
        logging.warning(f"获取远程列表失败: {e}")

    logging.info(f"💡 原始 IP 总数: {len(all_ips)}")

    # 并发 TCP 探测
    valid_results = []

    logging.info(f"🚀 开始 TCP 探测...")

    with ThreadPoolExecutor(MAX_THREADS) as executor:

        future_to_ip = {
            executor.submit(tcp_ping, ip, CHECK_PORT): ip
            for ip in all_ips
        }

        for future in as_completed(future_to_ip):

            res = future.result()

            if res:
                valid_results.append(res)

    # 按延迟排序
    valid_results.sort(key=lambda x: x[1])

    if not valid_results:
        logging.error("❌ 没有可用 IP")
        return

    # 去重
    unique_ips = []
    seen = set()

    for ip, delay in valid_results:
        if ip not in seen:
            unique_ips.append((ip, delay))
            seen.add(ip)

    logging.info(f"🌍 开始查询地区信息...")

    # 保存
    with open(OUTPUT_FILE, "w") as f:

        for ip, delay in unique_ips:

            loc = get_ip_location(ip)

            line = f"{ip}#{loc}"

            f.write(line + "\n")

            logging.info(f"{line} ({delay}ms)")

    logging.info(
        f"✅ 完成，共 {len(unique_ips)} 个 IP，最快 {unique_ips[0][1]}ms"
    )

    logging.info(f"⏱️ 总耗时: {round(time.time() - start_all, 2)}s")


if __name__ == "__main__":
    main()
