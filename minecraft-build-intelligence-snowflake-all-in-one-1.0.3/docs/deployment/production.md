# Production deployment

Use managed PostgreSQL/Redis/S3-compatible storage, TLS at an ingress, non-root read-only images, isolated parse/render worker pools, no default credentials, encrypted provider keys, signed artifact URLs, backups, migration jobs, OTel collectors, rate limits, pod disruption budgets, and network policies that deny parser egress. The Compose file is development-only.
