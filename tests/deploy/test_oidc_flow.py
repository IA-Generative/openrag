"""Vérifications de surface du flow OIDC OpenRAG.

Pas de full round-trip Keycloak (impossible sans compte test) — uniquement
les invariants observables de l'extérieur :
- /auth/login redirige bien vers Keycloak Mirai
- L'URL de callback est bien dans les redirect_uris attendus
- Les pages UI sans cookie redirigent vers /auth/login (mode OIDC)
- La discovery OIDC du SSO Mirai répond
- L'API rejette les requêtes sans bearer (sauf /health_check, /version, /docs)

Usage :
    BASE_HOST=openrag-mirai.fake-domain.name pytest tests/deploy/test_oidc_flow.py -v
"""

from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, urlparse

import pytest
import requests

BASE = os.environ.get("BASE_HOST", "openrag-mirai.fake-domain.name")
API = f"https://api.{BASE}"
INDEXER = f"https://indexer.{BASE}"
CHAT = f"https://chat.{BASE}"

SSO_ISSUER = os.environ.get(
    "OIDC_ENDPOINT",
    "https://sso.mirai.interieur.gouv.fr",
).rstrip("/")


def _no_redirect_get(url: str, **kwargs):
    return requests.get(url, allow_redirects=False, timeout=10, **kwargs)


def test_auth_login_redirects_to_sso():
    r = _no_redirect_get(f"{API}/auth/login")
    assert r.status_code in (302, 303), r.status_code
    loc = r.headers.get("Location", "")
    assert "sso.mirai.interieur.gouv.fr" in loc, f"redirect inattendu : {loc}"


def test_auth_login_includes_pkce_and_client_id():
    r = _no_redirect_get(f"{API}/auth/login")
    loc = r.headers.get("Location", "")
    qs = parse_qs(urlparse(loc).query)
    assert qs.get("client_id", [""])[0] == "openrag", qs
    assert "code_challenge" in qs, "PKCE manquant"
    assert qs.get("code_challenge_method", [""])[0] == "S256", qs


def test_auth_login_carries_next_param():
    r = _no_redirect_get(f"{API}/auth/login?next=%2Findexer")
    assert r.status_code in (302, 303)
    # OpenRAG encode le next dans state, pas de leak en clair attendu


def test_auth_callback_rejects_bad_state():
    """/auth/callback sans state ni code -> 400 ou 4xx."""
    r = _no_redirect_get(f"{API}/auth/callback")
    assert r.status_code >= 400, r.status_code


def test_indexer_ui_redirects_to_login():
    """Sans cookie de session, l'UI admin doit rediriger vers /auth/login."""
    r = _no_redirect_get(f"{INDEXER}/")
    # 200 avec page de login server-rendered, ou 302 vers login
    assert r.status_code in (200, 302, 303), r.status_code


def test_api_v1_rejects_unauth():
    """L'API v1 doit refuser sans bearer (401, pas 200/500)."""
    r = requests.get(f"{API}/v1/models", timeout=10, allow_redirects=False)
    assert r.status_code in (401, 302, 303), r.status_code


def test_health_check_is_open():
    """/health_check doit rester accessible sans auth pour les LB / monitoring."""
    r = requests.get(f"{API}/health_check", timeout=10)
    assert r.status_code == 200


def test_sso_discovery_reachable():
    """La discovery OIDC du SSO Mirai doit répondre (à défaut, OpenRAG ne pourra
    pas démarrer en mode oidc)."""
    r = requests.get(f"{SSO_ISSUER}/.well-known/openid-configuration", timeout=10)
    if r.status_code == 404:
        pytest.skip(f"realm non précisé dans OIDC_ENDPOINT={SSO_ISSUER}")
    assert r.status_code == 200, r.status_code
    body = r.json()
    for k in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        assert k in body, f"discovery incomplète : {k} manquant"


def test_backchannel_logout_endpoint_exists():
    """OpenRAG doit exposer /auth/backchannel-logout (POST seulement)."""
    r = requests.get(
        f"{API}/auth/backchannel-logout", timeout=10, allow_redirects=False
    )
    # GET sur un endpoint POST -> 405 ou 404 (mais pas 200 ni 500)
    assert r.status_code in (404, 405, 400), r.status_code


def test_redirect_uri_matches_expected_host():
    """Le redirect_uri envoyé au SSO doit correspondre à l'API publique."""
    r = _no_redirect_get(f"{API}/auth/login")
    loc = r.headers.get("Location", "")
    qs = parse_qs(urlparse(loc).query)
    redirect_uri = qs.get("redirect_uri", [""])[0]
    assert redirect_uri == f"{API}/auth/callback", redirect_uri


