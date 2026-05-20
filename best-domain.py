# -*- coding: utf-8 -*-
import requests
import re
import time
import socket
import concurrent.futures

# ============================================================
# 目标URL（优选域名源）
# ============================================================
TARGET_URL = 'https://bestcf.pages.dev/domain/Domain-Checked.txt'

# ============================================================
# 测速配置
# ============================================================
SPEED_TEST_PORT    = 443               # 测速端口（TCP连接测延迟）
SPEED_TEST_TIMEOUT = 3                 # 单次连接超时（秒）
SPEED_TEST_REPEAT  = 3                 # 每个域名测几次取平均
MAX_WORKERS        = 50                # 并发线程数
OUTPUT_FILE        = "best-domain.txt" # 输出文件
TOP_N              = 30                # 保存前多少个最快的域名

# ============================================================
# 1. 抓取与提取域名
# ============================================================
def fetch_domains(url):
    domain_set = set()
    print(f"[抓取] 正在从 {url} 获取域名...")
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        
        # 按行分割并清洗数据
        lines = resp.text.splitlines()
        for line in lines:
            domain = line.strip()
            # 过滤掉空行、注释或明显不是域名的行
            if domain and not domain.startswith('#') and '.' in domain:
                domain_set.add(domain)
                
        print(f"[成功] 提取到 {len(domain_set)} 个唯一域名\n")
    except Exception as e:
        print(f"[失败] 获取域名时发生错误: {e}\n")
    return domain_set

# ============================================================
# 2. TCP测延迟（单次）
# ============================================================
def tcp_latency_once(domain, port, timeout):
    try:
        # 创建连接套接字（同时支持IPv4和IPv6自动解析）
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        t0 = time.perf_counter()
        result = sock.connect_ex((domain, port))
        t1 = time.perf_counter()
        sock.close()
        if result == 0:
            return (t1 - t0) * 1000  # 转换为毫秒(ms)
    except Exception:
        pass
    return None

# ============================================================
# 3. 测速（多次平均）
# ============================================================
def measure_domain(domain):
    latencies = []
    for _ in range(SPEED_TEST_REPEAT):
        ms = tcp_latency_once(domain, SPEED_TEST_PORT, SPEED_TEST_TIMEOUT)
        if ms is not None:
            latencies.append(ms)
        time.sleep(0.05)  # 每次探测轻微间隔
        
    if latencies:
        return domain, sum(latencies) / len(latencies)
    return domain, None   # 不可达

# ============================================================
# 4. 并发测速所有域名
# ============================================================
def speedtest_all(domain_set):
    domain_list = list(domain_set)
    total = len(domain_list)
    print(f"[测速] 共 {total} 个域名，并发={MAX_WORKERS}，每域名测{SPEED_TEST_REPEAT}次...\n")

    results = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(measure_domain, d): d for d in domain_list}
        for fut in concurrent.futures.as_completed(futures):
            domain, ms = fut.result()
            done += 1
            if ms is not None:
                results.append((domain, ms))
                print(f"  [{done:>4}/{total}] {domain:<30} {ms:6.1f} ms")
            else:
                print(f"  [{done:>4}/{total}] {domain:<30} 超时/不可达")

    return results

# ============================================================
# 5. 主流程
# ============================================================
def main():
    print("=" * 60)
    print("  CF 优选域名 抓取 + 测速排序")
    print("=" * 60)
    
    # --- 抓取 ---
    domain_set = fetch_domains(TARGET_URL)
    if not domain_set:
        print("未获取到任何有效域名，程序结束。")
        return

    # --- 测速 ---
    results = speedtest_all(domain_set)

    # --- 排序（延迟从小到大）---
    results.sort(key=lambda x: x[1])

    # --- 筛选前 TOP_N 个 ---
    top_results = results[:TOP_N]

    # --- 输出展示 ---
    print(f"\n{'=' * 60}")
    print(f"  测速完成：可达 {len(results)} / {len(domain_set)} 个")
    print(f"  正在将速度最快的 {len(top_results)} 个域名写入 {OUTPUT_FILE}")
    print(f"{'=' * 60}\n")
    
    print(f"{'排名':<6} {'域名':<32} {'平均延迟':>10}")
    print("-" * 55)
    for rank, (domain, ms) in enumerate(top_results, 1):
        print(f"#{rank:<5} {domain:<32} {ms:>8.1f} ms")

    # --- 保存到文件 ---
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for domain, ms in top_results:
            f.write(f"{domain}\n")

    print(f"\n[保存] 已将最快的 {len(top_results)} 个域名成功写入 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
