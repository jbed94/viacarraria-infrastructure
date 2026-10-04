# Via Carraria — Infrastructure Specification (`viacarraria-infrastructure`)

Infrastructure orchestration: local container topology, S3 storage proxy, Mamba environment configs, pre-commit enforcement, and Kubernetes cloud deployment with scale-to-zero autoscaling.

---

## Tech Stack

- **Containerization**: Docker Compose (`platforms/docker-compose/`)
- **Environment Management**: Mamba (`environment.yml`, env `viacarraria-infrastructure`)
- **Quality Enforcement**: Pre-commit (`.pre-commit-config.yaml`), Ruff (Python), Biome / ESLint (JS/TS)
- **Object Storage**: MinIO (local dev) with multi-cloud upstream proxy tiering (AWS S3, Google Cloud Storage)
- **Production Orchestration**: Kubernetes, Helm (`platforms/helm/graph-app`), KEDA (`ScaledObject`), Karpenter (EC2 Spot instance provisioning)

---

## Environment & Directory Rules

- **Env (`environment.yml`)**: Mamba env `viacarraria-infrastructure`. Tools: `docker-cli`, `helm`, `kubectl` only.
- **Directories**:
  - `platforms/docker-compose/`: local multi-container development topology.
  - `platforms/helm/`: production Kubernetes manifests.
  - Only this sub-repository owns Docker Compose and Helm platform directories.

---

## Local Development Topology (`docker-compose`)

Development separates foundational infrastructure from application services on network `graph_infra_net`:

### 1. `docker-compose.infra.yaml` (Base Infrastructure)
- **PostgreSQL 16**: Port 5432. Relational and JSONB graph storage.
- **Redis 7**: Port 6379. Session caching, daily AI rate limiting, and deduplication hashes.
- **RabbitMQ 3.13**: Ports 5672 (AMQP) and 15672 (Management). Task broker with priority queues.
- **Weaviate**: Ports 8080 (REST) and 50051 (gRPC). Multi-tenant vector database.
- **MinIO**: Ports 9000 (S3 API) and 9001 (Web Console). S3-compatible document storage.
- **MinIO Bucket Initializer**: Automates bucket creation (`viacarraria-sources`) and configures upstream storage proxy rules for AWS S3 and GCS tiers.

### 2. `docker-compose.app.yaml` (Application Services)
- **`database-migrate`**: Runs Prisma database migrations against PostgreSQL before application boots.
- **`api`**: Backend NestJS microservice on Port 3000.
- **`web`**: Main React canvas application on Port 4173.
- **`admin-web`**: Standalone Decoupled Admin Panel on loopback Port 4174 (`Dockerfile.admin`).
- **`parsing-worker`**: FastStream Python worker consuming document parsing jobs.
- **`embedding-engine`**: HuggingFace Text Embeddings Inference (TEI) on Port 8081 for dense vector generation.
- **`reranking-engine`**: HuggingFace TEI serving BGE Reranker on Port 8082 for precision scoring.
- **`api-test` / `api-e2e`**: Dedicated test container profiles for isolated verification.

---

## Pre-commit Quality Enforcement (`.pre-commit-config.yaml`)

Hooks scoped by regex path to prevent cross-submodule overhead:
- **Services** (`files: ^viacarraria-services/`): Scoped to `ruff` and `ruff-format`.
- **Frontend** (`files: ^viacarraria-frontend/`): Scoped to Biome and pnpm lint.
- **Backend** (`files: ^viacarraria-backend/`): Scoped to NestJS linter.

---

## Production Cloud Deployment (Helm, KEDA, Scale-to-Zero)

Packaged as a Helm umbrella chart (`platforms/helm/graph-app`):

- **Stateless Services (Frontend, Backend)**: Autoscaled via standard Kubernetes Horizontal Pod Autoscaler (HPA) based on CPU and request rate.
- **Worker & Neural Inference (Parsing Worker, TEI Engine)**:
  - Autoscaled to zero via KEDA monitoring RabbitMQ `document_parsing_queue` depth.
  - When queue depth reaches 0, KEDA scales worker and TEI pods down to 0 replicas.
  - Karpenter detects pending neural worker pods, provisions cloud compute/GPU instances (EC2 Spot) within seconds, and terminates nodes when pods scale back to 0.
- **Stateful Infrastructure (PostgreSQL, Weaviate, MinIO)**: Deployed with persistent volume claims and vertical scaling.
