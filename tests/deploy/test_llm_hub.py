"""Vérifie que le hub LLM Mirai répond depuis la VM.

Lit la config depuis l'env (mêmes vars qu'OpenRAG : BASE_URL, API_KEY, MODEL,
EMBEDDER_*, RERANKER_*) ; à exécuter EN SSH sur la VM (où ces vars sont
disponibles via le .env du déploiement) ou en local après les avoir exportées.

Usage :
    pytest tests/deploy/test_llm_hub.py -v
    # ou en standalone :
    python tests/deploy/test_llm_hub.py
"""

from __future__ import annotations

import os
import time
from urllib.parse import urlparse

import pytest
import requests


def _env(*names: str, default: str = "") -> str:
    """Renvoie la première variable d'env définie parmi `names`."""
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


BASE_URL = _env("BASE_URL")
API_KEY = _env("API_KEY")
MODEL = _env("MODEL")

EMBEDDER_BASE_URL = _env("EMBEDDER_BASE_URL", default=BASE_URL)
EMBEDDER_API_KEY = _env("EMBEDDER_API_KEY", default=API_KEY)
EMBEDDER_MODEL = _env("EMBEDDER_MODEL_NAME", default="bge-multilingual-gemma2")

RERANKER_BASE_URL = _env("RERANKER_BASE_URL", default=BASE_URL)
RERANKER_API_KEY = _env("RERANKER_API_KEY", default=API_KEY)
RERANKER_MODEL = _env("RERANKER_MODEL", default="bge-multilingual-gemma2")


def _post(url: str, key: str, body: dict, timeout: float = 30.0) -> requests.Response:
    return requests.post(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=timeout,
    )


@pytest.mark.skipif(not BASE_URL or not API_KEY, reason="BASE_URL/API_KEY non définis")
def test_llm_chat_completion():
    """Le LLM principal répond en moins de 5s à un ping."""
    t0 = time.monotonic()
    r = _post(
        f"{BASE_URL.rstrip('/')}/chat/completions",
        API_KEY,
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": "reply with: pong"}],
            "max_tokens": 5,
        },
    )
    elapsed = (time.monotonic() - t0) * 1000
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "choices" in body and body["choices"], "réponse vide"
    assert elapsed < 5000, f"trop lent : {elapsed:.0f} ms"


