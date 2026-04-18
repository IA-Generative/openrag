"""Tests for MyRAG chunker strategies (TDD - written before implementation)."""

import pytest

from app.services.chunker import (
    chunk_by_article,
    chunk_by_section,
    chunk_by_qr,
    chunk_by_length,
    detect_strategy,
    chunk_document,
)


# --- Sample documents ---

CESEDA_SAMPLE = """# CESEDA

Partie legislative

Livre I : DISPOSITIONS GENERALES

Titre I : CHAMP D'APPLICATION

Article L110-1

Le present code regit, sous reserve du droit de l'Union europeenne et des conventions internationales,
l'entree, le sejour et l'eloignement des etrangers en France ainsi que l'exercice du droit d'asile.

Article L110-2

Le present code est applicable sur l'ensemble du territoire de la Republique.

Article L110-3

Sont considerees comme etrangers au sens du present code les personnes qui n'ont pas la nationalite
francaise, soit qu'elles aient une nationalite etrangere, soit qu'elles n'aient pas de nationalite.

Titre II : ADMINISTRATIONS EN CHARGE

Chapitre Ier : ETABLISSEMENTS PUBLICS

Article L121-1

L'Office francais de l'immigration et de l'integration est un etablissement public administratif
de l'Etat charge du service public de l'accueil. Il participe aux actions relatives a l'entree
des etrangers selon les conditions prevues a l'article L. 110-1.
"""

REPORT_SAMPLE = """# Rapport annuel 2025

## Introduction

Ce rapport presente les activites de l'annee 2025.

## Chapitre 1 : Bilan

Le bilan de l'annee est positif avec une augmentation de 15%.

### 1.1 Activites principales

Les activites principales incluent le traitement des dossiers.

## Chapitre 2 : Perspectives

Les perspectives pour 2026 sont encourageantes.
"""

FAQ_SAMPLE = """### Quels documents fournir pour un titre de sejour ?

Vous devez fournir un passeport valide, un justificatif de domicile et des photos d'identite.

### Quel est le delai de traitement ?

Le delai moyen est de 3 mois a compter du depot du dossier complet.

### Comment renouveler mon titre ?

Le renouvellement doit etre demande 2 mois avant l'expiration du titre en cours.
"""

PLAIN_TEXT = """Ceci est un texte brut sans structure particuliere. Il contient plusieurs paragraphes
qui doivent etre decoupes par longueur fixe avec un overlap configurable. Le texte peut etre
assez long et contenir des informations variees sur differents sujets sans marqueurs de section."""


# --- Tests: detection de strategie ---

class TestDetectStrategy:
    def test_detects_legal_code(self):
        assert detect_strategy(CESEDA_SAMPLE) == "article"

    def test_detects_report(self):
        assert detect_strategy(REPORT_SAMPLE) == "section"

    def test_detects_faq(self):
        assert detect_strategy(FAQ_SAMPLE) == "qr"

    def test_detects_plain_text(self):
        assert detect_strategy(PLAIN_TEXT) == "length"


# --- Tests: decoupage par article ---

class TestChunkByArticle:
    def test_extracts_articles(self):
        chunks = chunk_by_article(CESEDA_SAMPLE)
        articles = [c["metadata"]["article"] for c in chunks]
        assert "L110-1" in articles
        assert "L110-2" in articles
        assert "L110-3" in articles
        assert "L121-1" in articles

    def test_chunk_count(self):
        chunks = chunk_by_article(CESEDA_SAMPLE)
        assert len(chunks) == 4

    def test_chunk_has_content(self):
        chunks = chunk_by_article(CESEDA_SAMPLE)
        l110_1 = next(c for c in chunks if c["metadata"]["article"] == "L110-1")
        assert "l'entree, le sejour" in l110_1["content"]

    def test_chunk_has_hierarchy(self):
        chunks = chunk_by_article(CESEDA_SAMPLE)
        l110_1 = next(c for c in chunks if c["metadata"]["article"] == "L110-1")
        assert l110_1["metadata"]["livre"] == "I"
        assert l110_1["metadata"]["titre"] == "I"

    def test_chunk_has_filename(self):
        chunks = chunk_by_article(CESEDA_SAMPLE)
        l110_1 = next(c for c in chunks if c["metadata"]["article"] == "L110-1")
        assert l110_1["filename"] == "Article-L110-1.md"

    def test_extracts_references(self):
        chunks = chunk_by_article(CESEDA_SAMPLE)
        l121_1 = next(c for c in chunks if c["metadata"]["article"] == "L121-1")
        assert "L110-1" in l121_1["metadata"]["references"]

    def test_different_titre(self):
        chunks = chunk_by_article(CESEDA_SAMPLE)
        l121_1 = next(c for c in chunks if c["metadata"]["article"] == "L121-1")
        assert l121_1["metadata"]["titre"] == "II"
        assert l121_1["metadata"]["chapitre"] == "Ier"

    def test_empty_document(self):
        chunks = chunk_by_article("")
        assert chunks == []

    def test_no_articles(self):
        chunks = chunk_by_article("Just some text without articles.")
        assert chunks == []


