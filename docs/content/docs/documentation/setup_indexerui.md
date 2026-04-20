---
title: Indexer UI
---

## Configuring the Indexer UI

### 1. Download the `indexer-ui` Submodule

> Ensure the `indexer-ui` submodule is initialized and downloaded. If not, run the following command from the root of your `openrag` project:

```bash
cd <project-name> # openrag project
git submodule update --init --recursive
```

:::note
The `--init --recursive` flags will:

* Initialize all submodules defined in the `.gitmodules` file
* Clone the content of each submodule
* Recursively initialize and update nested submodules
:::

:::caution[Important]
Each version of **`openrag`** ships with a specific compatible commit of [indexer-ui](https://github.com/linagora/openrag-admin-ui). The above command is sufficient.
In development mode, to fetch the latest version of `indexer-ui`, run:
```bash title="fetching the latest version of submodules..."
git submodule foreach 'git checkout main && git pull'
```
:::

### 2. Set Environment Variables

To enable the Indexer UI, add the following environment variables to your configuration:

* Replace **`X.X.X.X`** with `localhost` (for local deployment) or your server IP
* Replace **`APP_PORT`** with your FastAPI port (default: 8080)
* Set the **base URL of the Indexer UI** (required to prevent CORS issues). Replace **`INDEXERUI_PORT`** accordingly
* Set the **base URL of your FastAPI backend** (used by the frontend). Replace **`APP_PORT`** accordingly

```bash
INCLUDE_CREDENTIALS=false # Set to true if FastAPI authentication is enabled
INDEXERUI_PORT=8060 # Port for the Indexer UI (default: 3042)
INDEXERUI_URL='http://X.X.X.X:INDEXERUI_PORT'
API_BASE_URL='http://X.X.X.X:APP_PORT'
```

### 3. Mount the Indexer UI under a Subpath (optional)

By default the Indexer UI is served at the root of its own origin (`http://host:INDEXERUI_PORT/`). If you want to expose it **on the same vhost as the backend** (behind a reverse proxy), you can mount it under a subpath via `INDEXERUI_BASE_PATH`. The typical reason is to keep the frontend and the backend same-origin.
With this setup, the backend's session cookie is first-party to the UI (this matters when `AUTH_MODE=oidc`, where a cross-origin `openrag_session` cookie is dropped by the browser).

```bash
# Empty (default) → root-level deployment.
# Set to mount under a subpath — leading slash required, no trailing slash.
INDEXERUI_BASE_PATH=/indexerui
```

:::caution[Rebuild required]
`INDEXERUI_BASE_PATH` is consumed as a **Docker build ARG** (passed to the `indexer-ui` Dockerfile via `docker-compose.yaml`), not a runtime variable. The SvelteKit app bakes the value into every asset URL and every API call at build time. After changing it you must rebuild the image:

```bash
docker compose build indexer-ui
docker compose up -d indexer-ui
```
:::

#### Example nginx rules (single vhost)

```nginx
server {
    listen 443 ssl http2;
    server_name rag.example.com;

    # ... TLS config ...

    # Indexer UI mounted under /indexerui/
    location /indexerui/ {
        proxy_pass         http://indexer-ui:3000/;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # Everything else → backend (API, /auth/*, /chainlit, /static, ...)
    location / {
        proxy_pass         http://openrag:8080;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

The trailing slash on `proxy_pass http://indexer-ui:3000/;` is load-bearing — it strips the `/indexerui` prefix before forwarding, leaving the SvelteKit app to re-add its `base` via `INDEXERUI_BASE_PATH`.