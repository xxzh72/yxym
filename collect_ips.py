import requests
import re
import os
import time
import socket
import concurrent.futures
from collections import defaultdict

# ============================================================
# 目标URL列表
# ============================================================
urls = [
    'https://api.uouin.com/cloudflare.html',
    'https://ip.164746.xyz',
    'https://ipdb.api.030101.xyz/?type=bestcf&country=true',
    'https://cf.090227.xyz',
    'https://stock.hostmonit.com/CloudFlareYes',
    'https://ip.haogege.xyz/',
    'https://ct.090227.xyz',
    'https://cmcc.090227.xyz',
    'https://addressesapi.090227.xyz/CloudFlareYes',
    'https://addressesapi.090227.xyz/ip.164746.xyz',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv4.txt'
]

# ============================================================
# 测速配置
# ============================================================
SPEED_TEST_PORT    = 443       # 测速端口（TCP连接测延迟）
SPEED_TEST_TIMEOUT = 3         # 单次连接超时（秒）
SPEED_TEST_REPEAT  = 3         # 每个IP测几次取平均
MAX_WORKERS        = 50        # 并发线程数
OUTPUT_FILE        = "ip.txt"  # 输出文件

# IPv4正则
ip_pattern = (
    r'(?:\d{1,2}|1\d{2}|2[0-4]\d|25[0-5])'
    r'(?:\.(?:\d{1,2}|1\d{2}|2[0-4]\d|25[0-5])){3}'
)

# ============================================================
# 1. 抓取IP
# ============================================================
def fetch_ips(urls):
    ip_set = set()
    for url in urls:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            matches = re.findall(ip_pattern, resp.text)
            ip_set.update(matches)
            print(f"[抓取] {url}  → +{len(matches)} 个IP")
        except Exception as e:
            print(f"[失败] {url}  → {e}")
    return ip_set

# ============================================================
# 2. TCP测延迟（单次）
# ============================================================
def tcp_latency_once(ip, port, timeout):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        t0 = time.perf_counter()
        result = sock.connect_ex((ip, port))
        t1 = time.perf_counter()
        sock.close()
        if result == 0:
            return (t1 - t0) * 1000  # ms
    except Exception:
        pass
    return None

# ============================================================
# 3. 测速（多次平均）
# ============================================================
def measure_ip(ip):
    latencies = []
    for _ in range(SPEED_TEST_REPEAT):
        ms = tcp_latency_once(ip, SPEED_TEST_PORT, SPEED_TEST_TIMEOUT)
        if ms is not None:
            latencies.append(ms)
        time.sleep(0.05)
    if latencies:
        return ip, sum(latencies) / len(latencies)
    return ip, None   # 不可达

# ============================================================
# 4. 并发测速所有IP
# ============================================================
def speedtest_all(ip_set):
    ip_list = list(ip_set)
    total = len(ip_list)
    print(f"\n[测速] 共 {total} 个IP，并发={MAX_WORKERS}，每IP测{SPEED_TEST_REPEAT}次...\n")

    results = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(measure_ip, ip): ip for ip in ip_list}
        for fut in concurrent.futures.as_completed(futures):
            ip, ms = fut.result()
            done += 1
            if ms is not None:
                results.append((ip, ms))
                print(f"  [{done:>4}/{total}] {ip:<18} {ms:6.1f} ms")
            else:
                print(f"  [{done:>4}/{total}] {ip:<18} 超时/不可达")

    return results

# ============================================================
# 5. 主流程
# ============================================================
def main():
    # --- 抓取 ---
    print("=" * 55)
    print("  CF 优选IP 抓取 + 测速排序")
    print("=" * 55)
    ip_set = fetch_ips(urls)
    print(f"\n[汇总] 去重后共 {len(ip_set)} 个唯一IP\n")

    if not ip_set:
        print("未抓取到任何IP，退出。")
        return

    # --- 测速 ---
    results = speedtest_all(ip_set)

    # --- 排序（延迟从小到大）---
    results.sort(key=lambda x: x[1])

    # --- 输出 ---
    print(f"\n{'=' * 55}")
    print(f"  测速完成：可达 {len(results)} / {len(ip_set)} 个")
    print(f"{'=' * 55}\n")
    print(f"{'排名':<6} {'IP地址':<20} {'平均延迟':>10}")
    print("-" * 40)
    for rank, (ip, ms) in enumerate(results, 1):
        print(f"#{rank:<5} {ip:<20} {ms:>8.1f} ms")

    # 只写IP，按速度排序
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ip, ms in results:
            f.write(f"{ip}\n")

    print(f"\n[保存] 已将 {len(results)} 个可达IP按延迟排序写入 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
