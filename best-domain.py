# -*- coding: utf-8 -*-
import requests
import time
import concurrent.futures
from requests.adapters import HTTPAdapter

# ============================================================
# 目标URL（优选域名源）
# ============================================================
TARGET_URL = 'https://bestcf.pages.dev/domain/Domain-Checked.txt'

# ============================================================
# 极限提速配置
# ============================================================
SPEED_TEST_TIMEOUT = 0.5               # 激进超时：超过1.5秒直接淘汰（我们要的是极速节点）
SPEED_TEST_REPEAT  = 2                 # 每个域名测2次取平均
MAX_WORKERS        = 100                # 并发线程数拉满到 100
OUTPUT_FILE        = "best-domain.txt" # 输出文件
TOP_N              = 30                # 保存前多少个最快的域名

# 创建一个全局的高并发 Session，用于复用底层连接池
session = requests.Session()
adapter = HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS)
session.mount('http://', adapter)
session.mount('https://', adapter)

# 模拟浏览器 Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Connection": "keep-alive"
}

# ============================================================
# 1. 抓取与提取域名
# ============================================================
def fetch_domains(url):
    domain_set = set()
    print(f"[抓取] 正在从 {url} 获取域名...")
    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        
        lines = resp.text.splitlines()
        for line in lines:
            domain = line.strip()
            if domain and not domain.startswith('#') and '.' in domain:
                domain_set.add(domain)
                
        print(f"[成功] 提取到 {len(domain_set)} 个唯一域名\n")
    except Exception as e:
        print(f"[失败] 获取域名时发生错误: {e}\n")
    return domain_set

# ============================================================
# 2. 极致优化的 HTTP 探测
# ============================================================
def http_latency_once(domain, timeout):
    url = f"https://{domain}"
    try:
        t0 = time.perf_counter()
        # allow_redirects=False 严禁重定向，节约时间
        resp = session.get(url, headers=HEADERS, timeout=timeout, allow_redirects=False)
        t1 = time.perf_counter()
        
        # 拦截 502, 503, 504, 429 等坏节点
        if resp.status_code in [502, 503, 504, 429]:
            return None
            
        return (t1 - t0) * 1000  # ms
    except Exception:
        return None

# ============================================================
# 3. 测速核心
# ============================================================
def measure_domain(domain):
    latencies = []
    for _ in range(SPEED_TEST_REPEAT):
        ms = http_latency_once(domain, SPEED_TEST_TIMEOUT)
        if ms is not None:
            latencies.append(ms)
        else:
            # 只要有一次失败（超时/503/被墙），直接整网淘汰，不再浪费时间测第二次
            return domain, None
        
    if len(latencies) == SPEED_TEST_REPEAT:
        return domain, sum(latencies) / len(latencies)
    return domain, None

# ============================================================
# 4. 真正的高并发验证与测速
# ============================================================
def speedtest_all(domain_set):
    domain_list = list(domain_set)
    total = len(domain_list)
    print(f"[HTTP高并发测速] 共 {total} 个域名，线程并发={MAX_WORKERS}...\n")

    results = []
    done = 0
    
    # 使用 ThreadPoolExecutor 进行真正的多线程消耗
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(measure_domain, d): d for d in domain_list}
        for fut in concurrent.futures.as_completed(futures):
            domain, ms = fut.result()
            done += 1
            if ms is not None:
                results.append((domain, ms))
                print(f"  [{done:>4}/{total}] {domain:<30} {ms:6.1f} ms [✅ 优质]")
            else:
                # 缩减输出，不打印每次失败，只在后台默默过滤，大幅减少由于IO打印造成的卡顿
                if done % 10 == 0 or done == total:
                    print(f"  进度: [{done}/{total}]...")

    return results

# ============================================================
# 5. 主流程
# ============================================================
def main():
    t_start = time.time()
    print("=" * 60)
    print("  CF 优选域名 极限狂飙版（连接池 + 高并发）")
    print("=" * 60)
    
    domain_set = fetch_domains(TARGET_URL)
    if not domain_set:
        print("未获取到任何有效域名，程序结束。")
        return

    results = speedtest_all(domain_set)

    # 排序
    results.sort(key=lambda x: x[1])
    top_results = results[:TOP_N]

    print(f"\n{'=' * 60}")
    print(f"  测速完成！有效高品质域名共 {len(results)} 个")
    print(f"  总耗时: {time.time() - t_start:.1f} 秒")
    print(f"  正在将最快的 {len(top_results)} 个域名写入 {OUTPUT_FILE}")
    print(f"{'=' * 60}\n")
    
    print(f"{'排名':<6} {'域名':<32} {'平均延迟':>10}")
    print("-" * 55)
    for rank, (domain, ms) in enumerate(top_results, 1):
        print(f"#{rank:<5} {domain:<32} {ms:>8.1f} ms")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for domain, ms in top_results:
            f.write(f"{domain}\n")

    print(f"\n[保存] 成功将优质域名写入 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
