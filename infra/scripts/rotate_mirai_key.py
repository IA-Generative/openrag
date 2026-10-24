#!/usr/bin/env python3
"""Remplace la clé Mirai d'OpenRAG, dans le .env ET dans le registre des modèles.

Depuis la 2.2, la clé vit à deux endroits :

* le ``.env`` (API_KEY, EMBEDDER_API_KEY, RERANKER_API_KEY, …) : ne sert plus
  qu'au premier amorçage et de repli, car ``MODEL_ENDPOINT_SYNC_ON_BOOT`` est
  faux par défaut ;
* les fiches ``model_endpoints`` en base (``extra.api_key``) : c'est ce que
  l'application utilise réellement. Elles se changent par l'API d'admin
  (``PUT /model-endpoints/{type}/{nom}``), qui recharge le registre à chaud.

Le script ne touche qu'aux fiches des types demandés (``--types``) qui pointent
sur la passerelle Mirai et portent l'ANCIENNE clé, et aux variables du .env qui
leur correspondent. Les autres gardent leur clé : c'est ce qui permet de donner
un jeton au LLM et à l'embedding sans toucher au reclasseur. Les points d'accès
Scaleway (VLM, transcription, contextualisation de secours) restent intacts.

À lancer sur la VM, en root :

    python3 rotate_mirai_key.py --types llm,embedder --dry-run   # montre le plan
    python3 rotate_mirai_key.py --types llm,embedder             # applique (confirmation)
    python3 rotate_mirai_key.py --types llm,embedder --restart   # + recrée le conteneur

La nouvelle clé est demandée sans écho (ou lue dans MIRAI_NEW_KEY). Aucune clé
n'est jamais affichée en clair.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ENV_FILE = "/opt/openrag/infra/compose/.env"
DEFAULT_API = "http://localhost:8080"
# Domaines qui identifient la passerelle Mirai (ancien et nouveau nom).
DEFAULT_HOST_SUFFIXES = ("api.ai.numerique-interieur.com", "mirai.interieur.gouv.fr")

# Variable de clé -> (variable d'URL qui dit à qui elle s'adresse, type de fiche).
KEY_URL_PAIRS = {
    "API_KEY": ("BASE_URL", "llm"),
    "EMBEDDER_API_KEY": ("EMBEDDER_BASE_URL", "embedder"),
    "RERANKER_API_KEY": ("RERANKER_BASE_URL", "reranker"),
    "VLM_API_KEY": ("VLM_BASE_URL", "vlm"),
    "TRANSCRIBER_API_KEY": ("TRANSCRIBER_BASE_URL", "stt"),
    "OPENAI_LOADER_API_KEY": ("OPENAI_LOADER_BASE_URL", "vlm"),
}
ALL_TYPES = ("llm", "embedder", "reranker", "vlm", "stt")

# Appel minimal par type : prouve que la clé ouvre CE service (/v1/models est public).
KEY_TESTS = {
    "llm": (
        "chat/completions",
        lambda m: {"model": m, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1},
    ),
    "embedder": ("embeddings", lambda m: {"model": m, "input": "test"}),
    "reranker": ("rerank", lambda m: {"model": m, "query": "test", "documents": ["test"]}),
}


def mask(secret: str | None) -> str:
    if not secret:
        return "(vide)"
    return f"{secret[:4]}…({len(secret)} car.)"


def die(msg: str) -> None:
    print(f"ERREUR : {msg}", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------- .env


def parse_env_line(line: str) -> tuple[str, str, str] | None:
    """Retourne (nom, valeur, guillemet) pour une ligne ``NOM=valeur``, sinon None."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    name, _, value = stripped.partition("=")
    name = name.removeprefix("export ").strip()
    value = value.strip()
    quote = ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        quote, value = value[0], value[1:-1]
    return name, value, quote


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        parsed = parse_env_line(line)
        if parsed:
            values[parsed[0]] = parsed[1]
    return values


def is_mirai_url(url: str | None, host_suffixes: list[str]) -> bool:
    if not url:
        return False
    host = urllib.parse.urlparse(url).hostname or ""
    return any(host == suffix or host.endswith("." + suffix) for suffix in host_suffixes)


def rewrite_env(path: Path, env_vars: set[str], old_keys: set[str], new_key: str) -> tuple[str, list[str]]:
    """Texte du .env où les variables *env_vars* portant une ancienne clé prennent la nouvelle."""
    out, changed = [], []
    for line in path.read_text().splitlines(keepends=True):
        parsed = parse_env_line(line)
        if parsed and parsed[0] in env_vars and parsed[1] in old_keys:
            name, _, quote = parsed
            eol = "\n" if line.endswith("\n") else ""
            out.append(f"{name}={quote}{new_key}{quote}{eol}")
            changed.append(name)
        else:
            out.append(line)
    return "".join(out), changed