# --- Tests: decoupage par section ---

class TestChunkBySection:
    def test_extracts_sections(self):
        chunks = chunk_by_section(REPORT_SAMPLE)
        assert len(chunks) >= 3

    def test_section_has_title(self):
        chunks = chunk_by_section(REPORT_SAMPLE)
        titles = [c["metadata"].get("section_title", "") for c in chunks]
        assert any("Introduction" in t for t in titles)
        assert any("Bilan" in t for t in titles)

    def test_section_has_content(self):
        chunks = chunk_by_section(REPORT_SAMPLE)
        intro = next(c for c in chunks if "Introduction" in c["metadata"].get("section_title", ""))
        assert "activites de l'annee" in intro["content"]

    def test_section_has_level(self):
        chunks = chunk_by_section(REPORT_SAMPLE)
        for c in chunks:
            assert "level" in c["metadata"]
            assert c["metadata"]["level"] in (1, 2, 3)


# --- Tests: decoupage par Q&R ---

class TestChunkByQR:
    def test_extracts_qr_pairs(self):
        chunks = chunk_by_qr(FAQ_SAMPLE)
        assert len(chunks) == 3

    def test_qr_has_question(self):
        chunks = chunk_by_qr(FAQ_SAMPLE)
        assert any("documents fournir" in c["metadata"].get("question", "") for c in chunks)

    def test_qr_has_answer(self):
        chunks = chunk_by_qr(FAQ_SAMPLE)
        first = chunks[0]
        assert "passeport" in first["content"]

    def test_qr_filename(self):
        chunks = chunk_by_qr(FAQ_SAMPLE)
        for c in chunks:
            assert c["filename"].startswith("QR-")
            assert c["filename"].endswith(".md")


# --- Tests: decoupage par longueur ---

class TestChunkByLength:
    def test_chunks_have_max_length(self):
        chunks = chunk_by_length(PLAIN_TEXT, max_chars=100, overlap=20)
        for c in chunks:
            assert len(c["content"]) <= 120  # max + overlap tolerance

    def test_chunks_have_overlap(self):
        chunks = chunk_by_length(PLAIN_TEXT, max_chars=100, overlap=20)
        if len(chunks) >= 2:
            end_first = chunks[0]["content"][-20:]
            start_second = chunks[1]["content"][:20]
            # Some overlap should exist
            assert len(set(end_first.split()) & set(start_second.split())) > 0

    def test_empty_document(self):
        chunks = chunk_by_length("", max_chars=100, overlap=20)
        assert chunks == []

    def test_chunk_has_page_number(self):
        chunks = chunk_by_length(PLAIN_TEXT, max_chars=100, overlap=20)
        for i, c in enumerate(chunks):
            assert c["metadata"]["page"] == i + 1


# --- Tests: chunk_document (auto-detection) ---

class TestChunkDocument:
    def test_auto_detects_and_chunks_legal(self):
        chunks = chunk_document(CESEDA_SAMPLE, strategy="auto")
        articles = [c["metadata"].get("article") for c in chunks if c["metadata"].get("article")]
        assert "L110-1" in articles

    def test_forced_strategy(self):
        chunks = chunk_document(CESEDA_SAMPLE, strategy="length", max_chars=200)
        # Should not extract articles, just length-based chunks
        assert all("article" not in c["metadata"] for c in chunks)

    def test_returns_list(self):
        chunks = chunk_document(FAQ_SAMPLE, strategy="auto")
        assert isinstance(chunks, list)
        assert len(chunks) > 0
