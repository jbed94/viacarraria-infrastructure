# Via Carraria — Minikube Local Cloud Deployment with Tailscale & SSL Guide

This guide provides a comprehensive, end-to-end walkthrough for deploying Via Carraria on a local Ubuntu/Debian machine using **Minikube**, **kubectl**, **Helm**, **Tailscale**, and **SSL/TLS**.

---

## 1. Machine Preparation & Tooling Installation

All platform tools are installed in user space (`~/.local/bin`), requiring no passwordless root/sudo for day-to-day operations.

### 1.1 Install `kubectl`
```bash
mkdir -p ~/.local/bin
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
mv kubectl ~/.local/bin/
```

### 1.2 Install `minikube`
```bash
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
chmod +x minikube-linux-amd64
mv minikube-linux-amd64 ~/.local/bin/minikube
```

### 1.3 Install `helm`
```bash
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
chmod 700 get_helm.sh
USE_SUDO=false HELM_INSTALL_DIR=$HOME/.local/bin ./get_helm.sh
rm get_helm.sh
```

### 1.4 Ensure PATH Configuration
Add `~/.local/bin` to your environment (in `~/.bashrc` or `~/.profile`):
```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
```

---

## 2. Minikube Cluster Provisioning (GCP-Parity Configuration)

Provision the cluster with resource limits suitable for emulating GCP cloud features (HPA, Ingress, KEDA scale-to-zero):

```bash
minikube start \
  --driver=docker \
  --cpus=12 \
  --memory=32768 \
  --disk-size=60g \
  --addons=ingress,metrics-server,default-storageclass,dashboard
```

Verify that the core addons are enabled:
```bash
minikube addons enable ingress
minikube addons enable metrics-server
minikube addons enable default-storageclass
```

### 2.1 Install KEDA Autoscaling Operator
```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update kedacore
helm upgrade --install keda kedacore/keda --namespace keda --create-namespace
```

---

## 3. Container Images & Single-Command Deployment

### 3.1 Build & Load Local Images
Build the submodules using Docker and load them into the Minikube Docker cache:
```bash
# Frontend
docker build -t viacarraria/frontend:latest -f viacarraria-frontend/platforms/docker/Dockerfile viacarraria-frontend
minikube image load viacarraria/frontend:latest

# Backend API
docker build -t viacarraria/backend:latest -f viacarraria-backend/platforms/docker/Dockerfile viacarraria-backend
minikube image load viacarraria/backend:latest

# Database Migrations & Seeding
docker build -t viacarraria/database-migrate:latest -f viacarraria-database/platforms/docker/Dockerfile viacarraria-database
minikube image load viacarraria/database-migrate:latest

# Python FastStream Ingestion Worker
docker build -t viacarraria/parsing-worker:latest -f viacarraria-services/platforms/docker/Dockerfile viacarraria-services
minikube image load viacarraria/parsing-worker:latest

# TEI Vector Embedding Engine
minikube image load ghcr.io/huggingface/text-embeddings-inference:cpu-1.8
docker tag ghcr.io/huggingface/text-embeddings-inference:cpu-1.8 viacarraria/embedding-engine:latest
minikube image load viacarraria/embedding-engine:latest
```

### 3.2 Deploy via Helm
Run the automated deployment script or execute Helm directly:

```bash
# Option A: Automated turnkey script
./viacarraria-infrastructure/scripts/deploy-minikube.sh

# Option B: Direct Helm upgrade/install
helm upgrade --install viacarraria ./viacarraria-infrastructure/platforms/helm/graph-app \
  -f ./viacarraria-infrastructure/platforms/helm/graph-app/values-minikube.yaml \
  --namespace viacarraria \
  --create-namespace
```

The pre-upgrade migration job will automatically wait for PostgreSQL, synchronize Prisma schemas (`pnpm db:push`), and seed the demo graphs (`pnpm seed`).

---

## 4. Port Forwarding & SSL/TLS Architecture

### 4.1 Understanding Port Forwarding: `8080:80` vs `8080:443`

A common source of confusion is which ports to forward:

```
[Remote User Browser] 
        │
        ▼ (HTTPS port 443 with Let's Encrypt TLS)
[Tailscale Serve daemon on Host machine]
        │
        ▼ (proxies unencrypted plain HTTP to localhost:8080)
[kubectl port-forward daemon (0.0.0.0:8080 -> ingress-nginx:80)]
        │
        ▼ (port 80)
[NGINX Ingress Controller inside Minikube]
        │
        ├─► /api/*  ──► viacarraria-backend:3000
        └─► /*      ──► viacarraria-frontend:80
```

1. **`kubectl port-forward ... 8080:80`**:
   - Forwards local host port `8080` to the NGINX Ingress controller's HTTP port `80`.
   - You **do not** forward `8080:443` when using Tailscale Serve, because Tailscale Serve connects to an **unencrypted HTTP target** (`http://127.0.0.1:8080`) and performs SSL termination on port `443` externally.
   - If you were to forward `8080:443`, port 8080 would expect TLS handshakes, breaking plain HTTP access and confusing Tailscale Serve.

2. **Starting the Ingress Port Forward Daemon**:
   ```bash
   nohup kubectl port-forward --address 0.0.0.0 service/ingress-nginx-controller -n ingress-nginx 8080:80 > /tmp/viacarraria-ingress-forward.log 2>&1 &
   ```

---

### 4.2 Configuring Tailscale & Automatic HTTPS (Port 443)

#### Step 1: Ensure Tailscale is Connected
Verify your machine’s Tailscale IP and hostname:
```bash
tailscale status
# Example: 100.122.139.123  jcore  jakub@  linux
```

#### Step 2: Enable Tailscale Serve (Automated Let's Encrypt SSL on Port 443)
Configure Tailscale to terminate TLS on standard port `443` and forward traffic to your Ingress port `8080`:

```bash
# Allow your user account to run tailscale serve without sudo prompts
sudo tailscale set --operator=$USER

# Start background HTTPS proxy
sudo tailscale serve --bg 8080
```

#### Step 3: Accessing the Application
Once `tailscale serve` is active, anyone on your Tailnet can access:
- **HTTPS URL**: `https://<hostname>.<tailnet-name>.ts.net/` (e.g. `https://jcore.tail7756e6.ts.net/`)
- **Direct HTTP (LAN or Tailnet)**: `http://100.122.139.123:8080/` or `http://192.168.1.89:8080/`

---

### 4.3 In-Cluster Minikube TLS (Port 8443 Alternative)

If you wish to terminate TLS directly inside Minikube without Tailscale:

1. Enable cert-manager in `values-minikube.yaml`:
   ```yaml
   ingress:
     tls:
       enabled: true
     certManager:
       enabled: true
   ```
2. Forward the Ingress controller's HTTPS port to a high non-privileged host port (e.g., 8443):
   ```bash
   kubectl port-forward --address 0.0.0.0 service/ingress-nginx-controller -n ingress-nginx 8443:443
   ```
3. Access via `https://localhost:8443/` or `https://jcore:8443/`.
