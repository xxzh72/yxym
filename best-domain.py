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
# 1.5 验证域名是否被中国防火墙（GFW）拦截
# ============================================================
def is_gfw_blocked(domain):
    """
    通过腾讯公共 DoH 接口模拟中国大陆境内解析。
    如果国内解析失败、超时，或无法建立 TCP 连接，则判定为被墙。
    """
    # 1. 检测 DNS 污染 / 拦截
    doh_url = f"https://dns.pub/dns-query?name={domain}&type=A"
    try:
        # 使用 DoH 获取腾讯 DNS 在国内解析出的 IP
        headers = {"accept": "application/dns-json"}
        resp = requests.get(doh_url, headers=headers, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            # 如果 Answer 为空，说明国内 DNS 无法解析该域名
            if "Answer" not in data or not data["Answer"]:
                return True
    except Exception:
        # 如果请求国内 DNS 接口自身超时或出错，谨慎起见先放行或视作异常
        pass

    # 2. 尝试用本地(当前环境)进行连接测试
    # 注：由于 GitHub Actions 服务器在海外，如果域名被 DNS 污染，海外服务器依然能解析出真 IP
    # 故此处配合上面的国内 DNS 状态双重校验
    try:
        # 尝试进行一次极简的 TCP 握手，若连基本的握手都失败则直接判定不可用
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        result = sock.connect_ex((domain, SPEED_TEST_PORT))
        sock.close()
        if result != 0:
            return True # 连不上，判定为被墙或死线
    except Exception:
        return True

    return False # 通过验证，未被墙

# ============================================================
# 2. TCP测延迟（单次）
# ============================================================
def tcp_latency_once(domain, port, timeout):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        t0 = time.perf_counter()
        result = sock.connect_ex((domain, port))
        t1 = time.perf_counter()
        sock.close()
        if result == 0:
            return (t1 - t0) * 1000  # ms
    except Exception:
        pass
    return None

# ============================================================
# 3. 测速与防墙过滤核心
# ============================================================
def measure_domain(domain):
    # 先验证是否被墙
    if is_gfw_blocked(domain):
        return domain, None, True # 被墙标记为 True
        
    latencies = []
    for _ in range(SPEED_TEST_REPEAT):
        ms = tcp_latency_once(domain, SPEED_TEST_PORT, SPEED_TEST_TIMEOUT)
        if ms is not None:
            latencies.append(ms)
        time.sleep(0.05)
        
    if latencies:
        return domain, sum(latencies) / len(latencies), False
    return domain, None, False   # 未被墙但单纯不可达

# ============================================================
# 4. 并发验证与测速
# ============================================================
def speedtest_all(domain_set):
    domain_list = list(domain_set)
    total = len(domain_list)
    print(f"[验证+测速] 共 {total} 个域名，并发={MAX_WORKERS}...\n")

    results = []
    blocked_count = 0
    done = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(measure_domain, d): d for d in domain_list}
        for fut in concurrent.futures.as_completed(futures):
            domain, ms, is_blocked = fut.result()
            done += 1
            if is_blocked:
                blocked_count += 1
                print(f"  [{done:>4}/{total}] {domain:<30} [❌ 已被墙/拦截]")
            elif ms is not None:
                results.append((domain, ms))
                print(f"  [{done:>4}/{total}] {domain:<30} {ms:6.1f} ms")
            else:
                print(f"  [{done:>4}/{total}] {domain:<30} [连接超时]")

    print(f"\n[统计] 过滤掉被墙/无效域名 {blocked_count} 个")
    return results

# ============================================================
# 5. 主流程
# ============================================================
def main():
    print("=" * 60)
    print("  CF 优选域名 墙拦截检测 + 测速排序")
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
    print(f"  测速完成：国内绿色可用 {len(results)} / {len(domain_set)} 个")
    print(f"  正在将速度最快的 {len(top_results)} 个正常域名写入 {OUTPUT_FILE}")
    print(f"{'=' * 60}\n")
    
    print(f"{'排名':<6} {'域名':<32} {'平均延迟':>10}")
    print("-" * 55)
    for rank, (domain, ms) in enumerate(top_results, 1):
        print(f"#{rank:<5} {domain:<32} {ms:>8.1f} ms")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for domain, ms in top_results:
            f.write(f"{domain}\n")

    print(f"\n[保存] 成功写入 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
