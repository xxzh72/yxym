# -*- coding: utf-8 -*-
import requests
import time
import concurrent.futures

# ============================================================
# 目标URL（优选域名源）
# ============================================================
TARGET_URL = 'https://bestcf.pages.dev/domain/Domain-Checked.txt'

# ============================================================
# 测速配置
# ============================================================
SPEED_TEST_TIMEOUT = 3                 # 单次请求超时（秒）
SPEED_TEST_REPEAT  = 2                 # 每个域名测几次取平均（HTTP请求较慢，缩减为2次）
MAX_WORKERS        = 30                # 并发线程数（HTTP请求消耗资源稍多，建议30-40）
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
# 2. 验证域名国内防墙情况并进行真正的 HTTP 探测
# ============================================================
def http_latency_once(domain, timeout):
    """
    通过真实的 HTTPS 请求来同时验证：
    1. 是否被墙 2. 真实应用层延迟 3. 是否可用（排除 Service Unavailable 等错误）
    """
    # 构造请求 URL，这里使用 https 协议
    url = f"https://{domain}"
    
    # 模拟常见浏览器 User-Agent，防止被部分节点拒绝
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        t0 = time.perf_counter()
        # allow_redirects=False 防止跳到其他无关网站导致测速不准
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=False)
        t1 = time.perf_counter()
        
        # 核心过滤：如果返回 502, 503, 504, 403 等异常状态码，直接废弃
        # Cloudflare 正常未配置完整的节点通常会返回 404 或 200，但绝对不会是 503 (Service Unavailable)
        if resp.status_code in [502, 503, 504, 429]:
            return None
            
        return (t1 - t0) * 1000  # 毫秒 (ms)
    except Exception:
        # 任何连接超时、SSL握手失败、被墙阻断，均返回 None
        return None

# ============================================================
# 3. 测速核心（单兵作战）
# ============================================================
def measure_domain(domain):
    latencies = []
    for _ in range(SPEED_TEST_REPEAT):
        ms = http_latency_once(domain, SPEED_TEST_TIMEOUT)
        if ms is not None:
            latencies.append(ms)
        time.sleep(0.1) # 稍作间隔
        
    if len(latencies) == SPEED_TEST_REPEAT: # 必须每次请求都成功才算稳定可用
        return domain, sum(latencies) / len(latencies)
    return domain, None

# ============================================================
# 4. 并发验证与测速
# ============================================================
def speedtest_all(domain_set):
    domain_list = list(domain_set)
    total = len(domain_list)
    print(f"[HTTP验证+测速] 共 {total} 个域名，并发={MAX_WORKERS}...\n")

    results = []
    done = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(measure_domain, d): d for d in domain_list}
        for fut in concurrent.futures.as_completed(futures):
            domain, ms = fut.result()
            done += 1
            if ms is not None:
                results.append((domain, ms))
                print(f"  [{done:>4}/{total}] {domain:<30} {ms:6.1f} ms [✅ 正常可用]")
            else:
                print(f"  [{done:>4}/{total}] {domain:<30} [❌ 墙拦截/服务不可用/超时]")

    return results

# ============================================================
# 5. 主流程
# ============================================================
def main():
    print("=" * 60)
    print("  CF 优选域名 HTTP服务可用性检测 + 测速排序")
    print("=" * 60)
    
    domain_set = fetch_domains(TARGET_URL)
    if not domain_set:
        print("未获取到任何有效域名，程序结束。")
        return

    results = speedtest_all(domain_set)

    # 按延迟从小到大排序
    results.sort(key=lambda x: x[1])
    top_results = results[:TOP_N]

    print(f"\n{'=' * 60}")
    print(f"  测速完成：服务完全正常 且 国内绿色可用 {len(results)} / {len(domain_set)} 个")
    print(f"  正在将速度最快的 {len(top_results)} 个高品质域名写入 {OUTPUT_FILE}")
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
