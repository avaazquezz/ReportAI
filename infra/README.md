# Infra

- `docker-compose.yml` — local development (hot reload, Postgres port exposed, source bind-mounted). Run via the root `Makefile`.
- `docker-compose.prod.yml` — private-server deployment behind Traefik. Structurally complete but untested until Phase 4; assumes an external `web` Docker network and a Traefik certificate resolver named `le` already exist on the server.
