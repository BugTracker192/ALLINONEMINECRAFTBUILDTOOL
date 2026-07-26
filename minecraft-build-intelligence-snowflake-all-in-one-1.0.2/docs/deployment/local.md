# Local deployment

Set `MINECRAFT_ASSET_ZIP` to a legally obtained asset archive and run `docker compose up --build`. The one-shot asset index service validates/extracts only render-relevant resources into the shared data volume. Web runs on `:8080`, API on `:8000`, renderer service on `:8090`, and MinIO console on `:9001`.
