import socket
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 配置区 ---
domains = [
    'proxy.xinyitang.dpdns.org',
    'proxyip.fxxk.dedyn.io',
    'proxyip.sg.fxxk.dedyn.io',
]

remote_url = "https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/bestproxy.txt"

# 地区映射文件
REGION_FILES = {
    "SG": "sg.txt",
    "JP": "jp.txt",
    "US": "us.txt"
}

PORTS = [80, 443, 8080, 3128]
TEST_URLS = ["http://httpbin.org/ip"]
TIMEOUT = 5
MAX_THREADS = 20

# =========================
# 获取 IP 地区
# =========================
def get_region(ip):
    """
    通过 ip-api.com 获取国家代码 (ISO 3166-1 alpha-2)
    """
    try:
        # 使用 json 接口获取 countryCode
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=status,countryCode", timeout=5).json()
        if response.get("status") == "success":
            return response.get("countryCode")
    except:
        pass
    return "UNKNOWN"

# =========================
# 解析域名
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
# 测速/有效性检测
# =========================
def speed_test(ip, port):
    proxy = f"http://{ip}:{port}"
    try:
        start = time.time()
        r = requests.get(TEST_URLS[0], proxies={"http": proxy, "https": proxy}, timeout=TIMEOUT)
        if r.status_code == 200:
            delay = round(time.time() - start, 2)
            # 测速成功后，顺便查询地区
            region = get_region(ip)
            return (ip, region)
    except:
        pass
    return None

# =========================
# 主流程
# =========================
def main():
    all_ips = set()

    # 1. 收集 IP
    for d in domains:
        all_ips.update(resolve_all_ips(d))

    try:
        data = requests.get(remote_url, timeout=10).text
        for line in data.splitlines():
            ip = line.split(':')[0].strip()
            if ip: all_ips.add(ip)
    except Exception as e:
        logging.error(f"远程获取失败: {e}")

    logging.info(f"待处理 IP 总数: {len(all_ips)}")

    # 2. 多线程检测与分类
    # region_buckets 结构: {"SG": {ip1, ip2}, "JP": {ip3}, ...}
    region_buckets = {code: set() for code in REGION_FILES.keys()}

    with ThreadPoolExecutor(MAX_THREADS) as ex:
        futures = {ex.submit(speed_test, ip, port): (ip, port) 
                   for ip in all_ips for port in PORTS}

        for f in as_completed(futures):
            result = f.result()
            if result:
                ip, region = result
                if region in region_buckets:
                    region_buckets[region].add(ip)
                    logging.info(f"发现有效 IP: {ip} 地区: {region}")

    # 3. 保存文件 (纯 IP 格式)
    for code, filename in REGION_FILES.items():
        ips_to_save = list(region_buckets[code])
        if ips_to_save:
            with open(filename, 'w') as f:
                f.write("\n".join(ips_to_save) + "\n")
            logging.info(f"保存完毕: {filename} (共 {len(ips_to_save)} 个)")
        else:
            # 如果没搜集到，确保文件存在或清空旧内容（根据需求可选择不处理）
            with open(filename, 'w') as f:
                pass
            logging.warning(f"地区 {code} 未找到有效 IP")

if __name__ == "__main__":
    main()
