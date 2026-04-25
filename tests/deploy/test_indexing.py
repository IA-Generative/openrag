"""Test d'ingestion bout-en-bout : upload d'un petit doc texte, vérif qu'il
apparaît dans la liste des fichiers.

Suppose un AUTH_TOKEN admin disponible (le bearer reste valide même en
mode AUTH_MODE=oidc — utilisé pour les appels programmatiques / CI).

Usage :
    BASE_HOST=openrag-mirai.fake-domain.name \\
    AUTH_TOKEN=sk-openrag-admin-... \\
        pytest tests/deploy/test_indexing.py -v
"""

from __future__ import annotations

import io
import os
import time
import uuid

import pytest
import requests

BASE = os.environ.get("BASE_HOST", "openrag-mirai.fake-domain.name")
API = f"https://api.{BASE}"
TOKEN = os.environ.get("AUTH_TOKEN", "")

PARTITION = os.environ.get("TEST_PARTITION", "smoke-test")

requires_token = pytest.mark.skipif(not TOKEN, reason="AUTH_TOKEN non défini")


def _h() -> dict:
    return {"Authorization": f"Bearer {TOKEN}"}


@requires_token
def test_health():
    r = requests.get(f"{API}/health_check", timeout=10)
    assert r.status_code == 200


@requires_token
def test_partition_create_or_exists():
    r = requests.post(
        f"{API}/partition", headers=_h(), json={"name": PARTITION}, timeout=15
    )
    # 200/201 si créé, 409 si déjà existant — les deux ok
    assert r.status_code in (200, 201, 409), r.text[:200]


@requires_token
def test_upload_small_document():
    content = (
        f"Document smoke test généré à {time.strftime('%Y-%m-%dT%H:%M:%S')}.\n"
        f"Identifiant unique : {uuid.uuid4().hex}\n"
        f"OpenRAG est un framework RAG modulaire FastAPI/Ray/Milvus.\n"
    ).encode("utf-8")

    files = {"file": (f"smoke-{uuid.uuid4().hex[:8]}.txt", io.BytesIO(content), "text/plain")}
    r = requests.post(
        f"{API}/indexer/add_file",
        headers=_h(),
        params={"partition": PARTITION},
        files=files,
        timeout=60,
    )
    assert r.status_code in (200, 202), r.text[:300]
    body = r.json()
    task_id = body.get("task_id") or body.get("id") or body.get("file_id")
    assert task_id, f"pas de task_id dans la réponse : {body}"


@requires_token
def test_files_list_eventually_contains_uploaded():
    """Liste les fichiers ; doit contenir au moins 1 entrée après l'upload."""
    deadline = time.time() + 60
    while time.time() < deadline:
        r = requests.get(
            f"{API}/indexer/files",
            headers=_h(),
            params={"partition": PARTITION},
            timeout=15,
        )
        if r.status_code == 200:
            files = r.json()
            if isinstance(files, dict):
                files = files.get("files", files.get("data", []))
            if files:
                return  # ok
        time.sleep(2)
    pytest.fail("aucun fichier visible dans la partition après 60s")


@requires_token
def test_search_finds_uploaded_content():
    """Recherche un terme distinctif du document uploadé."""
    # Le mot 'OpenRAG' est dans le contenu du upload
    r = requests.get(
        f"{API}/search",
        headers=_h(),
        params={"text": "OpenRAG framework", "partitions": PARTITION},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    docs = body if isinstance(body, list) else body.get("results", body.get("docs", []))
    assert docs, "aucun résultat de recherche"
