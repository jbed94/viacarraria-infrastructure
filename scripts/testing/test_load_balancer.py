#!/usr/bin/env python3
"""
Via Carraria — Ingress Load Balancer & Routing Integrity Verification
Verifies traffic routing, upstream proxying, CORS preflights, and balancing
across Frontend and Backend pods via NGINX Ingress.

Usage:
    python3 test_load_balancer.py [--base-url BASE_URL] [--rounds ROUNDS] [--concurrency CONCURRENCY]
    python3 test_load_balancer.py --base-url http://jcore:8080/ --rounds 100
"""

import argparse
import concurrent.futures
import time
import requests


def test_cors_preflight(base_url: str, origin: str) -> bool:
    """Verifies that CORS preflight (OPTIONS) succeeds for custom origin."""
    url = f"{base_url.rstrip('/')}/api/plans/ads/config"
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    try:
        resp = requests.options(url, headers=headers, timeout=5)
        # NGINX Ingress or NestJS should allow the request or return 200/204
        allowed_origin = resp.headers.get("Access-Control-Allow-Origin")
        status = resp.status_code in (200, 204)
        print(f"  • CORS Preflight for Origin '{origin}': HTTP {resp.status_code}")
        if allowed_origin:
            print(f"    - Access-Control-Allow-Origin: {allowed_origin}")
        return status
    except Exception as exc:
        print(f"  • CORS Preflight FAILED: {exc}")
        return False


def test_route(url: str, origin: str | None = None) -> tuple[int, float, int, str]:
    headers = {}
    if origin:
        headers["Origin"] = origin
    t0 = time.perf_counter()
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        server_header = resp.headers.get("Server", "unknown")
        return resp.status_code, elapsed_ms, len(resp.content), server_header
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return 0, elapsed_ms, 0, str(exc)


def run_load_balancer_test(base_url: str, rounds: int, concurrency: int):
    base_url = base_url.rstrip("/")
    print("=" * 70)
    print("      VIA CARRARIA — INGRESS LOAD BALANCER & ROUTING VERIFICATION")
    print("=" * 70)
    print(f"Base Ingress URL:   {base_url}")
    print(f"Rounds per route:   {rounds}")
    print(f"Worker concurrency: {concurrency}")
    print("=" * 70)

    # 1. Routing Verification Check
    routes = [
        ("Frontend SPA Root", f"{base_url}/"),
        ("Backend Ads Config API", f"{base_url}/api/plans/ads/config"),
        ("Backend Public Graphs API", f"{base_url}/api/graphs"),
    ]

    print("\n[Phase 1] Probing Target Ingress Routes...")
    for label, route_url in routes:
        status, lat, size, srv = test_route(route_url)
        status_label = f"HTTP {status}" if status > 0 else "FAIL"
        print(f"  • {label:<28} -> {status_label:<10} ({lat:6.2f} ms, {size:>6} bytes, Server: {srv})")

    # 2. CORS Preflight Check for Multiple Origins
    print("\n[Phase 2] Verifying CORS Across Custom Origins...")
    test_origins = [
        "http://localhost:8080",
        "http://192.168.1.89:8080",
        "http://100.122.139.123:8080",
        "http://jcore:8080",
        "http://jcore.tail7756e6.ts.net:8080",
        "https://jcore.tail7756e6.ts.net",
    ]
    for orig in test_origins:
        test_cors_preflight(base_url, orig)

    # 3. Concurrent Multi-Route Load Distribution
    print(f"\n[Phase 3] Generating Mixed Concurrent Traffic ({rounds * len(routes)} requests)...")
    tasks = []
    for label, route_url in routes:
        for _ in range(rounds):
            tasks.append((label, route_url))

    results_by_route: dict[str, list[tuple[int, float]]] = {r[0]: [] for r in routes}
    t0 = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_label = {
            executor.submit(test_route, url): label for label, url in tasks
        }
        for future in concurrent.futures.as_completed(future_to_label):
            label = future_to_label[future]
            status, lat, _, _ = future.result()
            results_by_route[label].append((status, lat))

    total_time = time.perf_counter() - t0
    total_reqs = len(tasks)

    print("\n" + "=" * 70)
    print("                     ROUTE PERFORMANCE & BALANCING SUMMARY")
    print("=" * 70)
    print(f"Total Requests:         {total_reqs:,}")
    print(f"Total Time:             {total_time:.2f} seconds")
    print(f"Effective Throughput:   {total_reqs / total_time:.1f} req/sec")
    print("-" * 70)

    for label, results in results_by_route.items():
        count = len(results)
        successes = sum(1 for s, _ in results if s == 200)
        lats = sorted([lat for _, lat in results])
        p50 = lats[int(len(lats) * 0.50)] if lats else 0
        p95 = lats[int(len(lats) * 0.95)] if lats else 0
        print(f"Route: {label}")
        print(f"  Success Rate:         {successes}/{count} ({(successes/count)*100:.1f}%)")
        print(f"  Latency (Median p50): {p50:.2f} ms")
        print(f"  Latency (p95):        {p95:.2f} ms")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Via Carraria Ingress Load Balancer & Routing Integrity Verification"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8080",
        help="Base URL of Ingress controller (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=50,
        help="Number of requests per route in the concurrent test (default: 50)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=15,
        help="Number of concurrent worker threads (default: 15)",
    )
    args = parser.parse_args()

    run_load_balancer_test(
        base_url=args.base_url,
        rounds=args.rounds,
        concurrency=args.concurrency,
    )


if __name__ == "__main__":
    main()
