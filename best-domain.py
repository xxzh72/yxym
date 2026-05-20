# -*- coding: utf-8 -*-
import requests
import time
import socket
import concurrent.futures
from requests.adapters import HTTPAdapter

# ============================================================
# 目标URL（优选域名源）
# ============================================================
TARGET_URL = 'https://bestcf.pages.dev/domain/Domain-Checked.txt'

# ============================================================
# 测速配置
# ============================================================
MAX_WORKERS        = 100                # 并发线程数（全力拉满）
OUTPUT_FILE        = "best-domain.txt" # 输出文件
FINAL_TOP_N        = 30                # 最终保存的域名数量

# 阶段一：TCP 海选配置
STAGE1_TIMEOUT     = 1.5               # TCP 超时时间
STAGE1_REPEAT      = 2                 # TCP 测几次取平均
STAGE1_TOP_N       = 100               # 海选前多少个进入复赛

# 阶段二：HTTP 精选配置
STAGE2_TIMEOUT     = 2.0               # HTTP 超时时间
STAGE2_REPEAT      = 2                 # HTTP 验证次数（必须全通）

# 全局高并发 Session
session = requests.Session()
adapter = HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS)
session.mount('http://', adapter)
session.mount('https://', adapter)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ============================================================
# 1. 抓取与提取域名
# ============================================================
def fetch_domains(url):
    domain_set = set()
    print(f"[抓取] 正在从 {url} 获取域名...")
    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        for line in resp.text.splitlines():
            domain = line.strip()
            if domain and not domain.startswith('#') and '.' in domain:
                domain_set.add(domain)
        print(f"[成功] 提取到 {len(domain_set)} 个唯一域名\n")
    except Exception as e:
        print(f"[失败] 获取域名时发生错误: {e}\n")
    return domain_set

# ============================================================
# 2. 阶段一：TCP 延迟探测
# ============================================================
def tcp_latency_once(domain, timeout):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        t0 = time.perf_counter()
        result = sock.connect_ex((domain, 443))
        t1 = time.perf_counter()
        sock.close()
        if result == 0:
            return (t1 - t0) * 1000
    except Exception:
        pass
    return None

def measure_domain_stage1(domain):
    latencies = []
    for _ in range(STAGE1_REPEAT):
        ms = tcp_latency_once(domain, STAGE1_TIMEOUT)
        if ms is not None:
            latencies.append(ms)
        else:
            return domain, None  # 一次失败直接淘汰
    return domain, sum(latencies) / len(latencies)

# ============================================================
# 3. 阶段二：HTTP 可用性/防墙探测
# ============================================================
def http_latency_once(domain, timeout):
    url = f"https://{domain}"
    try:
        t0 = time.perf_counter()
        resp = session.get(url, headers=HEADERS, timeout=timeout, allow_redirects=False)
        t1 = time.perf_counter()
        
        # 核心过滤：剔除 503 Service Unavailable、502、504、429 等故障节点
        if resp.status_code in [502, 503, 504, 429]:
            return None
        return (t1 - t0) * 1000
    except Exception:
        return None  # 墙拦截、SSL握手失败、超时等统一归为 None

def measure_domain_stage2(domain):
    latencies = []
    for _ in range(STAGE2_REPEAT):
        ms = http_latency_once(domain, STAGE2_TIMEOUT)
        if ms is not None:
            latencies.append(ms)
        else:
            return domain, None  # 一次 HTTP 异常（如503）即刻淘汰
    return domain, sum(latencies) / len(latencies)

# ============================================================
# 主流程
# ============================================================
def main():
    t_start = time.time()
    print("=" * 60)
    print("  CF 优选域名 双阶段极速精选（TCP海选 -> HTTP精选）")
    print("=" * 60)
    
    domain_set = fetch_domains(TARGET_URL)
    if not domain_set:
        return

    # --------------------------------------------------------
    # 【第一阶段】TCP 海选前 100 名
    # --------------------------------------------------------
    domain_list = list(domain_set)
    total = len(domain_list)
    print(f"【阶段 1】开始 TCP 物理延迟海选，目标基数: {total} 个域名...")
    
    stage1_results = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(measure_domain_stage1, d): d for d in domain_list}
        for fut in concurrent.futures.as_completed(futures):
            domain, ms = fut.result()
            done += 1
            if ms is not None:
                stage1_results.append((domain, ms))
            if done % 50 == 0 or done == total:
                print(f"  海选进度: [{done}/{total}]...")

    # 按 TCP 延迟排序，取前 STAGE1_TOP_N (100) 个
    stage1_results.sort(key=lambda x: x[1])
    top_100 = stage1_results[:STAGE1_TOP_N]
    print(f"  海选完成！已筛选出物理延迟最低的 {len(top_100)} 个域名进入复赛。\n")

    if not top_100:
        print("没有域名通过第一阶段测试，程序结束。")
        return

    # --------------------------------------------------------
    # 【第二阶段】HTTP 精选（防墙 + 排除 503）
    # --------------------------------------------------------
    print(f"【阶段 2】开始对前 {len(top_100)} 个域名进行 HTTPS 防墙与可用性精选...")
    stage2_results = []
    
    # 仅对前 100 个域名开辟并发验证
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(measure_domain_stage2, d[0]): d[0] for d in top_100}
        for fut in concurrent.futures.as_completed(futures):
            domain, ms = fut.result()
            if ms is not None:
                stage2_results.append((domain, ms))
                print(f"  [✅ 绿色可用] {domain:<30} 实际业务延迟: {ms:6.1f} ms")
            else:
                print(f"  [❌ 阻断/503] {domain:<30}")

    # 最终排序，取前 FINAL_TOP_N (30) 个
    stage2_results.sort(key=lambda x: x[1])
    final_top_30 = stage2_results[:FINAL_TOP_N]

    # --------------------------------------------------------
    # 输出与保存
    # --------------------------------------------------------
    print(f"\n{'=' * 60}")
    print(f"  全部测试完成！")
    print(f"  总耗时: {time.time() - t_start:.1f} 秒 (速度提升约 99%)")
    print(f"  正在将最完美的 {len(final_top_30)} 个域名写入 {OUTPUT_FILE}")
    print(f"{'=' * 60}\n")
    
    print(f"{'排名':<6} {'黄金域名':<32} {'真实业务延迟':>10}")
    print("-" * 55)
    for rank, (domain, ms) in enumerate(final_top_30, 1):
        print(f"#{rank:<5} {domain:<32} {ms:>8.1f} ms")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for domain, ms in final_top_30:
            f.write(f"{domain}\n")

    print(f"\n[保存] 成功！")

if __name__ == "__main__":
    main()
