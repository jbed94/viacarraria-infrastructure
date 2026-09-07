# Via Carraria — Kubernetes Helm Deployment Package (`graph-app`)

This directory contains the production-ready Helm chart (`graph-app`) for the complete **Via Carraria** knowledge canvas monorepo. It orchestrates all application tiers, neural workers, background infrastructure, autoscaling policies, ingress routing, and automated TLS lifecycle management.

---

## 1. Architectural Topology & Component Overview

```
                                      [ Internet ]
                                           │
                                           ▼
                               [ Cloud Load Balancer ]
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    │      NGINX Ingress Controller               │
                    │   (cert-manager Let's Encrypt TLS)          │
                    └──────────────┬──────────────────┬───────────┘
                                   │                  │
                Path: /            │                  │ Path: /api & /socket.io
                (HTTP 80)          ▼                  ▼ (HTTP 3000)
                    ┌──────────────────────┐   ┌──────────────────────┐
                    │  Frontend (Web SPA)  │   │  Backend (NestJS API)│
                    │  (Nginx Static Host) │   │  HPA Autoscaled (2-16)
                    │  HPA Autoscaled (2-12)   │  PodAntiAffinity HA  │
                    └──────────────────────┘   └──────────┬───────────┘
                                                          │
                      ┌───────────────────────────────────┼──────────────────────────────┐
                      ▼                                   ▼                              ▼
             ┌─────────────────┐                 ┌─────────────────┐            ┌─────────────────┐
             │  PostgreSQL 16  │                 │     Redis 7     │            │   RabbitMQ 3.13 │
             │  Relational DB  │                 │ Cache & Limits  │            │ Queue & AMQP DLQ│
             └─────────────────┘                 └─────────────────┘            └────────┬────────┘
                      ▲                                                                  │
                      │                                                                  ▼
                      │                                                        ┌──────────────────┐
                      │                                                        │ KEDA Autoscaler  │
                      │                                                        │ (QueueLength >=1)│
                      │                                                        └────────┬─────────┘
                      │                                                                 │
                      │                                     ┌───────────────────────────┴──────────┐
                      │                                     ▼                                      ▼
             ┌─────────────────┐                  ┌───────────────────┐                  ┌───────────────────┐
             │ Weaviate Vector │◄─────────────────┤  Parsing Worker   │─────────────────►│ Embedding Engine  │
             │ DB (PQ Enabled) │                  │  (FastStream)     │                  │  (HF TEI / Gemma) │
             └─────────────────┘                  │  Scale-to-Zero    │                  │  Scale-to-Zero    │
                                                  └───────────────────┘                  └───────────────────┘
```

### Chart Component Matrix

| Component | Architecture Type | Scaling Mechanism | Scale-to-Zero? | Storage / Volume |
| :--- | :--- | :--- | :--- | :--- |
| **`frontend`** | Stateless SPA / Nginx | HorizontalPodAutoscaler (HPA) | ❌ No (min 2 pods) | Ephemeral |
| **`admin`** | Standalone Admin SPA | Fixed / Zero-Trust VPN | ❌ No (1 pod) | Ephemeral |
| **`tailscale-operator`** | Zero-Trust VPN Operator | Sub-Chart (`pkgs.tailscale.com`) | ❌ No (1 pod) | Secret (`tailscale-oauth`) |
| **`backend`** | Stateless API Gateway | HorizontalPodAutoscaler (HPA) | ❌ No (min 2 pods) | Shared Uploads PVC / S3 |
| **`parsingWorker`** | Async Consumer | KEDA (`ScaledObject` on RabbitMQ) | ✅ **YES** (0 replicas idle) | Shared Uploads PVC / S3 |
| **`embeddingEngine`** | Neural Inference (TEI) | KEDA (`ScaledObject` on RabbitMQ) | ✅ **YES** (0 replicas idle) | Ephemeral / GKE Spot |
| **`rerankingEngine`** | Neural Reranker (TEI) | HorizontalPodAutoscaler (HPA) | ❌ No (min 1 replica) | Ephemeral |
| **`databaseMigrate`**| Helm Hook Job | One-shot (`post-install`, `pre-upgrade`) | Completed on exit | None |
| **`postgresql`** | Stateful Database | StatefulSet (or Cloud SQL) | ❌ No | PersistentVolumeClaim (RWO) |
| **`redis`** | In-Memory Cache | Deployment (or Memorystore) | ❌ No | Ephemeral / PVC |
| **`rabbitmq`** | Message Broker | StatefulSet with DLX/DLQ | ❌ No | PersistentVolumeClaim (RWO) |
| **`weaviate`** | Vector Database | StatefulSet with PQ compression | ❌ No | PersistentVolumeClaim (RWO) |
| **`minio`** | S3-Compatible Storage | Deployment + Provisioner Job | ❌ No | PersistentVolumeClaim (RWO) |
| **`admin`** | Decoupled Admin Portal | Deployment (Tailscale/VPN) | ❌ No (min 1 replica) | Ephemeral |

