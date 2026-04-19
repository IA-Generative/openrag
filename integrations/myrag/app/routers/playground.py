"""Playground router — quick RAG test for a collection."""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.openrag_client import OpenRAGClient

router = APIRouter(prefix="/api/playground", tags=["Playground"])


class PlaygroundChatRequest(BaseModel):
    question: str
    system_prompt: str = ""
    top_k: int = 5
    temperature: float = 0.1


async def _get_collection_sample(
    client: OpenRAGClient, collection: str, max_files: int = 5
) -> list[dict]:
    """Get a sample of files from the collection to provide context.

    Used as fallback when semantic search returns no results
    (e.g. for vague questions like "de quoi parle cette collection ?").
    """
    try:
        files = await client.list_files(collection)
        if not files:
            return []

        # Take a sample: first, middle, and last files for variety
        sample_indices = set()
        n = len(files)
        # Always include first
        sample_indices.add(0)
        if n > 1:
            sample_indices.add(n - 1)
        if n > 2:
            sample_indices.add(n // 2)
        # Fill up to max_files
        for i in range(min(n, max_files)):
            sample_indices.add(i)

        sample = [files[i] for i in sorted(sample_indices) if i < n]
        return sample[:max_files]
    except Exception:
        return []


@router.post("/{collection}/generate-eval")
async def generate_eval_dataset(collection: str):
    """Auto-generate an evaluation dataset from the collection's content.

    Fetches sample chunks, sends them to the LLM, and asks it to produce
    Q&A pairs in the evaluation JSON format.
    """
    client = OpenRAGClient(timeout=120.0)

    if not await client.health_check():
        raise HTTPException(
            status_code=503,
            detail="OpenRAG n'est pas accessible.",
        )

    # Get all files to understand the collection
    files = await client.list_files(collection)
    if not files:
        raise HTTPException(
            status_code=400,
            detail="La collection est vide. Indexez au moins un document.",
        )

    # Fetch content from a sample of files
    sample_files = files[:15]  # max 15 chunks for context
    content_parts = []
    for f in sample_files:
        fname = f.get("original_filename") or f.get("filename") or "?"
        # Fetch chunk content via extract URL
        try:
            chunk_id = f.get("_id") or ""
            file_id = f.get("file_id", "")
            text = await client.get_file_content(collection, file_id)
            if text:
                content_parts.append(f"### {fname}\n{text[:800]}")
        except Exception:
            content_parts.append(f"### {fname}\n(contenu non disponible)")

    if not content_parts:
        raise HTTPException(
            status_code=400,
            detail="Impossible de lire le contenu des documents indexes.",
        )

    context = "\n\n".join(content_parts)
    model = f"openrag-{collection}"

    prompt = f"""Voici des extraits d'une collection de documents :

{context}

A partir de ces extraits, genere un jeu de test d'evaluation pour un systeme RAG.
Produis exactement 8 questions-reponses variees qui couvrent les differents sujets du contenu.

Reponds UNIQUEMENT avec un JSON valide, sans texte avant ou apres, au format suivant :
{{
  "name": "{collection}-evaluation",
  "description": "Jeu de test genere automatiquement",
  "questions": [
    {{
      "id": "q1",
      "question": "La question ici ?",
      "expected_answer": "La reponse attendue basee sur le contenu.",
      "must_cite": ["mot-cle-1", "mot-cle-2"],
      "tags": ["theme"]
    }}
  ]
}}"""

    try:
        result = await client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erreur LLM: {e}")

    content = ""
    if "choices" in result and result["choices"]:
        content = result["choices"][0].get("message", {}).get("content", "")

    # Try to parse JSON from the response
    try:
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        dataset = json.loads(content.strip())

        # Add out-of-scope questions to test RAG robustness
        out_of_scope = [
            {
                "id": "hors-sujet-1",
                "question": "Quel est l'age du capitaine ?",
                "expected_answer": "",
                "must_cite": [],
                "tags": ["hors-sujet"],
                "out_of_scope": True,
                "note": "Question hors-sujet pour verifier que le RAG ne fabrique pas de reponse.",
            },
            {
                "id": "hors-sujet-2",
                "question": "Quelle est la capitale de la Mongolie ?",
                "expected_answer": "",
                "must_cite": [],
                "tags": ["hors-sujet"],
                "out_of_scope": True,
                "note": "Question hors-sujet pour verifier que le RAG ne fabrique pas de reponse.",
            },
        ]
        dataset.setdefault("questions", []).extend(out_of_scope)

        return dataset
    except (json.JSONDecodeError, IndexError):
        # Return raw text if JSON parsing fails
        return {
            "name": f"{collection}-evaluation",
            "description": "Jeu de test genere automatiquement",
            "questions": [],
            "raw_response": content,
            "error": "Le LLM n'a pas produit un JSON valide. Vous pouvez copier et corriger la reponse ci-dessus.",
        }


@router.post("/{collection}/chat")
async def playground_chat(collection: str, req: PlaygroundChatRequest):
    """Quick RAG chat test against a collection.

    If OpenRAG RAG returns no sources, falls back to manual context injection.
    """
    client = OpenRAGClient(timeout=120.0)

    if not await client.health_check():
        raise HTTPException(
            status_code=503,
            detail="OpenRAG n'est pas accessible. Verifiez que le service est demarre.",
        )

    # Load collection system prompt if not overridden
    system_prompt = req.system_prompt
    if not system_prompt:
        try:
            from app.services.collection_store import get_system_prompt
            prompt = await get_system_prompt(collection)
            if prompt:
                system_prompt = prompt
        except Exception:
            pass

    model = f"openrag-{collection}"

    # Step 1: Try normal RAG via OpenRAG chat completions
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": req.question})

    try:
        result = await client.chat(
            model=model,
            messages=messages,
            temperature=req.temperature,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erreur OpenRAG: {e}")

    # Extract response and sources
    content = ""
    sources = []
    if "choices" in result and result["choices"]:
        content = result["choices"][0].get("message", {}).get("content", "")

    extra_str = result.get("extra", "")
    if extra_str:
        try:
            extra = json.loads(extra_str) if isinstance(extra_str, str) else extra_str
            sources = extra.get("sources", [])
        except (json.JSONDecodeError, AttributeError):
            pass

    # Step 2: If no sources found, fallback — list files and use filenames as context
    fallback_used = False
    if not sources:
        sample_files = await _get_collection_sample(client, collection)
        if sample_files:
            fallback_used = True

            # Build context from file names and metadata
            file_list = []
            for i, f in enumerate(sample_files, 1):
                fname = f.get("original_filename") or f.get("filename") or f"fichier-{i}"
                fsize = f.get("file_size", "")
                file_list.append(f"- {fname} ({fsize})")
                sources.append(f)

            total_files_count = len(await client.list_files(collection))
            files_block = "\n".join(file_list)

            fallback_prompt = (
                system_prompt + "\n\n" if system_prompt else ""
            ) + (
                f"Cette collection '{collection}' contient {total_files_count} documents indexes. "
                f"Voici un echantillon des fichiers :\n{files_block}\n\n"
                "Reponds a la question en te basant sur les noms de fichiers pour decrire le contenu de la collection."
            )

            fallback_messages = [
                {"role": "system", "content": fallback_prompt},
                {"role": "user", "content": req.question},
            ]

            try:
                fallback_result = await client.chat(
                    model=model,
                    messages=fallback_messages,
                    temperature=req.temperature,
                )
                if "choices" in fallback_result and fallback_result["choices"]:
                    content = fallback_result["choices"][0].get("message", {}).get("content", "")
            except Exception:
                pass

    # Format source names
    source_names = []
    for s in sources:
        name = s.get("original_filename") or s.get("filename") or ""
        if name and name not in source_names:
            source_names.append(name)

    return {
        "response": content,
        "sources": sources,
        "source_names": source_names,
        "model": model,
        "system_prompt_used": bool(system_prompt),
        "fallback_used": fallback_used,
    }
