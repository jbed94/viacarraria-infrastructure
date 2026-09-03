# Via Carraria — Infrastructure Sub-Repository Specification (`viacarraria-infrastructure`)

This sub-repository manages local containerization, infrastructure topologies, Mamba environment configs, git pre-commit quality enforcement, and Kubernetes Helm cloud deployment.

---

## Technical Stack & Infrastructure Components

- **Local Container Orchestration**: Docker Compose (`docker-compose.infra.yaml` & `docker-compose.app.yaml`)
- **Environment Management**: Mamba (`environment.yml`, environment name `viacarraria`)
- **Quality Enforcement**: Pre-commit (`.pre-commit-config.yaml`), Ruff (Python), Biome / ESLint (JS/TS)
- **Cloud Deployment**: Kubernetes, Helm (`helm/graph-app`), KEDA (`ScaledObject`), Karpenter (Spot Node Provisioning)
- **Microservices Integration**: Links to worker and neural embedding services in [viacarraria-services/AGENTS.md](file:///home/jbed94/Projects/viacarraria/viacarraria-services/AGENTS.md)

---

## Submodule Architecture & Environment Management

- **Environment Definition (`environment.yml`)**: Mamba environment `viacarraria-infrastructure` containing minimal platform tools ONLY (e.g. `docker-cli`, `helm`, `kubectl`).
- **Submodule Directory Standard**:
  - `platforms/docker-compose/`: Local multi-service orchestration.
  - `platforms/helm/`: Production Kubernetes packaging.
  - Docker Compose and Helm platform directories exist exclusively in this sub-repository.

---

## Local Development Topology (`docker-compose`)

Local development separates base infrastructure from application services to optimize development isolation:

### 1. `docker-compose.infra.yaml` (Background Services)
Contains stateful databases, caches, and queue brokers exposed on `localhost`:
- **PostgreSQL 16**: Port 5432 (`./data/postgres`)
- **Weaviate Vector DB**: Ports 8080 (REST), 50051 (gRPC) (`./data/weaviate`)
- **RabbitMQ 3.12**: Ports 5672 (AMQP), 15672 (Management)
- **Redis 7**: Port 6379
- **Directus Admin UI**: Port 8055

### 2. `docker-compose.app.yaml` (Full System Verification)
Links `web` (frontend), `api` (backend), and `worker` (services) containers to the shared `graph_infra_net` network.

---

## Tooling & Pre-commit Configuration (`.pre-commit-config.yaml`)

Hooks are strictly scoped using regex path filtering to prevent cross-service overhead:
- Microservices Python code (`files: ^viacarraria-services/`): Scoped to `ruff` and `ruff-format`.
- Frontend React code (`files: ^viacarraria-frontend/`): Scoped to Biome / pnpm lint.
- Backend NestJS code (`files: ^viacarraria-backend/`): Scoped to NestJS linter.

---

## Production Cloud Deployment (Helm, KEDA & Scale-to-Zero)

The application is packaged as a Helm umbrella chart (`helm/graph-app`):

### 1. Component Scaling Matrix

| Component | Architecture | Autoscaling Mechanism | Scale-to-Zero? |
| :--- | :--- | :--- | :--- |
| **Frontend (React)** | Stateless CDN / Nginx | Standard K8s HPA | ❌ No |
| **Backend (Node.js API)** | Stateless Microservice | Standard K8s HPA (CPU/RPS) | ❌ No (min 1 pod) |
| **Parsing Worker (`viacarraria-services`)** | Async Queue Consumer | KEDA (`ScaledObject` on RabbitMQ queue depth) | ✅ **YES** (0 pods when idle) |
| **TEI Engine (`viacarraria-services`)** | Heavy Neural Service | KEDA + Karpenter (Spot GPU / Compute) | ✅ **YES** (0 pods when idle) |
| **Stateful DBs (Postgres/Weaviate)** | Stateful Infrastructure | Vertical Node Scaling | ❌ No |

### 2. KEDA & Karpenter "Zero-Waste" Strategy
- **KEDA**: Monitors RabbitMQ `document_parsing_queue`. When queue depth reaches 0, KEDA scales worker and TEI pods down to 0 replicas.
- **Karpenter**: Detects when unscheduled worker pods are pending, provisions cloud compute/GPU instances (EC2 Spot) within seconds, and automatically terminates instances when KEDA scales pods back to 0.
