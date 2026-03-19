---
title: Milvus Migrations
---

# Milvus Upgrade
OpenRAG has been upgraded from Milvus **2.5.4** to **2.6.11** to leverage the enhancements introduced in the latest releases, particularly the new temporal querying capabilities added in version **2.6.6+**.

## What's New in 2.6.x

Milvus 2.6.6+ introduced the **`TIMESTAMPTZ`** field type, which enables:

- **Comparison and range filtering** using standard operators (`=`, `!=`, `<`, `>`, etc.)
- **Interval arithmetic** — add or subtract durations (days, hours, minutes) directly in filter expressions
- **Time-based indexing** for faster temporal queries
- **Combined filtering** — pair timestamp conditions with vector similarity search

**Example — basic comparison:**
```python
expr = "tsz != ISO '2025-01-03T00:00:00+08:00'"
results = client.query(
    collection_name,
    filter=expr,
    output_fields=["id", "tsz"],
    limit=10
)
```

**Example — interval arithmetic:**
```python
expr = "tsz + INTERVAL 'P1D' > ISO '2025-01-03T00:00:00+08:00'"
results = client.query(
    collection_name,
    filter=expr,
    output_fields=["id", "tsz"],
    limit=10
)
```

> `INTERVAL` values follow [ISO 8601 duration](https://en.wikipedia.org/wiki/ISO_8601#Durations) syntax:
> * `P1D` = 1 day
> * `PT3H` = 3 hours
> * `P2DT6H` = 2 days and 6 hours.

## Current State

:::info
Temporal fields are currently stored as **strings**, not **`TIMESTAMPTZ`**. Migrating to `TIMESTAMPTZ` requires a schema and index change, and Milvus doesn't support migrations on schema and index changes: it has to be handled manually.

Until a Milvus schema & index migration strategy is defined, filtering still works via **lexicographic string comparison** on ISO 8601 strings:
```python
expr = "tsz != '2025-01-03T00:00:00+08:00'"  # No ISO/INTERVAL keywords
results = client.query(
    collection_name,
    filter=expr,
    output_fields=["id", "tsz"],
    limit=10
)
```
Full `TIMESTAMPTZ` support will be activated in a future release once the migration is established.
:::

## Milvus Version Upgrade Steps

:::danger[Who needs this migration?]
This migration is only required if you are upgrading from **OpenRAG <= 1.1.7**, which shipped with Milvus <= 2.5.x. If your deployment already runs Milvus 2.6.x, skip this section.
:::

> For the full official reference, see the [Milvus upgrade guide](https://milvus.io/docs/upgrade_milvus_standalone-docker.md#Upgrade-process).

### Step 1 — Upgrade Milvus to 2.5.16 (intermediate step)

:::caution[Do not update OpenRAG yet]
During this step, keep your current version of OpenRAG (<= 1.1.7) running. Only the Milvus image is changed here. OpenRAG itself is updated in Step 2.
:::

Milvus requires an intermediate upgrade to **v2.5.16** before jumping to 2.6.x. This step must be done manually **before** updating OpenRAG.

Temporarily edit `vdb/milvus.yaml` to set the intermediate Milvus image:

```diff lang=yaml
// vdb/milvus.yaml
milvus:
-  image: milvusdb/milvus:v2.5.4
+  image: milvusdb/milvus:v2.5.16
```

Then restart Milvus and wait for it to be healthy:

```bash
docker compose down
docker compose up milvus -d
```

Verify it is running and healthy before continuing:

```bash
docker inspect milvus-standalone --format '{{ .Config.Image }}'
# Expected: milvusdb/milvus:v2.5.16
```

### Step 2 — Update OpenRAG

Once Milvus 2.5.16 is healthy, stop all services and update OpenRAG to the new version. The updated `vdb/milvus.yaml` already includes Milvus 2.6.11 and the required MinIO and etcd upgrades.

```bash
docker compose down
```

Verify that all containers are stopped:

```bash
docker ps | grep milvus
```

Pull or checkout the new OpenRAG release, then start the stack:

```bash
docker compose up -d
```

Confirm the running Milvus version:

```bash
docker inspect milvus-standalone --format '{{ .Config.Image }}'
# Expected: milvusdb/milvus:v2.6.11
```
