"""MyRAG chunker — intelligent document splitting strategies."""

import re
from typing import Literal

# --- Regex patterns ---

ARTICLE_HEADER_RE = re.compile(
    r"^Article\s+([LRD]\d+(?:-\d+)*)\s*$", re.MULTILINE
)
ARTICLE_REF_RE = re.compile(
    r"\b[Ll](?:'article|'article)\s+([LRD])\.\s?(\d+(?:-\d+)*)\b"
    r"|\b([LRD])\.\s?(\d+(?:-\d+)*)\b"
)
LIVRE_RE = re.compile(r"Livre\s+([IVXLCDM]+)", re.IGNORECASE)
TITRE_RE = re.compile(r"Titre\s+([IVXLCDM]+(?:\s*\w*)?)", re.IGNORECASE)
CHAPITRE_RE = re.compile(r"Chapitre\s+([IVXLCDM]+(?:\s*\w*)?)", re.IGNORECASE)
SECTION_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
FAQ_HEADER_RE = re.compile(r"^#{1,4}\s+(.+\?)\s*$", re.MULTILINE)


Strategy = Literal["article", "section", "qr", "length", "auto"]

# Sensitivity levels for access control filtering
# Based on French classification convention + platform capability
Sensitivity = Literal["public", "internal", "restricted", "confidential", "secret"]

SENSITIVITY_LEVELS = {
    "public": 0,       # Accessible a tous (ex: textes de loi publies au JO)
    "internal": 1,     # Usage interne organisation (ex: notes de service)
    "restricted": 2,   # Diffusion restreinte (ex: procedures internes)
    "confidential": 3, # Confidentiel (ex: donnees personnelles, avis juridiques)
    "secret": 4,       # Secret (ex: defense nationale — hors scope plateforme)
}


def detect_strategy(text: str) -> Strategy:
    """Detect the best chunking strategy for the given text."""
    article_count = len(ARTICLE_HEADER_RE.findall(text))
    if article_count >= 2:
        return "article"

    faq_count = len(FAQ_HEADER_RE.findall(text))
    if faq_count >= 2:
        return "qr"

    section_count = len(SECTION_HEADER_RE.findall(text))
    if section_count >= 2:
        return "section"

    return "length"


def _extract_references(text: str) -> list[str]:
    """Extract article references (e.g., L. 110-1) from text."""
    refs = set()
    for match in ARTICLE_REF_RE.finditer(text):
        prefix = match.group(1) or match.group(3)
        number = match.group(2) or match.group(4)
        if prefix and number:
            refs.add(f"{prefix}{number}")
    return sorted(refs)


def _track_hierarchy(text_before: str) -> dict:
    """Extract the current Livre/Titre/Chapitre from preceding text."""
    hierarchy = {"livre": "", "titre": "", "chapitre": "", "section": ""}

    livres = LIVRE_RE.findall(text_before)
    if livres:
        hierarchy["livre"] = livres[-1].strip()

    titres = TITRE_RE.findall(text_before)
    if titres:
        hierarchy["titre"] = titres[-1].strip()

    chapitres = CHAPITRE_RE.findall(text_before)
    if chapitres:
        hierarchy["chapitre"] = chapitres[-1].strip()

    return hierarchy


def chunk_by_article(text: str, sensitivity: Sensitivity = "public") -> list[dict]:
    """Split a legal code by article. Each article becomes one chunk."""
    if not text.strip():
        return []

    matches = list(ARTICLE_HEADER_RE.finditer(text))
    if not matches:
        return []

    chunks = []
    for i, match in enumerate(matches):
        article_id = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        raw_content = text[start:end].strip()
        text_before = text[:match.start()]
        hierarchy = _track_hierarchy(text_before)
        references = _extract_references(raw_content)

        # Remove self-references
        references = [r for r in references if r != article_id]

        # Prefix content with article ID and hierarchy for LLM citation
        header_parts = [f"Article {article_id}"]
        if hierarchy["livre"]:
            header_parts.append(f"Livre {hierarchy['livre']}")
        if hierarchy["titre"]:
            header_parts.append(f"Titre {hierarchy['titre']}")
        if hierarchy["chapitre"]:
            header_parts.append(f"Chapitre {hierarchy['chapitre']}")
        header = " — ".join(header_parts)

        content = f"{header}\n\n{raw_content}"

        # Build parent path for hierarchy navigation
        parent_path = "/".join(
            p for p in [
                f"Livre-{hierarchy['livre']}" if hierarchy["livre"] else "",
                f"Titre-{hierarchy['titre']}" if hierarchy["titre"] else "",
                f"Chapitre-{hierarchy['chapitre']}" if hierarchy["chapitre"] else "",
            ] if p
        )

        chunks.append({
            "content": content,
            "filename": f"Article-{article_id}.md",
            "metadata": {
                "article": article_id,
                "page": i + 1,
                "livre": hierarchy["livre"],
                "titre": hierarchy["titre"],
                "chapitre": hierarchy["chapitre"],
                "section": hierarchy["section"],
                "parent_path": parent_path,
                "references": references,
                "referenced_by": [],  # populated in post-processing (graph build)
                "graph_ready": False,  # set to True after graph build
                "sensitivity": sensitivity,
            },
        })

    return chunks