---

## 2. External Setup Guide (Real-World Production Readiness)

Before running a production deployment on Google Cloud Platform (GCP), several external domain, security, and messaging services must be set up manually.

### 2.1. Domain Acquisition & DNS Configuration (e.g. OVH, Cloudflare, Namecheap)

1. **Purchase Domain**:
   - Register your domain (e.g., `viacarraria.com`) on your registrar of choice (e.g. [OVHcloud](https://www.ovhcloud.com/), [Cloudflare Registrar](https://www.cloudflare.com/products/registrar/), or Namecheap).
2. **Retrieve Ingress External IP**:
   - Once the NGINX Ingress Controller is provisioned on GKE, retrieve its public external IP:
     ```bash
     kubectl get service -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
     ```
3. **Configure DNS Records**:
   - In your registrar or DNS management portal (e.g., OVH DNS Zone), create the following records:
     - **Apex / Root Domain (`@`)**:
       - Type: `A`
       - Target / IP: `<YOUR_INGRESS_EXTERNAL_IP>`
       - TTL: `300` (5 minutes during deployment for rapid propagation)
     - **API Subdomain (`api`)** *(if using subdomain routing)*:
       - Type: `A` (or `CNAME` pointing to `@`)
       - Target / IP: `<YOUR_INGRESS_EXTERNAL_IP>`
     - **Admin Portal (`admin`)** *(Tailscale / Internal VPN routing)*:
       - Type: `CNAME` pointing to `@` (or Tailscale MagicDNS / internal ingress)
4. **Verify Propagation**:
   ```bash
   dig +short viacarraria.com
   nslookup viacarraria.com
   ```

---

### 2.2. Automated SSL/TLS Certificate Lifecycle (cert-manager & Let's Encrypt)

The Helm chart includes automated certificate issuance and renewal via **cert-manager** and the ACME protocol (Let's Encrypt).

1. **Install cert-manager on GKE**:
   ```bash
   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
   ```
2. **Verify cert-manager Webhook & Controller**:
   ```bash
   kubectl get pods -n cert-manager
   ```
3. **How the Automatic Lifecycle Works**:
   - When the chart is deployed with `ingress.certManager.enabled: true` and `ingress.certManager.createClusterIssuer: true`:
     1. A `ClusterIssuer` named `letsencrypt-prod` is automatically created pointing to `https://acme-v02.api.letsencrypt.org/directory`.
     2. The `Ingress` resource is annotated with `cert-manager.io/cluster-issuer: letsencrypt-prod`.
     3. When the Ingress is created, cert-manager intercepts the TLS host specification (`viacarraria.com`), contacts Let's Encrypt, and initiates an **HTTP-01 challenge**.
     4. cert-manager automatically creates a temporary solver pod and configures the Ingress to serve the challenge token under `http://viacarraria.com/.well-known/acme-challenge/<TOKEN>`.
     5. Let's Encrypt validates domain ownership and signs an X.509 TLS certificate.
     6. The signed certificate and private key are stored in the Kubernetes Secret `viacarraria-production-tls`.
     7. **Automatic Zero-Downtime Renewal**: cert-manager continuously inspects the certificate's validity and automatically initiates renewal **30 days before expiration**. The Secret is updated in place and NGINX reloads SSL context without dropping connections.
4. **Inspecting Certificate Status**:
   ```bash
   kubectl get certificate,certificaterequest,order,challenge -n viacarraria
   kubectl describe certificate viacarraria-production-tls -n viacarraria
   ```

---

### 2.3. Transactional Email Service Setup (User Lifecycle & Magic Links)

For production transactional emails (welcome emails, password resets, magic sign-in links):

1. **Create Provider Account**:
   - Register an account with [Resend](https://resend.com/), [SendGrid](https://sendgrid.com/), [Postmark](https://postmarkapp.com/), or [AWS SES](https://aws.amazon.com/ses/).
2. **Domain Authentication (SPF, DKIM, DMARC)**:
   - To ensure emails do not land in spam folders, configure the following DNS records on your domain registrar:
     - **SPF Record**:
       ```
       Type: TXT
       Name: @
       Value: "v=spf1 include:sendgrid.net ~all"
       ```
     - **DKIM Records**:
       - Add the two `CNAME` records provided by your email service (e.g. `s1._domainkey.viacarraria.com` and `s2._domainkey.viacarraria.com`).
     - **DMARC Record**:
       ```
       Type: TXT
       Name: _dmarc.viacarraria.com
       Value: "v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarc-reports@viacarraria.com"
       ```
3. **Generate API Keys**:
   - Generate an API key or SMTP credentials with restricted "Mail Send" permissions.
   - Inject the credentials into the runtime secret or Kubernetes environment.

---

### 2.4. Google Cloud Platform (GCP / GKE) Infrastructure Setup

1. **Create VPC-Native GKE Cluster**:
   ```bash
   gcloud container clusters create viacarraria-prod-cluster \
     --project=YOUR_PROJECT_ID \
     --region=us-central1 \
     --enable-ip-alias \
     --workload-pool=YOUR_PROJECT_ID.svc.id.goog \
     --num-nodes=1 \
     --machine-type=e2-standard-4 \
     --enable-autoscaling --min-nodes=1 --max-nodes=5
   ```
2. **Provision a Spot VM Node Pool for KEDA Scale-to-Zero Workers**:
   ```bash
   gcloud container node-pools create spot-worker-pool \
     --cluster=viacarraria-prod-cluster \
     --region=us-central1 \
     --spot \
     --machine-type=c2d-standard-4 \
     --enable-autoscaling --min-nodes=0 --max-nodes=8 \
     --node-labels=cloud.google.com/gke-spot=true \
     --node-taints=cloud.google.com/gke-spot=true:NoSchedule
   ```
   *Note: Spot VMs yield up to 60-91% cost savings for the bursty Docling parsing worker and neural embedding engine pods.*

3. **Google Cloud Storage (GCS) S3-Interoperability Bucket**:
   - Create a bucket for source document storage:
     ```bash
     gsutil mb -p YOUR_PROJECT_ID -c standard -l us-central1 gs://viacarraria-production-sources
     ```
   - Generate S3 HMAC keys for interoperability:
     ```bash
     gcloud storage hmac create viacarraria-storage-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
     ```
   - Set in `values-production.yaml`:
     ```yaml
     storage:
       driver: s3
       s3:
         endpoint: "https://storage.googleapis.com"
         bucket: "viacarraria-production-sources"
         accessKey: "GOOG..."
         secretKey: "..."
         forcePathStyle: "false"
     ```

4. **Install Ingress-NGINX and KEDA Operators**:
   ```bash
   # Install NGINX Ingress Controller
   helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
   helm repo update
   helm install ingress-nginx ingress-nginx/ingress-nginx \
     --namespace ingress-nginx --create-namespace \
     --set controller.service.externalTrafficPolicy=Local

   # Install KEDA (Kubernetes Event-driven Autoscaling)
   helm repo add kedacore https://kedacore.github.io/charts
   helm repo update
   helm install keda kedacore/keda \
     --namespace keda --create-namespace
   ```

---

## 3. Local Minikube Deployment Guide (Offline & Self-Contained)

The local Minikube profile (`values-minikube.yaml`) runs completely self-contained on your development laptop without connecting to external cloud services.

### 3.1. Start Minikube

```bash
minikube start \
  --cpus=4 \
  --memory=8192 \
  --disk-size=30g \
  --addons=ingress,metrics-server
```

### 3.2. Map Local Domain

Add `viacarraria.local` to `/etc/hosts` pointing to your Minikube IP:

```bash
MINIKUBE_IP=$(minikube ip)
echo "$MINIKUBE_IP viacarraria.local" | sudo tee -a /etc/hosts
```

### 3.3. Build Local Container Images in Minikube Docker Daemon

Point your shell to Minikube's internal Docker daemon and build images:

```bash
eval $(minikube docker-env)

# Build Frontend
docker build -t viacarraria/frontend:latest ./viacarraria-frontend/platforms/docker/

# Build Backend
docker build -t viacarraria/backend:latest ./viacarraria-backend/platforms/docker/

# Build Database Migrations
docker build -t viacarraria/database-migrate:latest ./viacarraria-database/platforms/docker/

# Build Parsing Worker & Embedding Engine
docker build -t viacarraria/parsing-worker:latest -f ./viacarraria-services/platforms/docker/parsing-worker.Dockerfile ./viacarraria-services/
docker build -t viacarraria/embedding-engine:latest -f ./viacarraria-services/platforms/docker/embedding-engine.Dockerfile ./viacarraria-services/
```

### 3.4. Deploy Helm Chart

```bash
helm upgrade --install viacarraria platforms/helm/graph-app \
  -f platforms/helm/graph-app/values-minikube.yaml \
  --namespace viacarraria --create-namespace
```

### 3.5. Verify Deployment

```bash
kubectl get pods -n viacarraria
kubectl get svc -n viacarraria
kubectl get ingress -n viacarraria
```

Open your browser and navigate to:
```
http://viacarraria.local
```

---

## 4. Production GKE Deployment Guide

### 4.1. Validate Chart & Schema Offline

Before deploying, run linting and dry-run rendering:

```bash
# Verify schema and templates
helm lint platforms/helm/graph-app -f platforms/helm/graph-app/values-production.yaml

# Render full manifests to inspect
helm template viacarraria platforms/helm/graph-app -f platforms/helm/graph-app/values-production.yaml > /tmp/rendered-production.yaml
```

### 4.2. Deploy to Production Cluster

```bash
# Authenticate with GKE
gcloud container clusters get-credentials viacarraria-prod-cluster --region=us-central1 --project=YOUR_PROJECT_ID

# Deploy Helm Release
helm upgrade --install viacarraria platforms/helm/graph-app \
  -f platforms/helm/graph-app/values-production.yaml \
  --namespace viacarraria --create-namespace \
  --wait --timeout 10m
```

### 4.3. Monitor Rollout & Ingress

```bash
# Check Pod rollout status
kubectl rollout status deployment/viacarraria-graph-app-backend -n viacarraria
kubectl rollout status deployment/viacarraria-graph-app-frontend -n viacarraria

# Check TLS Certificate issuance
kubectl get certificate -n viacarraria

# Inspect KEDA ScaledObjects
kubectl get scaledobject -n viacarraria
```

---

## 5. Helm Values Specification & Parameter Reference

### `secrets`
| Key | Type | Description |
| :--- | :--- | :--- |
| `databaseUrl` | string | Full PostgreSQL connection URI |
| `redisUrl` | string | Redis connection URI with authentication |
| `rabbitMqUrl` | string | RabbitMQ AMQP URI with user and password |
| `betterAuthUrl` | string | Canonical public URL of the backend API |
| `betterAuthSecret` | string | 32+ character random secret for JWT signing |
| `frontendOrigin` | string | Public origin URL of the frontend web application |
| `internalServiceToken` | string | Shared bearer token for internal microservice RPC |

### `storage` & `uploads`
| Key | Type | Description |
| :--- | :--- | :--- |
| `storage.driver` | string | Storage driver (`s3` or `local`) |
| `storage.s3.endpoint` | string | S3 endpoint URL (`https://storage.googleapis.com` or MinIO) |
| `storage.s3.bucket` | string | Destination bucket for parsed documents |
| `storage.s3.forcePathStyle` | string | S3 path-style addressing (`true` for MinIO, `false` for GCS/AWS) |
| `uploads.size` | string | Persistent volume claim size for local uploads (e.g. `10Gi`) |

### `ingress`
| Key | Type | Description |
| :--- | :--- | :--- |
| `enabled` | boolean | Enables Kubernetes Ingress resource |
| `className` | string | Ingress controller class name (`nginx` or `gce`) |
| `certManager.enabled` | boolean | Enables automated Let's Encrypt certificate acquisition |
| `certManager.clusterIssuer`| string | Name of the cert-manager ClusterIssuer (`letsencrypt-prod`) |
| `tls.enabled` | boolean | Enables TLS termination blocks |
| `hosts[].host` | string | Host domain name (e.g. `viacarraria.com`) |

### `autoscaling` (KEDA & HPA)
| Key | Type | Description |
| :--- | :--- | :--- |
| `parsingWorker.autoscaling.enabled` | boolean | Enables KEDA queue-length scaling for parser |
| `parsingWorker.autoscaling.minReplicaCount` | integer | Minimum pods (set to `0` for scale-to-zero) |
| `parsingWorker.autoscaling.maxReplicaCount` | integer | Maximum worker pods during heavy document loads |
| `embeddingEngine.autoscaling.enabled` | boolean | Enables KEDA queue-length scaling for neural TEI |
| `frontend.hpa.enabled` | boolean | Enables standard Kubernetes HPA for web frontend |
| `backend.hpa.enabled` | boolean | Enables standard Kubernetes HPA for backend API |

---

## 6. Operational Runbook & Maintenance

### 6.1. Inspecting Dead Letter Queue (DLQ)
When invalid or corrupt files exceed max retries (3 attempts), they are automatically routed to RabbitMQ's `document_parsing_dlq`. To inspect dead-lettered jobs:

```bash
kubectl exec -it deployment/viacarraria-graph-app-rabbitmq -n viacarraria -- rabbitmqctl list_queues name messages
```

### 6.2. Upgrading Application Versions
To perform a zero-downtime rolling update:

```bash
helm upgrade viacarraria platforms/helm/graph-app \
  -f platforms/helm/graph-app/values-production.yaml \
  --set frontend.image.tag=v0.2.0 \
  --set backend.image.tag=v0.2.0 \
  --namespace viacarraria
```
The pre-upgrade hook will automatically run database migrations before the new backend pods receive customer traffic.