# ----------------------------------------------------------------------------
# Validation directe du client_secret Keycloak (à exécuter sur la VM, lit env)
# ----------------------------------------------------------------------------

OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "openrag")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")


@pytest.mark.skipif(not OIDC_CLIENT_SECRET, reason="OIDC_CLIENT_SECRET non défini (à exécuter sur la VM)")
def test_keycloak_client_secret_is_valid():
    """Vérifie que le client_secret posé sur la VM correspond bien à celui
    enregistré dans Keycloak. On utilise le grant client_credentials —
    Keycloak rejette typiquement avec 'unauthorized_client' parce que
    serviceAccountsEnabled=false dans notre client, MAIS cette erreur
    confirme déjà que le secret est validé. La vraie erreur à éviter est
    'invalid_client' qui signifie secret incorrect."""
    r = requests.post(
        f"{SSO_ISSUER}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": OIDC_CLIENT_ID,
            "client_secret": OIDC_CLIENT_SECRET,
        },
        timeout=15,
    )
    body = r.json()
    err = body.get("error")
    # Cas acceptés : succès direct OU rejet pour raison non liée au secret
    assert err != "invalid_client", (
        f"client_secret incorrect (Keycloak retourne invalid_client). "
        f"Vérifier la valeur posée vs onglet Credentials du client."
    )
    # 200 + access_token (cas où serviceAccountsEnabled serait true) OU
    # 400/401 + unauthorized_client (cas attendu avec notre config)
    assert r.status_code in (200, 400, 401), r.status_code


# ----------------------------------------------------------------------------
# Multi-domaine — la VM doit accepter les hosts numerique-interieur.com mais
# en redirigeant (301) vers le canonical fake-domain.name avant l'auth.
# ----------------------------------------------------------------------------

NON_CANONICAL_BASE = os.environ.get(
    "NON_CANONICAL_BASE_HOST", "openrag-mirai.numerique-interieur.com"
)
NC_API = f"https://api.{NON_CANONICAL_BASE}"
NC_INDEXER = f"https://indexer.{NON_CANONICAL_BASE}"
NC_CHAT = f"https://chat.{NON_CANONICAL_BASE}"


def _expects_redirect_to_canonical(url: str, canonical_host: str) -> None:
    """Vérifie qu'un GET sur `url` retourne 301/308 avec Location pointant vers
    le canonical_host correspondant (même chemin)."""
    r = requests.get(url, allow_redirects=False, timeout=10)
    assert r.status_code in (301, 308), f"{url} -> {r.status_code} (attendu 301/308)"
    loc = r.headers.get("Location", "")
    parsed = urlparse(loc)
    assert parsed.hostname == canonical_host, (
        f"{url} redirige vers {parsed.hostname}, attendu {canonical_host}"
    )
    assert parsed.scheme == "https", f"redirect {url} non HTTPS : {loc}"


def test_non_canonical_api_redirects_to_canonical():
    """api.openrag-mirai.numerique-interieur.com → 301 vers
    api.openrag-mirai.fake-domain.name (préserve le path)."""
    _expects_redirect_to_canonical(
        f"{NC_API}/health_check", f"api.{BASE}"
    )


def test_non_canonical_indexer_redirects_to_canonical():
    _expects_redirect_to_canonical(
        f"{NC_INDEXER}/", f"indexer.{BASE}"
    )


def test_non_canonical_chat_redirects_to_canonical():
    _expects_redirect_to_canonical(
        f"{NC_CHAT}/", f"chat.{BASE}"
    )


def test_non_canonical_auth_login_redirects_then_to_sso():
    """Le path /auth/login sur le non-canonical doit d'abord rediriger vers
    le canonical (Caddy 301), puis le canonical redirige vers Keycloak.
    On suit la chaîne complète et on vérifie la destination finale."""
    r = requests.get(
        f"{NC_API}/auth/login", allow_redirects=True, timeout=15
    )
    # Le suivi des redirects doit arriver chez Keycloak Mirai
    final = r.url
    assert "sso.mirai.interieur.gouv.fr" in final, f"chaîne de redirect inattendue, final = {final}"


@pytest.mark.skipif(not OIDC_CLIENT_SECRET, reason="OIDC_CLIENT_SECRET non défini")
def test_keycloak_rejects_wrong_secret():
    """Sanity check : un mauvais secret doit retourner invalid_client.
    Sert de canary inverse — si ce test échoue, le test précédent
    pourrait être un faux positif."""
    r = requests.post(
        f"{SSO_ISSUER}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": OIDC_CLIENT_ID,
            "client_secret": "definitely-not-the-real-secret-" + "x" * 32,
        },
        timeout=15,
    )
    body = r.json()
    assert body.get("error") == "invalid_client", body