@pytest.mark.skipif(
    not EMBEDDER_BASE_URL or not EMBEDDER_API_KEY,
    reason="EMBEDDER_BASE_URL/API_KEY non définis",
)
def test_embedder():
    """L'embedder retourne un vecteur non vide."""
    r = _post(
        f"{EMBEDDER_BASE_URL.rstrip('/')}/embeddings",
        EMBEDDER_API_KEY,
        {"model": EMBEDDER_MODEL, "input": "test embedding"},
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    data = body.get("data", [])
    assert data and "embedding" in data[0]
    dim = len(data[0]["embedding"])
    assert dim > 100, f"dimension trop faible : {dim}"


@pytest.mark.skipif(
    not RERANKER_BASE_URL or not RERANKER_API_KEY,
    reason="RERANKER_BASE_URL/API_KEY non définis",
)
def test_reranker_cohere_compat():
    """Le reranker (format Cohere) classe 2 documents."""
    r = _post(
        f"{RERANKER_BASE_URL.rstrip('/')}/rerank",
        RERANKER_API_KEY,
        {
            "model": RERANKER_MODEL,
            "query": "what is RAG",
            "documents": [
                "Retrieval-Augmented Generation combines retrieval with LLMs.",
                "Pizza is a popular Italian dish.",
            ],
            "top_n": 2,
        },
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    results = body.get("results", [])
    assert len(results) == 2
    # Le doc pertinent doit avoir un score plus élevé que le doc non pertinent
    by_idx = {res["index"]: res["relevance_score"] for res in results}
    assert by_idx[0] > by_idx[1], f"reranker incohérent : {by_idx}"


@pytest.mark.skipif(not BASE_URL, reason="BASE_URL non défini")
def test_hub_url_uses_https():
    """Tous les endpoints hub doivent être en HTTPS (pas de leak en clair)."""
    for url, label in [
        (BASE_URL, "BASE_URL"),
        (EMBEDDER_BASE_URL, "EMBEDDER_BASE_URL"),
        (RERANKER_BASE_URL, "RERANKER_BASE_URL"),
    ]:
        if url:
            assert urlparse(url).scheme == "https", f"{label} doit être en https"


# ----------------------------------------------------------------------------
# VLM + Whisper Scaleway (mêmes vars OpenRAG)
# ----------------------------------------------------------------------------

VLM_BASE_URL = _env("VLM_BASE_URL")
VLM_API_KEY = _env("VLM_API_KEY")
VLM_MODEL = _env("VLM_MODEL", default="mistral-small-3.2-24b-instruct-2506")

TRANSCRIBER_BASE_URL = _env("TRANSCRIBER_BASE_URL")
TRANSCRIBER_API_KEY = _env("TRANSCRIBER_API_KEY")
TRANSCRIBER_MODEL = _env("TRANSCRIBER_MODEL_NAME", default="whisper-large-v3")


@pytest.mark.skipif(
    not VLM_BASE_URL or not VLM_API_KEY,
    reason="VLM_BASE_URL/API_KEY non définis (VLM désactivé)",
)
def test_vlm_inline_image():
    """Le VLM Scaleway répond à un message avec image PNG inline (16x16 rouge)."""
    import base64
    import struct
    import zlib

    def _png_solid(w, h, r, g, b):
        sig = b"\x89PNG\r\n\x1a\n"

        def chunk(t, d):
            c = zlib.crc32(t + d) & 0xFFFFFFFF
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", c)

        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        raw = b"".join(b"\x00" + bytes([r, g, b]) * w for _ in range(h))
        idat = zlib.compress(raw)
        return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")

    data_uri = "data:image/png;base64," + base64.b64encode(
        _png_solid(16, 16, 220, 30, 30)
    ).decode()

    r = _post(
        f"{VLM_BASE_URL.rstrip('/')}/chat/completions",
        VLM_API_KEY,
        {
            "model": VLM_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Color in 3 words?"},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            "max_tokens": 20,
        },
        timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    assert content, f"VLM réponse vide : {body}"


@pytest.mark.skipif(
    not TRANSCRIBER_BASE_URL or not TRANSCRIBER_API_KEY,
    reason="TRANSCRIBER_BASE_URL/API_KEY non définis (transcription désactivée)",
)
def test_whisper_silent_wav():
    """Whisper Scaleway transcrit un WAV silencieux 1s sans erreur (le contenu
    'text' peut être quelconque ; on valide juste 200 + format JSON OpenAI)."""
    import struct
    import wave
    from io import BytesIO

    buf = BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(b"\x00\x00" * 16000)
    w.close()
    buf.seek(0)

    r = requests.post(
        f"{TRANSCRIBER_BASE_URL.rstrip('/')}/audio/transcriptions",
        headers={"Authorization": f"Bearer {TRANSCRIBER_API_KEY}"},
        files={"file": ("silent.wav", buf.getvalue(), "audio/wav")},
        data={"model": TRANSCRIBER_MODEL},
        timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "text" in body, f"format inattendu : {body}"


if __name__ == "__main__":
    import sys

    print(f"BASE_URL          = {BASE_URL}")
    print(f"MODEL             = {MODEL}")
    print(f"EMBEDDER_MODEL    = {EMBEDDER_MODEL}")
    print(f"RERANKER_MODEL    = {RERANKER_MODEL}")
    print(f"VLM_MODEL         = {VLM_MODEL or '(disabled)'}")
    print(f"TRANSCRIBER_MODEL = {TRANSCRIBER_MODEL or '(disabled)'}")
    sys.exit(pytest.main([__file__, "-v"]))
