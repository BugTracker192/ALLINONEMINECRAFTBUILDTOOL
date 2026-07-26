# API overview

All endpoints are under `/api/v1`; health endpoints remain unversioned. Uploads stream to quarantine storage and return an upload ID. Imports, snapshots, AI runs, and exports are jobs. The development adapter uses an in-process job manager; production uses Celery/Redis with the same state payload.

Errors use `{error:{code,message,details,recoverable}}`. Expensive create/commit routes must support idempotency keys before public deployment.
