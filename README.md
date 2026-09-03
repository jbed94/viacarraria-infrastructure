# Via Carraria Infrastructure

Local Docker Compose topology, Helm packaging, and platform validation for Via
Carraria.

## Tooling

```bash
mamba env create -f environment.yml
mamba run -n viacarraria-infrastructure bash scripts/install-platform-tools.sh
mamba run -n viacarraria-infrastructure docker compose version
mamba run -n viacarraria-infrastructure helm lint platforms/helm/graph-app
mamba run -n viacarraria-infrastructure pre-commit run --all-files
```

The conda-forge channel does not publish `helm` or `kubectl` packages. The
bootstrap script downloads pinned Linux binaries from the official Helm and
Kubernetes release endpoints, verifies their SHA-256 checksums, and installs
them into the `viacarraria-infrastructure` environment. Override
`HELM_VERSION` or `KUBECTL_VERSION` when a different cluster-compatible
version is required.

Set `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` for production.
Local Compose leaves these unset and uses its ioredis limiter fallback; the
backend refuses requests in production when distributed limiter credentials are
missing.

Run the Compose-backed API end-to-end journey after starting the API stack:

```bash
mamba run -n viacarraria-infrastructure docker compose \
	-f platforms/docker-compose/docker-compose.infra.yaml \
	-f platforms/docker-compose/docker-compose.app.yaml \
	up -d --build api
mamba run -n viacarraria-infrastructure docker compose \
	-f platforms/docker-compose/docker-compose.infra.yaml \
	-f platforms/docker-compose/docker-compose.app.yaml \
	run --rm api-e2e
```

Compose runs PostgreSQL, Redis, RabbitMQ, Weaviate, Directus, the migration/seed
job, API, TEI, worker, and web client. The Helm chart deploys the API/client,
worker/TEI services, shared upload storage, and KEDA queue scalers; production
secrets and image references are supplied through chart values.