def chunk_by_section(text: str, sensitivity: Sensitivity = "internal") -> list[dict]:
    """Split a document by markdown headers (##, ###)."""
    if not text.strip():
        return []

    matches = list(SECTION_HEADER_RE.finditer(text))
    if not matches:
        return [{"content": text.strip(), "filename": "section-1.md",
                 "metadata": {"section_title": "", "level": 1, "page": 1, "sensitivity": sensitivity}}]

    chunks = []
    for i, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        content = text[start:end].strip()
        if not content:
            continue

        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
        chunks.append({
            "content": content,
            "filename": f"section-{slug}.md",
            "metadata": {
                "section_title": title,
                "level": level,
                "page": i + 1,
                "sensitivity": sensitivity,
            },
        })

    return chunks


def chunk_by_qr(text: str, sensitivity: Sensitivity = "public") -> list[dict]:
    """Split a FAQ document by question/answer pairs."""
    if not text.strip():
        return []

    matches = list(FAQ_HEADER_RE.finditer(text))
    if not matches:
        return []

    chunks = []
    for i, match in enumerate(matches):
        question = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        answer = text[start:end].strip()
        slug = re.sub(r"[^a-z0-9]+", "-", question.lower())[:40].strip("-")

        chunks.append({
            "content": answer,
            "filename": f"QR-{i + 1}-{slug}.md",
            "metadata": {
                "question": question,
                "page": i + 1,
                "sensitivity": sensitivity,
            },
        })

    return chunks


def chunk_by_length(text: str, max_chars: int = 512, overlap: int = 50, sensitivity: Sensitivity = "internal") -> list[dict]:
    """Split text into fixed-length chunks with overlap."""
    if not text.strip():
        return []

    chunks = []
    pos = 0
    page = 1

    while pos < len(text):
        end = min(pos + max_chars, len(text))

        # Try to break at a sentence boundary
        if end < len(text):
            last_period = text.rfind(".", pos, end)
            last_newline = text.rfind("\n", pos, end)
            break_at = max(last_period, last_newline)
            if break_at > pos + max_chars // 2:
                end = break_at + 1

        chunk_text = text[pos:end].strip()
        if chunk_text:
            chunks.append({
                "content": chunk_text,
                "filename": f"chunk-{page}.md",
                "metadata": {"page": page, "sensitivity": sensitivity},
            })
            page += 1

        pos = max(pos + 1, end - overlap)

    return chunks


def chunk_document(
    text: str,
    strategy: Strategy = "auto",
    max_chars: int = 512,
    overlap: int = 50,
    sensitivity: Sensitivity = "public",
) -> list[dict]:
    """Chunk a document using the specified or auto-detected strategy.

    The sensitivity level is applied to ALL chunks produced and stored in metadata.
    It can be modified later per-chunk via the collection admin API.

    Levels: public, internal, restricted, confidential, secret
    """
    if strategy == "auto":
        strategy = detect_strategy(text)

    if strategy == "article":
        return chunk_by_article(text, sensitivity=sensitivity)
    elif strategy == "section":
        return chunk_by_section(text, sensitivity=sensitivity)
    elif strategy == "qr":
        return chunk_by_qr(text, sensitivity=sensitivity)
    else:
        return chunk_by_length(text, max_chars=max_chars, overlap=overlap, sensitivity=sensitivity)
