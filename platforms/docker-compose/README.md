# Docker Compose

The local topology is split into persistent infrastructure and application
services.

```bash
docker compose -f platforms/docker-compose/docker-compose.infra.yaml up -d
docker compose -f platforms/docker-compose/docker-compose.app.yaml up --build
```

The application stack runs a one-shot `database-migrate` service before starting
the API. Copy `.env.example` to `.env` before customizing local values. The
default TEI model is intentionally lightweight for CPU development; set
`TEI_MODEL_ID=google/embeddinggemma-300m` when local resources support it.