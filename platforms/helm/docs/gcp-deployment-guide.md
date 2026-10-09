# Via Carraria — Google Cloud Platform (GCP / GKE) Production Deployment Guide

This guide details the complete procedure for provisioning Google Cloud Platform infrastructure and deploying the Via Carraria platform to Google Kubernetes Engine (GKE) using the production Helm profile.

---

## 1. Prerequisites & GCP Access Preparation

### 1.1 Install the Google Cloud SDK (`gcloud`)
```bash
# Verify or install gcloud CLI
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud version
```

### 1.2 Authenticate & Select Target Project
```bash
# Authenticate your Google Cloud account
gcloud auth login

# Set project ID and default compute region
export PROJECT_ID="your-gcp-project-id"
export REGION="europe-west1"
export ZONE="europe-west1-b"

gcloud config set project "$PROJECT_ID"
gcloud config set compute/region "$REGION"
gcloud config set compute/zone "$ZONE"
```

---

## 2. Required GCP APIs & Services to Enable

Execute the following command to enable all necessary Google Cloud APIs:

```bash
gcloud services enable \
  container.googleapis.com \
  compute.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  servicenetworking.googleapis.com \
  cloudresourcemanager.googleapis.com
```

### Explanation of Enabled Services:
- `container.googleapis.com`: Google Kubernetes Engine (GKE) cluster control plane and node pools.
- `compute.googleapis.com`: GCE virtual machine instances, VPC networks, and Global External Application Load Balancers.
- `sqladmin.googleapis.com`: Managed Google Cloud SQL for PostgreSQL 16.
- `redis.googleapis.com`: Managed Google Cloud Memorystore for Redis.
- `storage.googleapis.com`: Google Cloud Storage (GCS) for object storage.
- `secretmanager.googleapis.com`: Secure storage and injection of production API tokens and database credentials.
- `servicenetworking.googleapis.com`: Private Service Connect and VPC peering for private database communication.

---

## 3. Infrastructure Provisioning

### 3.1 VPC Network & Private Service Connection
```bash
# Create custom VPC network
gcloud compute networks create viacarraria-vpc --subnet-mode=custom

# Create subnet for GKE nodes and pods
gcloud compute networks subnets create viacarraria-gke-subnet \
  --network=viacarraria-vpc \
  --region=$REGION \
  --range=10.10.0.0/20 \
  --secondary-range=pods=10.20.0.0/16,services=10.30.0.0/20

# Allocate IP range for private services (Cloud SQL and Memorystore)
gcloud compute addresses create google-managed-services-viacarraria \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network=viacarraria-vpc

gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-viacarraria \
  --network=viacarraria-vpc
```

---

### 3.2 GKE Cluster with Workload Identity & GCE Ingress
```bash
gcloud container clusters create-auto viacarraria-prod-cluster \
  --region=$REGION \
  --network=viacarraria-vpc \
  --subnetwork=viacarraria-gke-subnet \
  --cluster-secondary-range-name=pods \
  --services-secondary-range-name=services \
  --enable-private-nodes \
  --master-ipv4-cidr=172.16.0.0/28 \
  --enable-master-authorized-networks \
  --master-authorized-networks=$(curl -s ifconfig.me)/32

# Get cluster credentials for kubectl
gcloud container clusters get-credentials viacarraria-prod-cluster --region=$REGION
```

---

### 3.3 Managed Cloud SQL for PostgreSQL 16
```bash
# Provision Cloud SQL instance with Private IP
gcloud sql instances create viacarraria-postgres-prod \
  --database-version=POSTGRES_16 \
  --tier=db-custom-4-16384 \
  --region=$REGION \
  --network=projects/$PROJECT_ID/global/networks/viacarraria-vpc \
  --no-assign-ip \
  --availability-type=REGIONAL \
  --storage-type=SSD \
  --storage-size=50GB \
  --storage-auto-increase \
  --backup \
  --enable-point-in-time-recovery

# Create application database and user
gcloud sql databases create viacarraria --instance=viacarraria-postgres-prod
gcloud sql users create viacarraria_app \
  --instance=viacarraria-postgres-prod \
  --password="GENERATE_STRONG_RANDOM_PASSWORD"
```

