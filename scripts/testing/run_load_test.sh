#!/usr/bin/env bash
set -euo pipefail

################################################################################
# Via Carraria — Performance & Autoscaling Test Suite Orchestrator
#
# Convenient wrapper script to execute throughput benchmarks, Ingress routing
# tests, and KEDA scale-to-zero autoscaling verifications.
#
# Examples:
#   ./run_load_test.sh --benchmark http://localhost:8080/ 3000 30
#   ./run_load_test.sh --load-balancer http://localhost:8080 50
#   ./run_load_test.sh --keda 5
#   ./run_load_test.sh --all
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$(which python3)"

print_usage() {
  cat << EOF
Usage: $0 [MODE] [OPTIONS]

Modes:
  --benchmark [URL] [REQUESTS] [CONCURRENCY]
      Runs high-throughput HTTP stress test and measures latency percentiles.
      Defaults: URL=http://localhost:8080/, REQUESTS=3000, CONCURRENCY=30

  --load-balancer [URL] [ROUNDS]
      Verifies multi-route Ingress proxying, CORS preflights, and balancing.
      Defaults: URL=http://localhost:8080, ROUNDS=50

  --keda [MESSAGES] [COOLDOWN]
      Validates KEDA queue-driven scale-out and scale-to-zero cooldown.
      Defaults: MESSAGES=5, COOLDOWN=20

  --all
      Runs all three verification suites sequentially.

  --help
      Displays this help text.

EOF
}

if [ $# -eq 0 ]; then
  print_usage
  exit 1
fi

MODE="$1"
shift || true

case "$MODE" in
  --benchmark|-b)
    URL="${1:-http://localhost:8080/}"
    REQUESTS="${2:-3000}"
    CONCURRENCY="${3:-30}"
    echo "==> Executing Throughput Benchmark..."
    "$PYTHON_BIN" "${SCRIPT_DIR}/benchmark_throughput.py" "$URL" -n "$REQUESTS" -c "$CONCURRENCY"
    ;;

  --load-balancer|-l)
    URL="${1:-http://localhost:8080}"
    ROUNDS="${2:-50}"
    echo "==> Executing Ingress Load Balancer Verification..."
    "$PYTHON_BIN" "${SCRIPT_DIR}/test_load_balancer.py" --base-url "$URL" --rounds "$ROUNDS"
    ;;

  --keda|-k)
    MESSAGES="${1:-5}"
    COOLDOWN="${2:-20}"
    echo "==> Executing KEDA Scale-to-Zero Verification..."
    "$PYTHON_BIN" "${SCRIPT_DIR}/test_keda_scaling.py" -m "$MESSAGES" -c "$COOLDOWN"
    ;;

  --all|-a)
    echo "==> [1/3] Executing Ingress Load Balancer Verification..."
    "$PYTHON_BIN" "${SCRIPT_DIR}/test_load_balancer.py" --base-url "http://localhost:8080" --rounds 30

    echo ""
    echo "==> [2/3] Executing Throughput Benchmark..."
    "$PYTHON_BIN" "${SCRIPT_DIR}/benchmark_throughput.py" "http://localhost:8080/" -n 3000 -c 30

    echo ""
    echo "==> [3/3] Executing KEDA Scale-to-Zero Verification..."
    "$PYTHON_BIN" "${SCRIPT_DIR}/test_keda_scaling.py" -m 5 -c 20
    ;;

  --help|-h)
    print_usage
    exit 0
    ;;

  *)
    echo "Unknown option: $MODE"
    print_usage
    exit 1
    ;;
esac
