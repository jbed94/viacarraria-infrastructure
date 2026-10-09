# Via Carraria — Performance Benchmarking, Routing & Autoscaling Test Suite

This document describes the automated stress testing, Ingress load balancing, and KEDA queue autoscaling verification suite located in [`viacarraria-infrastructure/scripts/testing/`](file:///home/jbed94/Projects/viacarraria/viacarraria-infrastructure/scripts/testing/).

---

## 1. Test Suite Overview

| Script | Purpose & Mechanics | Typical Parameters |
|---|---|---|
| [`benchmark_throughput.py`](file:///home/jbed94/Projects/viacarraria/viacarraria-infrastructure/scripts/testing/benchmark_throughput.py) | High-throughput HTTP stress tester using thread-local Keep-Alive connection pooling (`requests.Session` + `HTTPAdapter`). Captures requests/second, bandwidth (MB/s), error rates, and full latency percentiles (min, p50, p90, p95, p99, max). | `-n 3000 -c 30` |
| [`test_load_balancer.py`](file:///home/jbed94/Projects/viacarraria/viacarraria-infrastructure/scripts/testing/test_load_balancer.py) | Validates Ingress reverse proxying across SPA root, Ads Config API, and Graphs API. Sends concurrent requests to verify balanced pod distribution and checks CORS preflight (`OPTIONS`) handling across multiple allowed origins. | `--rounds 50 -c 15` |
| [`test_keda_scaling.py`](file:///home/jbed94/Projects/viacarraria/viacarraria-infrastructure/scripts/testing/test_keda_scaling.py) | Validates KEDA queue-driven scale-to-zero. Injects synthetic jobs into RabbitMQ `document_parsing_queue`, tracks rapid scale-up (0 -> 2+ pods) for `parsingWorker` and `embeddingEngine`, purges queue, and monitors cooldown back to 0 replicas. | `-m 5 -c 20` |
| [`run_load_test.sh`](file:///home/jbed94/Projects/viacarraria/viacarraria-infrastructure/scripts/testing/run_load_test.sh) | Unified CLI runner orchestrating all three test suites with simple command-line flags. | `--all` |

---

## 2. Usage & Command Reference

### Master CLI Orchestrator (`run_load_test.sh`)

```bash
cd viacarraria-infrastructure/scripts/testing

# Display help and available options
./run_load_test.sh --help

# Run Ingress throughput benchmark (default: 3000 requests, 30 concurrency)
./run_load_test.sh --benchmark http://localhost:8080/ 3000 30

# Run Ingress routing & CORS preflight verification (50 rounds per route)
./run_load_test.sh --load-balancer http://localhost:8080 50

# Run KEDA scale-to-zero test (5 messages, 20s cooldown)
./run_load_test.sh --keda 5 20

# Run all test suites sequentially
./run_load_test.sh --all
```

---

### Throughput & Latency Benchmark (`benchmark_throughput.py`)

```bash
# Benchmark against local Ingress port forward
python3 benchmark_throughput.py http://localhost:8080/ -n 5000 -c 40

# Benchmark over Tailscale interface
python3 benchmark_throughput.py http://100.122.139.123:8080/ -n 3000 -c 30

# Benchmark API endpoint with JSON summary output
python3 benchmark_throughput.py http://jcore:8080/api/plans/ads/config \
  -n 2000 -c 20 --json-out /tmp/benchmark-report.json
```

#### Output Metrics Captured:
- **Total Execution Time**: Elapsed wall-clock time in seconds.
- **Throughput Rate**: Average completed requests/second.
- **Data Transfer Rate**: MB/second transferred over HTTP Keep-Alive connections.
- **Status Code Breakdown**: Counts of HTTP 200, 4xx, 5xx, or socket connection drops.
- **Latency Distribution**: Min, p50 (Median), p90, p95, p99, and Max latency in milliseconds.

---

### Ingress Load Balancer & Routing Integrity (`test_load_balancer.py`)

```bash
python3 test_load_balancer.py --base-url http://localhost:8080 --rounds 50 --concurrency 15
```

#### Test Phases:
1. **Route Probing**: Checks HTTP status, latency, response byte length, and `Server` headers for:
   - Frontend SPA: `/`
   - Ads Configuration API: `/api/plans/ads/config`
   - Public Graphs API: `/api/graphs`
2. **CORS Preflight Testing**: Sends `OPTIONS` requests with multiple `Origin` headers (`http://localhost:8080`, `http://192.168.1.89:8080`, `http://100.122.139.123:8080`, `http://jcore:8080`, `https://jcore.tail7756e6.ts.net`), verifying `Access-Control-Allow-Origin` headers.
3. **Concurrent Multi-Route Balancing**: Blends concurrent traffic across all routes and outputs per-route latency percentiles.

---

### KEDA Queue-Driven Scale-to-Zero Verification (`test_keda_scaling.py`)

```bash
python3 test_keda_scaling.py --namespace viacarraria --messages 5 --cooldown 20
```

#### Verification Lifecycle:
1. **Phase 1: Initial Idle State**: Confirms `parsing-worker` and `embedding-engine` are scaled down to 0 replicas.
2. **Phase 2: Burst Scale-Up**: Injects synthetic jobs into RabbitMQ `document_parsing_queue`; validates that KEDA detects queue depth >= 1 and triggers rapid scale-out to >= 1 pods in < 5 seconds.
3. **Phase 3: Queue Drain & Cooldown**: Purges the queue and monitors the 20-second cooldown period, validating that both deployments safely terminate worker pods and return to 0 replicas.