---

### 3.4 Managed Memorystore for Redis
```bash
gcloud redis instances create viacarraria-redis-prod \
  --size=4 \
  --region=$REGION \
  --zone=$ZONE \
  --network=viacarraria-vpc \
  --redis-version=redis_7_0 \
  --tier=STANDARD_HA
```

---

### 3.5 Google Cloud Storage (GCS) Bucket
```bash
# Create multi-regional bucket with uniform bucket-level access
gcloud storage buckets create gs://viacarraria-sources-prod \
  --location=EU \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access

# Create HMAC interoperability key for S3-compatible XML API
gcloud storage hmac create viacarraria-storage-sa@$PROJECT_ID.iam.gserviceaccount.com
```

---

### 3.6 GKE Workload Identity Setup
```bash
# Create GCP IAM Service Account
gcloud iam service-accounts create viacarraria-k8s \
  --description="Service account for Via Carraria GKE pods" \
  --display-name="viacarraria-k8s"

# Grant GCS storage object admin permissions
gcloud storage buckets add-iam-policy-binding gs://viacarraria-sources-prod \
  --member="serviceAccount:viacarraria-k8s@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Allow Kubernetes ServiceAccount in namespace 'viacarraria' to impersonate GCP SA
gcloud iam service-accounts add-iam-policy-binding viacarraria-k8s@$PROJECT_ID.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:$PROJECT_ID.svc.id.goog[viacarraria/viacarraria-graph-app]"
```

---

## 4. Deploying Via Carraria to GKE via Helm

### 4.1 Create Google-Managed SSL Certificate & FrontendConfig
Create `platforms/helm/graph-app/templates/gcp-ingress-extras.yaml` (or apply directly):

```yaml
apiVersion: networking.gke.io/v1
kind: ManagedCertificate
metadata:
  name: viacarraria-managed-cert
  namespace: viacarraria
spec:
  domains:
    - app.viacarraria.com
---
apiVersion: networking.gke.io/v1beta1
kind: FrontendConfig
metadata:
  name: viacarraria-frontend-config
  namespace: viacarraria
spec:
  redirectToHttps:
    enabled: true
    responseCodeName: MOVED_PERMANENTLY_DEFAULT
```

### 4.2 Deploy Helm Release
```bash
# Ensure target namespace exists
kubectl create namespace viacarraria --dry-run=client -o yaml | kubectl apply -f -

# Deploy using the GCP values profile
helm upgrade --install viacarraria ./viacarraria-infrastructure/platforms/helm/graph-app \
  -f ./viacarraria-infrastructure/platforms/helm/graph-app/values-gcp.yaml \
  --namespace viacarraria \
  --set secrets.databaseUrl="postgresql://viacarraria_app:PASSWORD@PRIVATE_IP:5432/viacarraria?sslmode=require" \
  --set secrets.redisUrl="redis://default:REDIS_AUTH@REDIS_PRIVATE_IP:6379" \
  --wait \
  --timeout 15m
```

---

## 5. Post-Deployment Verification & DNS Setup

1. **Retrieve External Load Balancer IP**:
   ```bash
   kubectl get ingress viacarraria-graph-app -n viacarraria
   # Look for the ADDRESS column (e.g., 34.149.x.x)
   ```
2. **Point DNS A Record**:
   Point your domain (e.g. `app.viacarraria.com`) to the external IP.
3. **Monitor Managed Certificate Status**:
   ```bash
   kubectl describe managedcertificate viacarraria-managed-cert -n viacarraria
   # Status transitions from 'Provisioning' to 'Active' once DNS propagates
   ```
