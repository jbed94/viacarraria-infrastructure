# Via Carraria — GCP (GKE) Cloud Architecture vs Minikube Comparison

This document provides a comparative architectural breakdown between the local **Minikube** development profile and the production **Google Cloud Platform (GKE)** profile.

---

## 1. Architectural Topology Comparison

```
LOCAL MINIKUBE TOPOLOGY (Single-Node Docker Emulation)
┌────────────────────────────────────────────────────────────────────────┐
│ Host Machine (AMD Ryzen 9 / 128GB RAM)                                 │
│                                                                        │
│   Tailscale Mesh ──► Port-Forward (8080:80) ──► NGINX Ingress          │
│                                                       │                │
│   ┌───────────────────────────────────────────────────┴────────────┐   │
│   │ Minikube Cluster (12 vCPUs / 32GB RAM)                         │   │
│   │                                                                │   │
│   │   • Frontend SPA (Nginx) ──► Backend API (NestJS)              │   │
│   │   • In-Cluster Postgres 16   • In-Cluster Redis 7              │   │
│   │   • In-Cluster RabbitMQ      • In-Cluster Weaviate             │   │
│   │   • In-Cluster MinIO (S3)    • KEDA (Scale-to-Zero Workers)    │   │
│   │   • `standard` StorageClass (Docker HostPath)                  │   │
│   └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘

GOOGLE CLOUD PLATFORM (GKE) PRODUCTION TOPOLOGY
┌────────────────────────────────────────────────────────────────────────┐
│ Google Cloud VPC (europe-west1)                                        │
│                                                                        │
│   Internet ──► Cloud Armor DDoS ──► Global Application Load Balancer   │
│                                              │ (Managed SSL / CDN)     │
│   ┌──────────────────────────────────────────┴─────────────────────┐   │
│   │ Google Kubernetes Engine (GKE Autopilot / Multi-Zone)          │   │
│   │                                                                │   │
│   │   • Frontend Pods (3-15 HPA)   • Backend Pods (3-20 HPA)       │   │
│   │   • Spot Worker Nodes (KEDA Scale-to-Zero Docling Workers)     │   │
│   │   • Weaviate Vector DB (pd-ssd Compute Engine Disks)           │   │
│   │   • RabbitMQ HA Cluster (pd-balanced Compute Engine Disks)     │   │
│   │   • Workload Identity Federation (IAM SA ◄──► K8s SA)          │   │
│   └───────────────┬───────────────────────────────┬────────────────┘   │
│                   │ Private Service Connect       │ Private Access     │
│                   ▼                               ▼                    │
│   ┌───────────────────────────────┐ ┌──────────────────────────────┐   │
│   │ Managed Google Cloud SQL      │ │ Google Cloud Storage (GCS)   │   │
│   │ (PostgreSQL 16 HA + Read Reps)│ │ (11 9s Multi-Regional)       │   │
│   ├───────────────────────────────┤ ├──────────────────────────────┤   │
│   │ Managed Cloud Memorystore     │ │ Google Secret Manager        │   │
│   │ (Redis 7 HA Standard Tier)    │ │ (Encrypted Runtime Secrets)  │   │
│   └───────────────────────────────┘ └──────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Detailed Dimension Comparison

| Architectural Dimension | Local Minikube Profile | Google Cloud Platform (GKE) Profile |
|---|---|---|
| **Ingress & Routing** | Community NGINX Ingress (`ingressClassName: nginx`), NodePort service, manual host port forward. | Google Cloud External Application Load Balancer (`ingressClassName: gce`), global anycast VIP, integrated Cloud CDN. |
| **SSL / TLS Termination** | Tailscale Serve (`tailscale serve --bg 8080`) or self-signed certs. | Google-Managed SSL Certificates (`networking.gke.io/v1: ManagedCertificate`), automatic Google CA issuance & zero-downtime renewal. |
| **DDoS & Web Security** | Local NGINX rate-limiting rules. | Google Cloud Armor edge defense (WAF, Geo-blocking, Layer 7 rate limiting). |
| **Storage CSI** | `standard` StorageClass (hostPath on Docker Linux VM, single-node bound). | Compute Engine Persistent Disk CSI (`pd-balanced` for general workloads, `pd-ssd` for vector/database IOPS). Multi-zone regional replication. |
| **Object Storage** | In-cluster MinIO pod backed by local PVC. | Google Cloud Storage (GCS) Multi-Regional (99.999999999% durability, Nearline/Coldline automated lifecycle rules). |
| **Relational Database** | In-cluster PostgreSQL 16 StatefulSet with 2GB disk. | Google Cloud SQL for PostgreSQL 16 (Private Service Connect, automated PITR backups, automated HA failover). |
| **Caching & Rate Limiting** | In-cluster Redis 7 pod. | Google Cloud Memorystore for Redis (HA Standard Tier with automated cross-zone replication). |
| **Identity & IAM** | Plain Kubernetes Secret objects. | GKE Workload Identity Federation (linking Kubernetes ServiceAccounts to Google Cloud IAM ServiceAccounts). |
| **Autoscaling Mechanics** | Local `metrics-server` (CPU/Memory HPA), KEDA queue triggers (scale-to-zero) constrained by host machine CPU. | GKE Cluster Autoscaler / Karpenter automatically provisions/drains Compute Engine VMs; worker pods run on GKE Spot Instances. |
| **High Availability & PDB** | Disabled (single pod baseline for all services). | PodDisruptionBudgets active (`minAvailable: 2`), multi-zone `podAntiAffinity` rules, zero-trust NetworkPolicies. |

---

## 3. Helm Values Parity Mapping

- **Local Development**: Use [`platforms/helm/graph-app/values-minikube.yaml`](file:///home/jbed94/Projects/viacarraria/viacarraria-infrastructure/platforms/helm/graph-app/values-minikube.yaml)
- **Production GCP**: Use [`platforms/helm/graph-app/values-gcp.yaml`](file:///home/jbed94/Projects/viacarraria/viacarraria-infrastructure/platforms/helm/graph-app/values-gcp.yaml)
