#!/usr/bin/env python3
"""
Via Carraria — High-Throughput HTTP Stress & Latency Benchmark Suite
Measures connection throughput, Keep-Alive pooling performance, and latency percentiles.

Usage:
    python3 benchmark_throughput.py [URL] [-n REQUESTS] [-c CONCURRENCY] [--timeout TIMEOUT]
    python3 benchmark_throughput.py http://jcore:8080/ -n 5000 -c 40
    python3 benchmark_throughput.py http://192.168.1.89:8080/api/plans/ads/config -n 2000 -c 20
"""

import argparse
import concurrent.futures
import json
import math
import sys
import threading
import time
import requests

thread_local = threading.local()


def get_session(pool_size: int = 50) -> requests.Session:
    """Provides a thread-local HTTP session with Keep-Alive connection pooling."""
    if not hasattr(thread_local, "session"):
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=pool_size,
            pool_maxsize=pool_size,
            max_retries=1,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        thread_local.session = session
    return thread_local.session


def fetch(url: str, headers: dict, timeout: float) -> tuple[int, float, int, str]:
    """Executes a single HTTP GET and records status, latency (ms), bytes received, and error if any."""
    session = get_session()
    t0 = time.perf_counter()
    try:
        resp = session.get(url, headers=headers, timeout=timeout)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return resp.status_code, elapsed_ms, len(resp.content), ""
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return 0, elapsed_ms, 0, str(exc)


def calculate_percentile(sorted_list: list[float], p: float) -> float:
    """Calculates linear-interpolated percentile."""
    if not sorted_list:
        return 0.0
    k = (len(sorted_list) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_list[int(k)]
    d0 = sorted_list[int(f)] * (c - k)
    d1 = sorted_list[int(c)] * (k - f)
    return d0 + d1


def run_benchmark(
    url: str,
    total_requests: int,
    concurrency: int,
    headers: dict,
    timeout: float,
    output_json: str | None = None,
):
    print("=" * 70)
    print("           VIA CARRARIA — INGRESS THROUGHPUT BENCHMARK")
    print("=" * 70)
    print(f"Target URL:         {url}")
    print(f"Total Requests:     {total_requests:,}")
    print(f"Concurrency:        {concurrency} worker threads")
    print(f"Request Timeout:    {timeout}s")
    if headers:
        print(f"Custom Headers:     {headers}")
    print("=" * 70)

    start_time = time.perf_counter()
    results: list[tuple[int, float, int, str]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(fetch, url, headers, timeout) for _ in range(total_requests)
        ]
        completed = 0
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
            completed += 1
            if completed % max(1, total_requests // 10) == 0:
                pct = (completed / total_requests) * 100
                sys.stdout.write(f"\rProgress: {completed:,}/{total_requests:,} ({pct:.0f}%)")
                sys.stdout.flush()

    total_duration = time.perf_counter() - start_time
    print("\n")

    latencies = sorted([r[1] for r in results])
    status_counts: dict[int, int] = {}
    total_bytes = 0
    errors: dict[str, int] = {}

    for status, lat, byte_count, err_msg in results:
        status_counts[status] = status_counts.get(status, 0) + 1
        total_bytes += byte_count
        if err_msg:
            errors[err_msg] = errors.get(err_msg, 0) + 1

    req_per_sec = total_requests / total_duration if total_duration > 0 else 0
    mb_per_sec = (total_bytes / (1024 * 1024)) / total_duration if total_duration > 0 else 0
    success_count = status_counts.get(200, 0)
    success_rate = (success_count / total_requests) * 100 if total_requests > 0 else 0

    p50 = calculate_percentile(latencies, 0.50)
    p90 = calculate_percentile(latencies, 0.90)
    p95 = calculate_percentile(latencies, 0.95)
    p99 = calculate_percentile(latencies, 0.99)
    min_lat = latencies[0] if latencies else 0
    max_lat = latencies[-1] if latencies else 0

    print("=" * 70)
    print("                        BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"Total Execution Time:   {total_duration:.2f} seconds")
    print(f"Throughput Rate:        {req_per_sec:,.1f} requests/sec")
    print(f"Data Transfer Rate:     {mb_per_sec:.2f} MB/sec ({total_bytes / (1024*1024):.2f} MB total)")
    print(f"Successful (HTTP 200):  {success_count:,} / {total_requests:,} ({success_rate:.2f}%)")
    
    if any(k != 200 for k in status_counts):
        print("\nStatus Code Breakdown:")
        for code, count in sorted(status_counts.items()):
            label = "HTTP " + str(code) if code > 0 else "Connection Failed"
            print(f"  {label:<20} {count:>6,} ({(count/total_requests)*100:.1f}%)")

    if errors:
        print("\nConnection Errors:")
        for err, count in list(errors.items())[:5]:
            print(f"  - {err} ({count} occurrences)")

    print("\nLatency Distribution:")
    print(f"  • Min:                {min_lat:7.2f} ms")
    print(f"  • Median (p50):       {p50:7.2f} ms")
    print(f"  • 90th Percentile:    {p90:7.2f} ms")
    print(f"  • 95th Percentile:    {p95:7.2f} ms")
    print(f"  • 99th Percentile:    {p99:7.2f} ms")
    print(f"  • Max:                {max_lat:7.2f} ms")
    print("=" * 70)

    if output_json:
        report = {
            "targetUrl": url,
            "totalRequests": total_requests,
            "concurrency": concurrency,
            "durationSeconds": round(total_duration, 3),
            "requestsPerSec": round(req_per_sec, 2),
            "mbPerSec": round(mb_per_sec, 2),
            "successRate": round(success_rate, 2),
            "statusCodes": status_counts,
            "latencyMs": {
                "min": round(min_lat, 2),
                "p50": round(p50, 2),
                "p90": round(p90, 2),
                "p95": round(p95, 2),
                "p99": round(p99, 2),
                "max": round(max_lat, 2),
            },
        }
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\n[INFO] Detailed benchmark report written to: {output_json}")


def main():
    parser = argparse.ArgumentParser(
        description="Via Carraria High-Throughput Ingress Stress & Latency Benchmark"
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="http://localhost:8080/",
        help="Target URL (default: http://localhost:8080/)",
    )
    parser.add_argument(
        "-n",
        "--requests",
        type=int,
        default=3000,
        help="Total number of HTTP requests to send (default: 3000)",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=30,
        help="Number of concurrent worker threads (default: 30)",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=10.0,
        help="Request timeout in seconds (default: 10.0)",
    )
    parser.add_argument(
        "-H",
        "--header",
        action="append",
        help="Custom HTTP header in 'Key: Value' format (can be specified multiple times)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default=None,
        help="Optional path to output results in JSON format",
    )

    args = parser.parse_args()

    headers = {}
    if args.header:
        for h in args.header:
            if ":" in h:
                k, v = h.split(":", 1)
                headers[k.strip()] = v.strip()

    run_benchmark(
        url=args.url,
        total_requests=args.requests,
        concurrency=args.concurrency,
        headers=headers,
        timeout=args.timeout,
        output_json=args.json_out,
    )


if __name__ == "__main__":
    main()
