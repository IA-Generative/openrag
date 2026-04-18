"""Tests for graph builder (TDD)."""

import json
import pytest

from app.services.graph_builder import (
    GraphBuilder,
    extract_references,
    build_graph_from_chunks,
)


SAMPLE_CHUNKS = [
    {
        "content": "Article L110-1 — Livre I, Titre I\n\nLe present code regit l'entree et le sejour.",
        "filename": "Article-L110-1.md",
        "metadata": {
            "article": "L110-1",
            "livre": "I",
            "titre": "I",
            "chapitre": "",
            "references": [],
            "parent_path": "Livre-I/Titre-I",
        },
    },
    {
        "content": "Article L421-1 — Livre IV, Titre II, Chapitre III\n\nL'etranger marie avec un ressortissant francais se voit delivrer une carte selon les conditions prevues a l'article L. 110-1 et L. 321-4.",
        "filename": "Article-L421-1.md",
        "metadata": {
            "article": "L421-1",
            "livre": "IV",
            "titre": "II",
            "chapitre": "III",
            "references": ["L110-1", "L321-4"],
            "parent_path": "Livre-IV/Titre-II/Chapitre-III",
        },
    },
    {
        "content": "Article L321-4 — Livre III, Titre II\n\nConditions de delivrance. Voir aussi article L. 421-1.",
        "filename": "Article-L321-4.md",
        "metadata": {
            "article": "L321-4",
            "livre": "III",
            "titre": "II",
            "chapitre": "",
            "references": ["L421-1"],
            "parent_path": "Livre-III/Titre-II",
        },
    },
]


class TestExtractReferences:
    def test_extract_basic(self):
        refs = extract_references("conditions prevues a l'article L. 110-1")
        assert "L110-1" in refs

    def test_extract_multiple(self):
        refs = extract_references("articles L. 421-1 et R. 311-3")
        assert "L421-1" in refs
        assert "R311-3" in refs

    def test_extract_none(self):
        refs = extract_references("pas de reference ici")
        assert refs == []

    def test_extract_with_dash(self):
        refs = extract_references("article D. 421-11-1")
        assert "D421-11-1" in refs


class TestGraphBuilder:
    def test_build_from_chunks(self):
        graph = build_graph_from_chunks(SAMPLE_CHUNKS)
        assert graph is not None
        assert graph.number_of_nodes() == 3
        assert graph.number_of_edges() >= 2

    def test_nodes_have_attributes(self):
        graph = build_graph_from_chunks(SAMPLE_CHUNKS)
        node = graph.nodes["L421-1"]
        assert node["label"] == "Article L421-1"
        assert node["livre"] == "IV"
        assert node["entity_type"] == "article"

    def test_edges_have_type(self):
        graph = build_graph_from_chunks(SAMPLE_CHUNKS)
        assert graph.has_edge("L421-1", "L110-1")
        edge = graph.edges["L421-1", "L110-1"]
        assert edge["description"] == "cite"

    def test_bidirectional_references(self):
        graph = build_graph_from_chunks(SAMPLE_CHUNKS)
        # L421-1 → L321-4 and L321-4 → L421-1
        assert graph.has_edge("L421-1", "L321-4")
        assert graph.has_edge("L321-4", "L421-1")

    def test_referenced_by_populated(self):
        graph = build_graph_from_chunks(SAMPLE_CHUNKS)
        node = graph.nodes["L110-1"]
        assert "L421-1" in node.get("referenced_by", [])

    def test_degree(self):
        graph = build_graph_from_chunks(SAMPLE_CHUNKS)
        # L421-1 has edges to L110-1 and L321-4
        assert graph.degree("L421-1") >= 2


class TestGraphBuilderClass:
    @pytest.fixture
    def builder(self, tmp_path):
        return GraphBuilder(data_dir=str(tmp_path))

    def test_build_and_save(self, builder):
        builder.build("test-col", SAMPLE_CHUNKS)
        assert builder.get("test-col") is not None
        assert builder.get("test-col").number_of_nodes() == 3

    def test_save_and_load(self, builder):
        builder.build("test-col", SAMPLE_CHUNKS)
        builder.save("test-col")

        # Create new builder and load
        builder2 = GraphBuilder(data_dir=builder.data_dir)
        graph = builder2.load("test-col")
        assert graph is not None
        assert graph.number_of_nodes() == 3

    def test_get_subgraph(self, builder):
        builder.build("test-col", SAMPLE_CHUNKS)
        sub = builder.get_subgraph("test-col", ["L421-1"], depth=1)
        assert sub is not None
        assert "L421-1" in sub.nodes
        assert "L110-1" in sub.nodes  # 1 hop away

    def test_to_graph_data_response(self, builder):
        builder.build("test-col", SAMPLE_CHUNKS)
        response = builder.to_graph_data_response("test-col")
        assert response["graph_ready"] is True
        assert len(response["nodes"]) == 3
        assert len(response["edges"]) >= 2

        # Check node format
        node = next(n for n in response["nodes"] if n["id"] == "L421-1")
        assert node["label"] == "Article L421-1"
        assert node["entity_type"] == "article"
        assert node["degree"] >= 2
        assert "source_group" in node

    def test_nonexistent_collection(self, builder):
        assert builder.get("nonexistent") is None

    def test_empty_chunks(self, builder):
        builder.build("empty", [])
        graph = builder.get("empty")
        assert graph.number_of_nodes() == 0
