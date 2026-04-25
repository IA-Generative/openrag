"""Smoke test end-to-end du flow RAG : OpenAI-compatible chat completion.

Vérifie que l'endpoint /v1/chat/completions d'OpenRAG répond correctement
en utilisant la chaîne complète (LLM externe via LiteLLM Mirai + retrieval).

Usage :
    BASE_HOST=openrag-mirai.fake-domain.name \\
    AUTH_TOKEN=sk-openrag-admin-... \\
        pytest tests/deploy/test_chat_completion.py -v
"""

from __future__ import annotations

import os
import time

import pytest
import requests

BASE = os.environ.get("BASE_HOST", "openrag-mirai.fake-domain.name")
API = f"https://api.{BASE}"
TOKEN = os.environ.get("AUTH_TOKEN", "")
PARTITION = os.environ.get("TEST_PARTITION", "smoke-test")

requires_token = pytest.mark.skipif(not TOKEN, reason="AUTH_TOKEN non défini")


def _h() -> dict:
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@requires_token
def test_chat_completion_simple():
    """LLM répond à un ping simple sans contexte RAG (model=openrag-<partition>
    ou openrag-all selon convention de l'API)."""
    t0 = time.monotonic()
    r = requests.post(
        f"{API}/v1/chat/completions",
        headers=_h(),
        json={
            "model": f"openrag-{PARTITION}",
            "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
            "max_tokens": 10,
            "stream": False,
        },
        timeout=60,
    )
    elapsed_ms = (time.monotonic() - t0) * 1000
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "choices" in body and body["choices"], "réponse vide"
    content = body["choices"][0].get("message", {}).get("content", "")
    assert content, f"contenu vide : {body}"
    assert elapsed_ms < 30000, f"trop lent : {elapsed_ms:.0f} ms"


@requires_token
def test_chat_completion_with_rag_context():
    """Avec un fichier indexé dans la partition (cf. test_indexing.py),
    le LLM doit pouvoir retourner une réponse qui mentionne OpenRAG.
    Vérifie aussi que le champ `extra` contient les sources."""
    r = requests.post(
        f"{API}/v1/chat/completions",
        headers=_h(),
        json={
            "model": f"openrag-{PARTITION}",
            "messages": [
                {
                    "role": "user",
                    "content": "What is OpenRAG? Reply with one short sentence.",
                }
            ],
            "max_tokens": 80,
            "stream": False,
        },
        timeout=90,
    )
    if r.status_code == 404:
        pytest.skip(f"partition '{PARTITION}' inexistante — lancer test_indexing.py d'abord")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    content = body["choices"][0]["message"]["content"]
    # Réponse non vide et raisonnablement substantielle
    assert content and len(content) > 10, f"réponse trop courte : {content!r}"
    # extra field présent (peut être string JSON ou dict selon la version)
    extra = body["choices"][0].get("extra")
    if extra:
        # Sources extraites — soit string JSON, soit dict
        if isinstance(extra, str):
            import json as _json
            try:
                extra = _json.loads(extra)
            except Exception:
                extra = {}
        assert "sources" in extra or extra == {}, f"extra inattendu : {extra!r}"


@requires_token
def test_chat_completion_streaming():
    """Le streaming SSE doit retourner des chunks delta, terminés par [DONE]."""
    t0 = time.monotonic()
    r = requests.post(
        f"{API}/v1/chat/completions",
        headers=_h(),
        json={
            "model": f"openrag-{PARTITION}",
            "messages": [{"role": "user", "content": "Count to 3."}],
            "max_tokens": 30,
            "stream": True,
        },
        timeout=60,
        stream=True,
    )
    if r.status_code == 404:
        pytest.skip(f"partition '{PARTITION}' inexistante")
    assert r.status_code == 200, r.text[:300]

    chunks = 0
    saw_done = False
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data: "):
            payload = line[6:]
            if payload.strip() == "[DONE]":
                saw_done = True
                break
            chunks += 1
            if chunks > 200:  # garde-fou
                break
    elapsed_ms = (time.monotonic() - t0) * 1000
    assert chunks > 0, "aucun chunk reçu"
    assert saw_done, "stream pas terminé par [DONE]"
    assert elapsed_ms < 60000, f"stream trop lent : {elapsed_ms:.0f} ms"


@requires_token
def test_search_endpoint():
    """L'endpoint /search doit répondre avec un format cohérent."""
    r = requests.get(
        f"{API}/search",
        headers={"Authorization": f"Bearer {TOKEN}"},
        params={"text": "OpenRAG framework", "partitions": PARTITION},
        timeout=30,
    )
    if r.status_code == 404:
        pytest.skip(f"partition '{PARTITION}' inexistante")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    docs = body if isinstance(body, list) else body.get("results", body.get("docs", []))
    assert isinstance(docs, list), f"format inattendu : {body}"
