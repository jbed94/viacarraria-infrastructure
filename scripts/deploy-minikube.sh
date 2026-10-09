#!/usr/bin/env bash
set -euo pipefail

################################################################################
# Via Carraria — Minikube Single-Command Deployment Automation Script
#
# This script provisions and initializes the complete Via Carraria platform on a
# local Minikube cluster with GCP-parity capabilities:
# 1. Validates prerequisites (minikube, kubectl, helm, docker).
# 2. Ensures Minikube cluster is active with GCP-parity addons:
#    - ingress (NGINX)
#    - metrics-server (HPA)
#    - default-storageclass
#    - KEDA (scale-to-zero queue workers)
# 3. Builds and loads local container images if missing.
# 4. Deploys the complete Helm release (in-cluster PostgreSQL, Redis, RabbitMQ,
#    Weaviate, MinIO, Backend, Frontend, and automated DB migrations & seed).
# 5. Bridges Ingress on 0.0.0.0:8080 for universal LAN & Tailscale network access.
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HELM_CHART_DIR="${REPO_ROOT}/viacarraria-infrastructure/platforms/helm/graph-app"
VALUES_FILE="${HELM_CHART_DIR}/values-minikube.yaml"
NAMESPACE="viacarraria"
PORT_FORWARD_PORT=8080

echo "================================================================================"
echo "           Via Carraria — Minikube Local Cloud Deployment                      "
echo "================================================================================"

# 1. Verify Prerequisites
for cmd in minikube kubectl helm docker; do
  if ! command -v "$cmd" &> /dev/null; then
    echo "ERROR: Required command '$cmd' is not in PATH."
    echo "Please ensure platform tools are installed in PATH or ~/.local/bin."
    exit 1
  fi
done

# 2. Check Minikube Status
echo "==> Checking Minikube status..."
if ! minikube status &> /dev/null; then
  echo "Minikube is not running. Starting Minikube cluster with 12 vCPUs, 32GB RAM..."
  minikube start \
    --driver=docker \
    --cpus=12 \
    --memory=32768 \
    --disk-size=60g \
    --addons=ingress,metrics-server,default-storageclass,dashboard
else
  echo "Minikube is running."
fi

# Ensure required addons are active
echo "==> Ensuring required addons are enabled..."
minikube addons enable ingress >/dev/null 2>&1 || true
minikube addons enable metrics-server >/dev/null 2>&1 || true
minikube addons enable default-storageclass >/dev/null 2>&1 || true

# 3. Ensure KEDA Operator is Installed
echo "==> Checking KEDA autoscaling operator..."
if ! kubectl get namespace keda &> /dev/null; then
  echo "Installing KEDA via Helm..."
  helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1 || true
  helm repo update kedacore >/dev/null 2>&1 || true
  helm upgrade --install keda kedacore/keda --namespace keda --create-namespace
else
  echo "KEDA operator namespace exists."
fi

# 4. Check & Load Container Images
echo "==> Verifying local container images in Minikube..."
REQUIRED_IMAGES=(
  "viacarraria/frontend:latest"
  "viacarraria/backend:latest"
  "viacarraria/database-migrate:latest"
  "viacarraria/parsing-worker:latest"
  "viacarraria/embedding-engine:latest"
)

for img in "${REQUIRED_IMAGES[@]}"; do
  if ! minikube image ls --format table | grep -q "${img%:*}"; then
    echo "Image '$img' not found inside Minikube. Loading from local Docker..."
    if ! docker image inspect "$img" &> /dev/null; then
      echo "Image '$img' not found in Docker. Please run build for the corresponding submodule."
    else
      minikube image load "$img"
    fi
  else
    echo "Image '$img' already present in Minikube."
  fi
done

# 5. Apply Helm Release
echo "==> Deploying Via Carraria stack via Helm (Namespace: ${NAMESPACE})..."
helm upgrade --install viacarraria "${HELM_CHART_DIR}" \
  -f "${VALUES_FILE}" \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  --wait \
  --timeout 10m

# 6. Check Ingress Port Forward Daemon
echo "==> Checking external Ingress port forward on port ${PORT_FORWARD_PORT}..."
if ! ss -tulpn | grep -q ":${PORT_FORWARD_PORT} "; then
  echo "Starting background port forward from 0.0.0.0:${PORT_FORWARD_PORT} to ingress-nginx..."
  nohup kubectl port-forward --address 0.0.0.0 service/ingress-nginx-controller -n ingress-nginx "${PORT_FORWARD_PORT}:80" > /tmp/viacarraria-port-forward.log 2>&1 &
  sleep 2
else
  echo "Port forward on port ${PORT_FORWARD_PORT} is already active."
fi

# 7. Print Access Information
HOST_LAN_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7}' | head -n1 || echo "127.0.0.1")
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "Not configured")
HOSTNAME=$(hostname)

echo ""
echo "================================================================================"
echo "                  Via Carraria is successfully deployed!                        "
echo "================================================================================"
echo "Access the application from any device using:"
echo "  • Localhost:       http://localhost:${PORT_FORWARD_PORT}/"
echo "  • Local LAN:       http://${HOST_LAN_IP}:${PORT_FORWARD_PORT}/"
if [ "$TAILSCALE_IP" != "Not configured" ]; then
echo "  • Tailscale IP:    http://${TAILSCALE_IP}:${PORT_FORWARD_PORT}/"
echo "  • Tailscale Host:  http://${HOSTNAME}:${PORT_FORWARD_PORT}/"
echo "  • Tailscale FQDN:  http://${HOSTNAME}.tail7756e6.ts.net:${PORT_FORWARD_PORT}/"
fi
echo ""
echo "To enable standard HTTPS (port 443) on Tailscale with Let's Encrypt:"
echo "  sudo tailscale serve --bg ${PORT_FORWARD_PORT}"
echo "================================================================================"
