#!/usr/bin/env python3
"""Build the article reference graph for a collection from a local file.

Usage:
    python build-graph.py CESEDA.md ceseda-v3
    python build-graph.py document.md my-collection --strategy article
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.services.chunker import chunk_document
from app.services.graph_builder import GraphBuilder


def main():
    parser = argparse.ArgumentParser(description="Build MyRAG article reference graph")
    parser.add_argument("file", help="Source document (MD/TXT)")
    parser.add_argument("collection", help="Collection name")
    parser.add_argument("--strategy", default="auto", help="Chunking strategy")
    parser.add_argument("--data-dir", default="./data", help="Data directory")
    args = parser.parse_args()

    # Read file
    print(f"Reading {args.file}...")
    with open(args.file) as f:
        text = f.read()
    print(f"  {len(text)} chars, {text.count(chr(10))} lines")

    # Chunk
    print(f"Chunking with strategy '{args.strategy}'...")
    chunks = chunk_document(text, strategy=args.strategy)
    print(f"  {len(chunks)} chunks produced")

    articles = [c for c in chunks if c.get("metadata", {}).get("article")]
    print(f"  {len(articles)} articles detected")

    if not articles:
        print("No articles found. Cannot build graph.")
        sys.exit(1)

    # Build graph
    print("Building graph...")
    os.environ.setdefault("DATA_DIR", args.data_dir)

    builder = GraphBuilder(data_dir=args.data_dir)
    graph = builder.build(args.collection, chunks)

    print(f"  {graph.number_of_nodes()} nodes")
    print(f"  {graph.number_of_edges()} edges")

    # Stats
    if graph.number_of_nodes() > 0:
        degrees = [graph.degree(n) for n in graph.nodes]
        avg_degree = sum(degrees) / len(degrees)
        max_node = max(graph.nodes, key=lambda n: graph.degree(n))
        print(f"  Average degree: {avg_degree:.1f}")
        print(f"  Most connected: {max_node} ({graph.degree(max_node)} connections)")

        # Top 10 most connected
        top = sorted(graph.nodes, key=lambda n: graph.degree(n), reverse=True)[:10]
        print(f"\n  Top 10 most connected articles:")
        for n in top:
            refs_out = list(graph.successors(n))
            refs_in = graph.nodes[n].get("referenced_by", [])
            print(f"    {n}: {graph.degree(n)} links ({len(refs_out)} cites, {len(refs_in)} cited by)")

    # Save
    builder.save(args.collection)
    graph_path = os.path.join(args.data_dir, args.collection, "graph.json")
    size = os.path.getsize(graph_path)
    print(f"\nGraph saved: {graph_path} ({size / 1024:.1f} KB)")

    # Verify GraphDataResponse
    response = builder.to_graph_data_response(args.collection)
    print(f"GraphDataResponse: {response['total_nodes']} nodes, {response['total_edges']} edges, graph_ready={response['graph_ready']}")

    print("\nDone! Test with:")
    print(f"  curl http://localhost:8200/graph?corpus_id={args.collection}")
    print(f"  curl http://localhost:8200/graph/data?corpus_id={args.collection}")


if __name__ == "__main__":
    main()