def write_atomically(path: Path, text: str) -> None:
    st = path.stat()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".env.tmp-")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.chmod(tmp, st.st_mode & 0o777)
        os.chown(tmp, st.st_uid, st.st_gid)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------- HTTP


def http(method: str, url: str, token: str | None, body: dict | None = None, timeout: float = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw.decode(errors="replace")[:300]
        return exc.code, payload


def test_new_key(key: str, targets: list[dict]) -> None:
    """Teste la clé sur l'URL et le modèle de chaque fiche visée, avant toute écriture."""
    for ep in targets:
        label = f"{ep['model_type']}/{ep['name']}"
        if ep["model_type"] not in KEY_TESTS:
            print(f"  ? {label} : pas de test prévu, non vérifié")
            continue
        route, body = KEY_TESTS[ep["model_type"]]
        model = ep.get("model_name") or ep["name"]
        url = f"{ep['endpoint'].rstrip('/')}/{route}"
        payload_in = body(model)
        if ep["model_type"] == "reranker" and (ep.get("extra") or {}).get("implementation") == "tei":
            # TEI : champ ``texts`` au lieu de ``documents`` (cf. TEIReranker).
            payload_in = {"query": "test", "texts": ["test"]}
        status, payload = http("POST", url, key, payload_in)
        if status == 200:
            print(f"  ✓ {label} : nouvelle clé acceptée ({url}, modèle {model})")
        elif status == 429:
            print(f"  ⚠ {label} : 429, clé reconnue mais déjà au plafond de son quota — on continue")
        else:
            die(
                f"{label} : {url} refuse la nouvelle clé ({status}) : {payload}.\n"
                "Rien n'a été modifié. Retirer ce type de --types s'il doit garder sa clé actuelle."
            )


# ---------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    ap.add_argument("--api", default=DEFAULT_API, help="URL de l'API OpenRAG vue de la VM")
    ap.add_argument(
        "--host-suffix",
        action="append",
        help=f"domaine qui identifie Mirai (répétable ; défaut : {', '.join(DEFAULT_HOST_SUFFIXES)})",
    )
    ap.add_argument("--dry-run", action="store_true", help="ne rien écrire, montrer le plan")
    ap.add_argument("--yes", action="store_true", help="ne pas demander de confirmation")
    ap.add_argument(
        "--types",
        required=True,
        help=f"types de fiches à basculer, séparés par des virgules, parmi {','.join(ALL_TYPES)}"
        " (ex. llm,embedder) ; les autres gardent leur clé",
    )
    ap.add_argument("--skip-test", action="store_true", help="ne pas tester la nouvelle clé avant")
    ap.add_argument(
        "--restart",
        action="store_true",
        help="recréer le conteneur openrag ensuite (relit le .env, vide les clients des workers Ray)",
    )
    args = ap.parse_args()
    types = [t.strip() for t in args.types.split(",") if t.strip()]
    unknown = [t for t in types if t not in ALL_TYPES]
    if not types or unknown:
        die(f"--types invalide ({', '.join(unknown) or 'vide'}) ; choisir parmi {', '.join(ALL_TYPES)}")
    suffixes = args.host_suffix or list(DEFAULT_HOST_SUFFIXES)

    env_path = Path(args.env_file)
    if not env_path.is_file():
        die(f"{env_path} introuvable (option --env-file)")
    env = read_env(env_path)
    admin_token = env.get("AUTH_TOKEN")
    if not admin_token:
        die("AUTH_TOKEN absent du .env : impossible d'appeler l'API d'admin")

    # 1. Ancienne clé : celle des variables des types visés dont l'URL associée est Mirai.
    selected_vars = {
        key_var
        for key_var, (url_var, model_type) in KEY_URL_PAIRS.items()
        if model_type in types
        and env.get(key_var) not in (None, "", "EMPTY")
        and is_mirai_url(env.get(url_var), suffixes)
    }
    old_keys = {env[key_var] for key_var in selected_vars}
    print(f"Fichier : {env_path}")
    print(f"Types à basculer : {', '.join(types)} — les autres gardent leur clé")
    if old_keys:
        print(f"Ancienne(s) clé(s) Mirai trouvée(s) dans le .env : {', '.join(mask(k) for k in old_keys)}")
    else:
        print("Aucune clé Mirai reconnue dans le .env : les fiches seront choisies d'après leur URL seule.")

    # 2. Fiches en base candidates : types visés, sur Mirai, portant l'ancienne clé.
    api = args.api.rstrip("/")
    status, endpoints = http("GET", f"{api}/model-endpoints/", admin_token)
    if status != 200:
        die(f"GET /model-endpoints/ → {status} : {endpoints}")
    candidates, notes = [], []
    for ep in endpoints:
        label = f"{ep['model_type']}/{ep['name']}"
        if not is_mirai_url(ep.get("endpoint"), suffixes):
            notes.append(f"  - {label:40} ignorée (hors Mirai : {urllib.parse.urlparse(ep['endpoint']).hostname})")
            continue
        if ep["model_type"] not in types:
            notes.append(f"  = {label:40} garde sa clé (type hors --types)")
            continue
        current = None
        if ep.get("has_api_key"):
            st, revealed = http(
                "POST", f"{api}/model-endpoints/{ep['model_type']}/{ep['name']}/reveal-api-key", admin_token
            )
            current = (revealed or {}).get("api_key") if st == 200 else None
        if old_keys and current not in old_keys:
            notes.append(f"  ! {label:40} ignorée : clé {mask(current)} ≠ ancienne clé du .env (à vérifier)")
            continue
        candidates.append((ep, current))

    # 3. Nouvelle clé, testée sur l'URL et le modèle de chaque fiche à basculer.
    new_key = os.environ.get("MIRAI_NEW_KEY") or getpass.getpass("Nouvelle clé Mirai (rien ne s'affiche) : ")
    new_key = new_key.strip()
    if not new_key:
        die("clé vide")
    if new_key in old_keys:
        die("la nouvelle clé est identique à l'ancienne")
    print(f"Nouvelle clé : {mask(new_key)}")
    targets = [ep for ep, current in candidates if current != new_key]
    if not args.skip_test:
        test_new_key(new_key, targets)

    # 4. Plan pour le .env.
    new_env_text, env_vars = rewrite_env(env_path, selected_vars, old_keys, new_key)
    kept = sorted(name for name, value in env.items() if value in old_keys and name not in env_vars)
    print(f"\n.env — variables à changer : {', '.join(env_vars) or 'aucune'}")
    if kept:
        print(f".env — gardent l'ancienne clé (hors --types) : {', '.join(kept)}")

    # 5. Plan pour les fiches.
    print("\nFiches model_endpoints :")
    for ep, current in candidates:
        label = f"{ep['model_type']}/{ep['name']}"
        if current == new_key:
            print(f"  - {label:40} déjà à jour")
        else:
            print(f"  → {label:40} {mask(current)} → {mask(new_key)}")
    print("\n".join(notes))

    if not env_vars and not targets:
        print("\nRien à faire.")
        return
    if args.dry_run:
        print("\n--dry-run : aucune modification.")
        return
    if not args.yes and input("\nAppliquer ? [o/N] ").strip().lower() not in ("o", "oui", "y", "yes"):
        print("Abandon, rien n'a été modifié.")
        return

    # 6. .env : sauvegarde puis réécriture atomique.
    if env_vars:
        backup = env_path.with_name(f"{env_path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(env_path, backup)
        write_atomically(env_path, new_env_text)
        print(f"\n✓ .env mis à jour (sauvegarde : {backup})")

    # 7. Fiches : on renvoie l'``extra`` complet (masqué), seule api_key change ;
    #    le serveur conserve les autres secrets masqués (preserve_existing_secrets).
    failures = 0
    for ep in targets:
        label = f"{ep['model_type']}/{ep['name']}"
        extra = dict(ep.get("extra") or {})
        extra["api_key"] = new_key
        st, payload = http(
            "PUT", f"{api}/model-endpoints/{ep['model_type']}/{ep['name']}", admin_token, {"extra": extra}
        )
        if st == 200 and payload.get("has_api_key"):
            print(f"✓ {label} mise à jour")
        else:
            failures += 1
            print(f"✗ {label} : {st} {payload}")

    # 8. Redémarrage facultatif.
    if args.restart:
        compose_dir = env_path.parent
        running = subprocess.run(
            ["docker", "compose", "-p", "openrag", "ps", "--services", "--status", "running"],
            cwd=compose_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        services = [s for s in ("openrag", "openrag-cpu") if s in running]
        if not services:
            print("! aucun service openrag en marche trouvé, pas de redémarrage")
        else:
            print(f"\nRecréation de {', '.join(services)} (courte interruption)…")
            subprocess.run(
                ["docker", "compose", "-p", "openrag", "up", "-d", "--no-deps", "--force-recreate", *services],
                cwd=compose_dir,
                check=True,
            )
            print("✓ conteneur recréé — attendre que /health_check réponde 200")
    else:
        print(
            "\nL'API utilise la nouvelle clé tout de suite ; les workers d'indexation relisent le registre"
            " sous 60 s.\nPour être certain que plus rien ne garde l'ancienne (clients en cache, repli .env),"
            " relancer avec --restart\nou : cd "
            f"{env_path.parent} && docker compose -p openrag up -d --no-deps --force-recreate openrag"
        )
    if failures:
        sys.exit(2)


if __name__ == "__main__":
    main()
